"""``babel`` entry point.

Argv shapes (MASTER.md Section 4.1):

    babel                        -> open the main menu
    babel --help                 -> suite-level help text
    babel --version              -> print VERSION and exit
    babel <tool> [tool args...]  -> bypass menu, run that tool directly
    babel <tool> --setup         -> that tool's diagnostic
    babel <tool> --help          -> that tool's help
    babel --setup                -> aggregated diagnostic across all tools
    babel --make-invite          -> alias for `babel void --make-invite`
    babel --ascii                -> force Tier-1 ASCII chrome (MASTER.md 3.5)
"""
from __future__ import annotations

import os
import sys
from typing import Callable, Sequence

KNOWN_TOOLS = {"void", "mask", "strip", "carrier", "mirage"}


SUITE_HELP = """\
babel -- Tower of Babel suite launcher

usage:
  babel                       open the main menu
  babel <tool> [args]         jump straight into a tool
  babel <tool> --help         per-tool help
  babel <tool> --setup        per-tool diagnostic
  babel --setup               aggregated diagnostic across every tool
  babel --version             print the suite version
  babel --make-invite         shortcut for `babel void --make-invite`
  babel --ascii               force Tier-1 ASCII chrome (small terminals)

tools (MASTER.md Section 7):
  void      ephemeral encrypted messenger over Tor
  mask      disposable identity generator
  strip     metadata laundry
  carrier   steganography (PNG / WAV)
  mirage    cover traffic generator

See README.md, RELEASE_NOTES.md, and docs/tools/<NAME>.md for detail.
"""


def _read_version() -> str:
    """Read VERSION sitting next to the repo root.  Falls back gracefully."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "..", "VERSION"),
        os.path.join(here, "VERSION"),
    ):
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return "0.0.0"


def _run_void(args: Sequence[str]) -> int:
    """Hand off to VOID's existing CLI exactly as `void <args>` would."""
    from tools.void.client.app import main as void_main
    sys.argv = ["void"] + list(args)
    void_main()
    return 0


def _run_strip(args: Sequence[str]) -> int:
    """Hand off to STRIP's argparse CLI."""
    from tools.strip.cli import main as strip_main
    return strip_main(list(args))


def _run_carrier(args: Sequence[str]) -> int:
    """Hand off to CARRIER's argparse CLI."""
    from tools.carrier.cli import main as carrier_main
    return carrier_main(list(args))


def _run_mask(args: Sequence[str]) -> int:
    """Hand off to MASK's argparse CLI."""
    from tools.mask.cli import main as mask_main
    return mask_main(list(args))


def _run_mirage(args: Sequence[str]) -> int:
    """Hand off to MIRAGE's argparse CLI."""
    from tools.mirage.cli import main as mirage_main
    return mirage_main(list(args))


def _run_menu() -> int:
    """Launch ChromeApp with the suite menu mounted as the first view.

    Multiplex flow (MASTER.md 4.4, docs/NAVIGATION.md):
    every tool view mounts inside the chrome's content slot.
    SERVICE-flavour tools (VOID, MIRAGE) get a numbered slot via
    the registry, reachable with Alt+<digit>; ACTION-flavour tools
    (MASK, STRIP, CARRIER) tear down on Esc.

    Phase 7 v1.0 bridge: the VoidView lobby cannot run the chat /
    connecting / starmap flows in-chrome yet (those are Screen
    subclasses under tools/void/client/app.py).  When the user
    submits the lobby, ``ChromeApp.void_session_bridge`` stashes
    the args on the App and exits.  We catch that here and run the
    legacy ``VoidApp`` against the populated arguments.  Subsequent
    post-1.0 work removes this branch entirely.
    """
    from babel.menu import MainMenuView
    from babel.shell import ChromeApp

    app = ChromeApp(initial_view=MainMenuView(), version=_read_version())
    app.run()

    # VOID session bridge: if the user submitted the lobby, relaunch
    # the legacy VoidApp with the populated arguments.
    args = getattr(app, "_void_session_args", None)
    if args:
        # Build the argv equivalent of "babel void <inferred flags>"
        # so the existing CLI / lobby autofill path takes over.  The
        # legacy lobby will re-show with the room + password + onion
        # pre-set via the env hand-off below.
        os.environ["BABEL_VOID_ROOM"] = str(args.get("room", ""))
        os.environ["BABEL_VOID_PASSWORD"] = str(args.get("password", ""))
        os.environ["BABEL_VOID_SERVER"] = str(args.get("server", ""))
        os.environ["BABEL_VOID_ONION"] = str(args.get("onion", ""))
        return _run_void([])

    return 0


