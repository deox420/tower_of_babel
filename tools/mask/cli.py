"""MASK CLI front-end.

Subcommands::

    babel mask                              # interactive screen
    babel mask new [--locale ...] [--profile ...] [--no-mail] [--no-avatar]
                   [--clearnet --i-know] [--export PATH] [--export-avatar PATH]
                   [--json]
    babel mask decode <mask://...>
    babel mask import <blob-path>
    babel mask --setup

Passphrase is read from ``BABEL_MASK_PASS`` if set, otherwise
prompted on stdin with masking when a TTY is attached. Exit codes
follow ``docs/tools/MASK.md`` Section 4.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from tools.mask.alias import LOCALES, PROFILES
from tools.mask.bundle import (
    MalformedBlob, WrongPassphrase, export_blob, import_blob,
    passphrase_as_secure,
)
from tools.mask.link import build as mask_build, parse as mask_parse
from tools.mask.mail import MailUnavailable, TorRequired
from tools.mask.pipeline import GenerateOpts, generate_identity


# Exit codes (MASK.md Section 4)
EX_OK = 0
EX_WARN = 1
EX_USAGE = 2
EX_IO = 3
EX_MAIL = 4
EX_TOR = 5
EX_WRONGPASS = 6


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="babel mask",
        description="disposable identity generator -- "
                    "alias + bio + local avatar + temp-mail",
    )
    p.add_argument("--setup", action="store_true",
                   help="diagnostic: argon2 + Pillow + httpx + Tor")
    sub = p.add_subparsers(dest="cmd")

    p_new = sub.add_parser("new", help="generate a fresh identity")
    p_new.add_argument("--locale", choices=LOCALES, default="en")
    p_new.add_argument("--profile", choices=PROFILES, default="default")
    p_new.add_argument("--no-mail", action="store_true",
                       help="skip the temp-mail acquisition step")
    p_new.add_argument("--no-avatar", action="store_true",
                       help="skip avatar generation (rare; saves ~5ms)")
    p_new.add_argument("--clearnet", action="store_true",
                       help="bypass Tor for mail (requires --i-know)")
    p_new.add_argument("--i-know", action="store_true",
                       help="confirm that you accept the clearnet warning")
    p_new.add_argument("--export", metavar="PATH",
                       help="passphrase-encrypted bundle written to PATH")
    p_new.add_argument("--export-avatar", metavar="PATH",
                       help="write the 256x256 avatar PNG to PATH")
    p_new.add_argument("--json", action="store_true",
                       help="emit the full bundle as JSON instead of mask://")

    p_dec = sub.add_parser("decode", help="parse a mask:// URL")
    p_dec.add_argument("url")
    p_dec.add_argument("--json", action="store_true")

    p_imp = sub.add_parser("import",
                           help="decrypt a previously exported blob")
    p_imp.add_argument("blob_path")
    p_imp.add_argument("--json", action="store_true")

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.setup:
        from tools.mask.setup_check import run as setup_run
        code, lines = setup_run()
        for line in lines:
            sys.stdout.write(line + "\n")
        return code

    if args.cmd is None:
        return _run_interactive()
    if args.cmd == "new":
        return _cmd_new(args)
    if args.cmd == "decode":
        return _cmd_decode(args)
    if args.cmd == "import":
        return _cmd_import(args)
    parser.print_help()
    return EX_USAGE


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_new(args: argparse.Namespace) -> int:
    # Clearnet requires explicit opt-in.  No exceptions on the CLI
    # path; the interactive screen has its own confirmation panel.
    use_tor = not args.clearnet
    if args.clearnet and not args.i_know:
        sys.stderr.write(_CLEARNET_BANNER)
        sys.stderr.write(
            "mask: --clearnet bypasses Tor. Re-run with --i-know "
            "to confirm.\n"
        )
        return EX_USAGE

    opts = GenerateOpts(
        locale=args.locale, profile=args.profile,
        use_tor=use_tor, fetch_mail=not args.no_mail,
    )

    warn = False
    try:
        identity = asyncio.run(generate_identity(opts))
    except TorRequired as e:
        sys.stderr.write(f"mask: {e}\n")
        return EX_TOR
    except MailUnavailable as e:
        sys.stderr.write(f"mask: mail provider unreachable: {e}\n")
        return EX_MAIL
    except ValueError as e:
        sys.stderr.write(f"mask: {e}\n")
        return EX_USAGE

    if opts.fetch_mail and identity.mail is None:
        # Pipeline swallowed a MailUnavailable -- mail provider failed
        # but the alias / avatar still generated.  Warn but exit 1.
        warn = True
        sys.stderr.write("mask: warning: mail provider unreachable; "
                         "identity generated without mail handle\n")

    # ----- emit the primary output -------------------------------------
    if args.json:
        sys.stdout.write(json.dumps(identity.to_dict(), indent=2,
                                    sort_keys=True) + "\n")
    else:
        sys.stdout.write(mask_build(identity) + "\n")

    # ----- optional exports --------------------------------------------
    if args.export_avatar:
        try:
            Path(args.export_avatar).expanduser().write_bytes(
                identity.avatar.png_bytes)
        except OSError as e:
            sys.stderr.write(f"mask: avatar write failed: {e}\n")
            return EX_IO

    if args.export:
        passphrase = _read_passphrase(confirm=True)
        if passphrase is None:
            return EX_USAGE
        with passphrase_as_secure(passphrase) as pwbuf:
            try:
                blob = export_blob(identity, pwbuf)
            except Exception as e:
                sys.stderr.write(f"mask: export failed: {e}\n")
                return EX_IO
        try:
            Path(args.export).expanduser().write_bytes(blob)
        except OSError as e:
            sys.stderr.write(f"mask: export write failed: {e}\n")
            return EX_IO

    return EX_WARN if warn else EX_OK


def _cmd_decode(args: argparse.Namespace) -> int:
    try:
        identity = mask_parse(args.url)
    except Exception as e:
        sys.stderr.write(f"mask: decode failed: {e}\n")
        return EX_USAGE
    if args.json:
        sys.stdout.write(json.dumps(identity.to_dict(), indent=2,
                                    sort_keys=True) + "\n")
        return EX_OK
    _print_identity(identity)
    return EX_OK


def _cmd_import(args: argparse.Namespace) -> int:
    try:
        blob = Path(args.blob_path).expanduser().read_bytes()
    except OSError as e:
        sys.stderr.write(f"mask: cannot read blob: {e}\n")
        return EX_IO

    passphrase = _read_passphrase(confirm=False)
    if passphrase is None:
        return EX_USAGE

    with passphrase_as_secure(passphrase) as pwbuf:
        try:
            identity = import_blob(blob, pwbuf)
        except WrongPassphrase:
            sys.stderr.write("mask: wrong passphrase\n")
            return EX_WRONGPASS
        except MalformedBlob as e:
            sys.stderr.write(f"mask: {e}\n")
            return EX_USAGE
        except Exception as e:
            sys.stderr.write(f"mask: import failed: {e}\n")
            return EX_IO

    if args.json:
        sys.stdout.write(json.dumps(identity.to_dict(), indent=2,
                                    sort_keys=True) + "\n")
    else:
        _print_identity(identity)
    return EX_OK


def _run_interactive() -> int:
    """Removed in v2.0.0 — interactive MASK is reached via `babel`.

    Returns a usage error pointing at the new entry point so old
    docs and muscle memory get a clear redirect rather than a crash.
    """
    sys.stderr.write(
        "mask: interactive MASK is now part of the babel menu in v2.0.0.\n"
        "      run `babel` and pick `[2] MASK`, or use `babel --exec mask "
        "new ...` for one-shot scripting.\n"
    )
    return EX_USAGE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_CLEARNET_BANNER = (
    "\n"
    "  ! CLEARNET MODE -- Tor will not be used for the mail request.\n"
    "    Your OS resolver and your ISP will see api.mail.tm /\n"
    "    api.guerrillamail.com lookups originating from your IP.\n"
    "\n"
)


def _read_passphrase(*, confirm: bool) -> bytes | None:
    env = os.environ.get("BABEL_MASK_PASS")
    if env is not None:
        return env.encode("utf-8")
    try:
        p1 = getpass.getpass("passphrase: ")
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\nmask: no passphrase\n")
        return None
    if not p1:
        sys.stderr.write("mask: empty passphrase refused\n")
        return None
    if confirm:
        try:
            p2 = getpass.getpass("passphrase (confirm): ")
        except (EOFError, KeyboardInterrupt):
            sys.stderr.write("\nmask: no passphrase\n")
            return None
        if p1 != p2:
            sys.stderr.write("mask: passphrases do not match\n")
            return None
    return p1.encode("utf-8")


def _print_identity(identity) -> None:
    a = identity.alias
    sys.stdout.write(f" alias    {a.given} {a.family} "
                     f"({a.locale}, {a.profile})\n")
    sys.stdout.write(f" handle   {a.handle}\n")
    sys.stdout.write(f" bio      {identity.bio}\n")
    sys.stdout.write(f" avatar   sha256:{identity.avatar.sha256}\n")
    if identity.mail is not None:
        sys.stdout.write(f" mail     {identity.mail.address} "
                         f"({identity.mail.provider})\n")
        if identity.mail.inbox_url:
            sys.stdout.write(f"          inbox: {identity.mail.inbox_url}\n")
    else:
        sys.stdout.write(" mail     (none)\n")
    sys.stdout.write(f" ts       {identity.ts}\n")


if __name__ == "__main__":
    raise SystemExit(main())
