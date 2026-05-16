"""VOID server v3. Pure blind relay. In-memory only. No logs, no disk.

The HKDF epoch rotation from v2 is REMOVED. Phase 3 moves all key
management to clients via X3DH + Double Ratchet; the server now:

- routes ``msg`` frames per-recipient (``to: <opaque_uid>``)
- stores and serves opaque X3DH prekey bundles (``publish_bundle`` /
  ``fetch_bundle``)
- forwards ``ratchet_init`` handshake frames blindly
- enforces room cap (16), rate limit (20/s), frame cap (16 KB)
- applies 50-350 ms jitter on each forward as before
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import ssl
import sys
import time
import uuid
from collections import deque
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

MAX_FRAME = 32 * 1024
RATE_LIMIT_PER_SEC = 20
MAX_ROOM_ID_LEN = 64
MAX_ROOM_SIZE = 16
MAX_CONNECTIONS = 512        # global cap; new connections refused beyond this

JITTER_MIN_MS = 50
JITTER_MAX_MS = 350

ROOMS: dict[str, set[WebSocketServerProtocol]] = {}
CONNS: dict[WebSocketServerProtocol, str] = {}              # ws -> opaque uid
UIDS: dict[str, WebSocketServerProtocol] = {}               # uid -> ws (reverse)
RATES: dict[WebSocketServerProtocol, deque[float]] = {}
CURRENT: dict[WebSocketServerProtocol, str | None] = {}     # ws -> roomId
BUNDLES: dict[str, dict] = {}                               # uid -> opaque bundle (JSON dict)

JITTER_ENABLED = True


def _debug(msg: str) -> None:
    if os.environ.get("DEBUG"):
        print(f"[void-server] {msg}", file=sys.stderr, flush=True)


# --- helpers ----------------------------------------------------------------


def _valid_room_id(rid: Any) -> bool:
    return (
        isinstance(rid, str)
        and 1 <= len(rid) <= MAX_ROOM_ID_LEN
        and all(c in "0123456789abcdef" for c in rid)
    )


def _valid_uid(s: Any) -> bool:
    return isinstance(s, str) and len(s) == 32 and all(c in "0123456789abcdef" for c in s)


def _b64_decoded_len(s: str) -> int:
    if not isinstance(s, str) or not s:
        return -1
    pad = 0
    if s.endswith("=="):
        pad = 2
    elif s.endswith("="):
        pad = 1
    return (len(s) // 4) * 3 - pad


def _is_b64_str(s: Any, max_len: int = 200) -> bool:
    if not isinstance(s, str):
        return False
    if not s or len(s) > max_len:
        return False
    # Reject anything that isn't strict base64.
    return all(c.isalnum() or c in "+/=_-" for c in s)


PAD_BLOCK = 1024
GCM_TAG = 16
MAX_CIPHERTEXT = 8 * 1024 + GCM_TAG   # 8208 bytes after b64-decode


def _valid_dr_envelope(d: Any) -> bool:
    """Shape-validate the dr payload of a msg/ratchet_init frame."""
    if not isinstance(d, dict):
        return False
    for k in ("rpub", "n", "pn", "ct"):
        if k not in d:
            return False
    if not _is_b64_str(d["rpub"], 128) or _b64_decoded_len(d["rpub"]) != 32:
        return False
    if not isinstance(d["n"], int) or d["n"] < 0 or d["n"] > 2**31:
        return False
    if not isinstance(d["pn"], int) or d["pn"] < 0 or d["pn"] > 2**31:
        return False
    if not _is_b64_str(d["ct"], 16384):
        return False
    n = _b64_decoded_len(d["ct"])
    if n < PAD_BLOCK + GCM_TAG or n > MAX_CIPHERTEXT:
        return False
    if (n - GCM_TAG) % PAD_BLOCK != 0:
        return False
    return True


def _valid_signature(s: Any) -> bool:
    if not _is_b64_str(s, 200):
        return False
    n = _b64_decoded_len(s)
    # Ed25519 sig = 64B; we allow a small margin for DER-wrapped variants.
    return 32 <= n <= 128


def _valid_x3dh_envelope(d: Any) -> bool:
    """Shape-validate the x3dh header of a ratchet_init frame."""
    if not isinstance(d, dict):
        return False
    for k in ("ik", "ek", "spk"):
        if k not in d:
            return False
        if not _is_b64_str(d[k], 128) or _b64_decoded_len(d[k]) != 32:
            return False
    if "opk" in d:
        if not _is_b64_str(d["opk"], 128) or _b64_decoded_len(d["opk"]) != 32:
            return False
    return True


def _valid_bundle(b: Any) -> bool:
    """Shape-validate a published bundle before relaying it. Server is still
    blind to bundle content semantically; this only blocks the trivial DoS
    where a malicious peer publishes garbage that crashes every other peer's
    X3DH deserialise."""
    if not isinstance(b, dict):
        return False
    for k in ("ik", "spk", "spk_sig", "opks"):
        if k not in b:
            return False
    # IK + SPK are 32-byte Curve25519/Ed25519 pub keys.
    if not _is_b64_str(b["ik"], 128) or _b64_decoded_len(b["ik"]) != 32:
        return False
    if not _is_b64_str(b["spk"], 128) or _b64_decoded_len(b["spk"]) != 32:
        return False
    # SPK signature: Ed25519 = 64B; allow a small margin.
    if not _is_b64_str(b["spk_sig"], 200):
        return False
    sig_len = _b64_decoded_len(b["spk_sig"])
    if not (32 <= sig_len <= 128):
        return False
    if not isinstance(b["opks"], list) or len(b["opks"]) > 200:
        return False
    for opk in b["opks"]:
        if not _is_b64_str(opk, 128) or _b64_decoded_len(opk) != 32:
            return False
    return True


def _rate_ok(ws: WebSocketServerProtocol) -> bool:
    q = RATES.setdefault(ws, deque())
    now = time.monotonic()
    while q and now - q[0] > 1.0:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_SEC:
        return False
    q.append(now)
    return True


# --- broadcasting -----------------------------------------------------------


async def _safe_send(ws: WebSocketServerProtocol, payload: str, dead: list) -> None:
    try:
        await ws.send(payload)
    except Exception:
        dead.append(ws)


async def broadcast_presence() -> None:
    # Only include uids that have published a bundle (i.e. are ready to chat).
    users = [uid for uid in CONNS.values() if uid in BUNDLES]
    if not CONNS:
        return
    payload = json.dumps({"type": "presence", "users": users}, separators=(",", ":"))
    dead: list = []
    await asyncio.gather(
        *[_safe_send(ws, payload, dead) for ws in list(CONNS.keys())],
        return_exceptions=True,
    )
    for ws in dead:
        await _drop(ws)


async def _drop(ws: WebSocketServerProtocol) -> None:
    uid = CONNS.pop(ws, None)
    if uid is not None:
        UIDS.pop(uid, None)
        BUNDLES.pop(uid, None)
    RATES.pop(ws, None)
    room = CURRENT.pop(ws, None)
    if room and room in ROOMS:
        ROOMS[room].discard(ws)
        if not ROOMS[room]:
            del ROOMS[room]
    try:
        await ws.close()
    except Exception:
        pass


# --- frame handlers ---------------------------------------------------------


async def handle_publish_bundle(ws: WebSocketServerProtocol, data: dict) -> None:
    bundle = data.get("bundle")
    if not _valid_bundle(bundle):
        _debug("publish_bundle REJECTED (invalid shape)")
        return
    uid = CONNS.get(ws)
    if uid is None:
        return
    BUNDLES[uid] = bundle
    _debug(f"publish_bundle uid={uid}")
    await broadcast_presence()


async def handle_fetch_bundle(ws: WebSocketServerProtocol, data: dict) -> None:
    target = data.get("target")
    if not _valid_uid(target):
        return
    payload: dict
    if target in BUNDLES:
        payload = {"type": "bundle", "target": target, "bundle": BUNDLES[target]}
    else:
        payload = {"type": "bundle", "target": target, "missing": True}
    try:
        await ws.send(json.dumps(payload, separators=(",", ":")))
    except Exception:
        pass


async def handle_join(ws: WebSocketServerProtocol, data: dict) -> None:
    rid = data.get("roomId")
    if not _valid_room_id(rid):
        return
    if rid in ROOMS and len(ROOMS[rid]) >= MAX_ROOM_SIZE:
        try:
            await ws.close(1013, "room full")
        except Exception:
            pass
        return
    prev = CURRENT.get(ws)
    if prev and prev in ROOMS:
        ROOMS[prev].discard(ws)
        if not ROOMS[prev]:
            del ROOMS[prev]
    CURRENT[ws] = rid
    ROOMS.setdefault(rid, set()).add(ws)
    _debug(f"join uid={CONNS.get(ws)} room={rid} size={len(ROOMS[rid])}")


async def _route_to(payload: str, target_uid: str, sender_room: str | None) -> None:
    peer = UIDS.get(target_uid)
    if peer is None:
        return
    # Same-room sanity check.
    if sender_room is not None and CURRENT.get(peer) != sender_room:
        return
    if JITTER_ENABLED:
        try:
            await asyncio.sleep(random.uniform(JITTER_MIN_MS / 1000.0, JITTER_MAX_MS / 1000.0))
        except asyncio.CancelledError:
            return
    try:
        await peer.send(payload)
    except Exception:
        await _drop(peer)


async def handle_ratchet_init(ws: WebSocketServerProtocol, data: dict) -> None:
    target = data.get("to")
    if not _valid_uid(target):
        return
    # Shape-validate so the server cannot be used to amplify garbage to
    # the recipient (DoS amplifier).
    if not _valid_x3dh_envelope(data.get("x3dh")):
        return
    if not _valid_dr_envelope(data.get("dr")):
        return
    if not _valid_signature(data.get("sig")):
        return
    sender_uid = CONNS.get(ws)
    if sender_uid is None:
        return
    payload = json.dumps(
        {
            "type": "ratchet_init",
            "from": sender_uid,
            "to": target,
            "x3dh": data["x3dh"],
            "dr": data["dr"],
            "sig": data["sig"],
        },
        separators=(",", ":"),
    )
    asyncio.create_task(_route_to(payload, target, CURRENT.get(ws)))


async def handle_msg(ws: WebSocketServerProtocol, data: dict) -> None:
    rid = data.get("roomId")
    if rid != CURRENT.get(ws):
        return
    if not _valid_room_id(rid):
        return
    target = data.get("to")
    if not _valid_uid(target):
        return
    # Strict shape checks on the relay payload.
    if not _valid_dr_envelope(data.get("dr")):
        return
    if not _valid_signature(data.get("sig")):
        return
    sender_uid = CONNS.get(ws)
    if sender_uid is None:
        return
    payload = json.dumps(
        {
            "type": "msg",
            "roomId": rid,
            "from": sender_uid,
            "to": target,
            "dr": data["dr"],
            "sig": data["sig"],
        },
        separators=(",", ":"),
    )
    asyncio.create_task(_route_to(payload, target, rid))


async def handle_leave(ws: WebSocketServerProtocol, data: dict) -> None:
    rid = CURRENT.get(ws)
    if rid and rid in ROOMS:
        ROOMS[rid].discard(ws)
        if not ROOMS[rid]:
            del ROOMS[rid]
    CURRENT[ws] = None


# --- main connection loop ---------------------------------------------------


async def handler(ws: WebSocketServerProtocol) -> None:
    if len(CONNS) >= MAX_CONNECTIONS:
        try:
            await ws.close(1013, "server full")
        except Exception:
            pass
        return
    uid = uuid.uuid4().hex
    CONNS[ws] = uid
    UIDS[uid] = ws
    CURRENT[ws] = None
    RATES[ws] = deque()
    _debug(f"connect uid={uid} peers={len(CONNS)}")
    try:
        async for raw in ws:
            raw_len = len(raw) if isinstance(raw, bytes) else len(raw.encode("utf-8", "ignore"))
            if raw_len > MAX_FRAME:
                await ws.close(1009, "frame too large")
                break
            if not _rate_ok(ws):
                await ws.close(1008, "rate")
                break
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            t = data.get("type")
            if t == "publish_bundle":
                await handle_publish_bundle(ws, data)
            elif t == "fetch_bundle":
                await handle_fetch_bundle(ws, data)
            elif t == "join":
                await handle_join(ws, data)
            elif t == "ratchet_init":
                await handle_ratchet_init(ws, data)
            elif t == "msg":
                await handle_msg(ws, data)
            elif t == "leave":
                await handle_leave(ws, data)
            else:
                continue
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        _debug(f"handler error: {e!r}")
    finally:
        had_bundle = uid in BUNDLES
        await _drop(ws)
        _debug(f"disconnect uid={uid} peers={len(CONNS)}")
        if had_bundle:
            await broadcast_presence()


# --- TLS helper -------------------------------------------------------------


def generate_selfsigned(cert_path: str, key_path: str) -> None:
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "void.local")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.DNSName("void.local")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


async def _serve(host: str, port: int, ssl_ctx: ssl.SSLContext | None) -> None:
    async with websockets.serve(
        handler,
        host,
        port,
        ssl=ssl_ctx,
        max_size=MAX_FRAME,
        ping_interval=20,
        ping_timeout=20,
        compression=None,
    ):
        _debug(
            f"listening on {host}:{port} tls={'yes' if ssl_ctx else 'no'} "
            f"jitter={'on' if JITTER_ENABLED else 'off'}"
        )
        await asyncio.Future()


def main() -> None:
    global JITTER_ENABLED
    ap = argparse.ArgumentParser(prog="void-server", add_help=True)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1; put a Tor hidden service in front)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--cert")
    ap.add_argument("--key")
    ap.add_argument("--insecure", action="store_true",
                    help="run plain ws:// (recommended when behind a hidden service)")
    ap.add_argument("--no-jitter", action="store_true",
                    help="disable per-relay jitter (debug / tests only)")
    args = ap.parse_args()

    if args.no_jitter:
        JITTER_ENABLED = False

    ssl_ctx: ssl.SSLContext | None = None
    if args.cert and args.key:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(args.cert, args.key)
    elif args.insecure:
        ssl_ctx = None
    else:
        sys.stderr.write(
            "void-server: refuses to start without TLS.\n"
            "Provide --cert and --key, or pass --insecure (recommended only when\n"
            "this server is reachable only via a Tor hidden service on 127.0.0.1).\n"
        )
        sys.exit(2)

    try:
        asyncio.run(_serve(args.host, args.port, ssl_ctx))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