def _run_setup() -> int:
    """Aggregate every tool's ``setup_check.run()``.

    Each contributor returns ``(exit_code, list[str])``; we
    concatenate the lines and return the worst exit code. Phase 2
    has VOID + STRIP wired in; later tools slot into ``contributors``
    as they ship.
    """
    contributors: list[tuple[str, Callable[[], tuple[int, list[str]]]]] = []

    try:
        from tools.void.client.setup_check import run as void_run
        contributors.append(("void", void_run))
    except Exception:
        pass

    try:
        from tools.strip.setup_check import run as strip_run
        contributors.append(("strip", strip_run))
    except Exception:
        pass

    try:
        from tools.carrier.setup_check import run as carrier_run
        contributors.append(("carrier", carrier_run))
    except Exception:
        pass

    try:
        from tools.mask.setup_check import run as mask_run
        contributors.append(("mask", mask_run))
    except Exception:
        pass

    try:
        from tools.mirage.setup_check import run as mirage_run
        contributors.append(("mirage", mirage_run))
    except Exception:
        pass

    worst = 0
    for _name, fn in contributors:
        try:
            result = fn()
        except Exception as e:
            sys.stderr.write(f"setup: {_name} diagnostic failed: {e}\n")
            worst = max(worst, 1)
            continue
        # MASTER.md 6.3 contract is (code, lines), but VOID's pre-suite
        # diagnostic still writes its own lines and returns only int.
        # Accept both shapes so the aggregator survives the transition.
        if isinstance(result, tuple) and len(result) == 2:
            code, lines = result
            for line in lines:
                sys.stdout.write(line + "\n")
        else:
            code = int(result)
        worst = max(worst, code)
    return worst


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = list(argv)

    # ``--ascii`` is a global modifier; consume it before tool dispatch so
    # tools never see it.  Without it, the auto-detector inspects $LANG,
    # $TERM, and the stdout encoding (cp1252 etc. -> ASCII fallback).
    from babel import theme
    if "--ascii" in args:
        args = [a for a in args if a != "--ascii"]
        theme.force_ascii_fallback(True)
    else:
        theme.detect_ascii_fallback()

    if not args:
        return _run_menu()

    # Suite-level flags handled before any tool dispatch.
    if args[0] in ("--help", "-h"):
        sys.stdout.write(SUITE_HELP)
        return 0
    if args[0] in ("--version", "-V"):
        sys.stdout.write(f"babel {_read_version()}\n")
        return 0

    # `--make-invite` shortcut, documented all over VOID's predecessor
    # README.  Treat as `babel void --make-invite`.
    if args[0] == "--make-invite":
        return _run_void(args)

    # `babel --setup` aggregator.
    if args[0] == "--setup":
        return _run_setup()

    head = args[0]
    if head in KNOWN_TOOLS:
        tail = args[1:]
        if head == "void":
            return _run_void(tail)
        if head == "strip":
            return _run_strip(tail)
        if head == "carrier":
            return _run_carrier(tail)
        if head == "mask":
            return _run_mask(tail)
        if head == "mirage":
            return _run_mirage(tail)

    # Unknown subcommand or flag.  Print the suite help with a clear
    # error to stderr; do NOT silently dispatch to VOID -- that hid
    # typos and bound `babel --help` to VOID's argparse instead of
    # the suite (pre-1.0 bug, fixed here).
    sys.stderr.write(
        f"babel: unknown argument {head!r}.  Run `babel --help` "
        f"for the suite usage.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
