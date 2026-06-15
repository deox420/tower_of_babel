"""``void --make-invite``: one-shot host.

Speaks the Tor control-port protocol directly (no ``stem`` dependency)
to spin up an *ephemeral* hidden service, embeds a void-server inside
this process, and prints a single ``void://...`` link the user pastes
to their peer. When the user hits Ctrl+C the onion vanishes — true to
VOID's "no persistence" promise.

Supported Tor configs (in order of preference):
  - cookie auth   (most Linux / macOS distros, Termux)
  - safe-cookie   (newer Tor)
  - null auth     (uncommon but allowed)
  - password auth (Tor Browser bundle on Windows) — falls back to a
    clear error if a password is required and we don't have one.

The user does NOT need to edit torrc as long as the control port is
already exposed. If it isn't, we tell them in plain English what to
add.
"""
from __future__ import annotations

import asyncio
import secrets
import socket
import sys

from shared.tor.control import TorControl, TorControlError, TorInfo  # noqa: F401

from . import link as link_module


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _print_banner(invite: str, onion: str, room: str, pw: str) -> None:
    sep = "═" * 64
    print()
    print(sep)
    print("  VOID — hosting an ephemeral room")
    print(sep)
    print()
    print("  Share this invite with your peer (one line):")
    print()
    print(f"    {invite}")
    print()
    print("  details inside the invite:")
    print(f"    onion    : {onion}")
    print(f"    room key : {room}")
    print(f"    password : {pw}")
    print()
    print("  The invite stays valid only while this command runs.")
    print("  Ctrl+C to stop and delete the onion.")
    print(sep)
    print()


async def make_invite_main() -> int:
    # 1. Control port
    try:
        ctrl = await TorControl.connect()
    except TorControlError as e:
        print(f"void: {e}", file=sys.stderr)
        return 1

    # 2. ProtocolInfo + auth
    try:
        info = await ctrl.protocol_info()
        await ctrl.authenticate(info)
    except TorControlError as e:
        print(f"void: {e}", file=sys.stderr)
        await ctrl.close()
        return 1

    # 3. Pick a local port and spin up an onion → 8765 → 127.0.0.1:LOCAL
    local_port = _pick_free_port()
    virt_port = 8765
    try:
        service_id = await ctrl.add_onion(virt_port, local_port)
    except TorControlError as e:
        print(f"void: could not create onion: {e}", file=sys.stderr)
        await ctrl.close()
        return 1

    onion = f"{service_id}.onion:{virt_port}"

    # 4. Random room + password
    room = secrets.token_urlsafe(6).rstrip("=")[:8]
    pw = secrets.token_urlsafe(9).rstrip("=")[:12]

    invite = link_module.encode(link_module.Invite(onion=onion, room=room, password=pw))
    _print_banner(invite, onion, room, pw)

    # 5. Launch server inside this process.
    from tools.void.server import main as server_main_mod
    server_task = asyncio.create_task(
        server_main_mod._serve("127.0.0.1", local_port, None)
    )

    async def keepalive() -> None:
        try:
            while True:
                await asyncio.sleep(30)
                try:
                    await ctrl._cmd("GETINFO version")
                except Exception:
                    return
        except asyncio.CancelledError:
            return

    keep_task = asyncio.create_task(keepalive())

    try:
        await asyncio.gather(server_task, keep_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        try:
            await ctrl.del_onion(service_id)
        except Exception:
            pass
        try:
            await ctrl.close()
        except Exception:
            pass
        print("\nvoid: stopped. onion deleted.")
    return 0


def run() -> int:
    try:
        return asyncio.run(make_invite_main())
    except KeyboardInterrupt:
        return 0
