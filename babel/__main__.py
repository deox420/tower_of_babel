"""``babel`` entry point — v2.0.0.

Argv shapes (docs/V2_REDESIGN.md §4.5):

    babel                              -> open the suite menu
    babel --help                       -> suite-level help
    babel --version                    -> print VERSION and exit
    babel --setup                      -> aggregated diagnostic
    babel --ascii                      -> force Tier-1 ASCII chrome
    babel --exec <tool> [args...]      -> one-shot scripting (no chrome)

The legacy ``babel <tool>`` and per-tool aliases (``void``, ``mask``,
``strip``, ``carrier``, ``mirage``) are removed in v2.0.0. All five
tools are reached through the menu; their scripted operations live
behind ``--exec``.

VOID's full in-chrome migration is deferred to v2.1.0 — when the
user picks VOID from the menu and presses ``[Enter]``, the suite
app exits with ``return_value=("launch_void", argv)`` so this entry
point can re-exec VOID's standalone client and then come back to
the menu when VOID exits.
"""
from __future__ import annotations

import os
import sys
from typing import Callable, Sequence

KNOWN_TOOLS = {"void", "mask", "strip", "carrier", "mirage"}


SUITE_HELP = """\
babel -- Tower of Babel suite launcher (v2.0.0)

usage:
  babel                              open the suite menu
  babel --exec <tool> <args>         one-shot scripting (no chrome)
  babel --setup                      aggregated diagnostic across every tool
  babel --version                    print the suite version
  babel --ascii                      force Tier-1 ASCII chrome (small terminals)

interactive tools (reached through the menu):
  [1] VOID      ephemeral encrypted messenger over Tor
  [2] MASK      disposable identity generator
  [3] STRIP     metadata laundry
  [4] CARRIER   steganography (PNG / WAV)
  [5] MIRAGE    cover traffic generator

scripting (--exec):
  babel --exec mask new --locale es_AR --profile alpine-hiker
  babel --exec strip ~/photo.jpg
  babel --exec carrier embed cover.png secret.txt
  babel --exec mirage start --profile office_worker
  babel --exec void --make-invite

See README.md, RELEASE_NOTES.md, docs/V2_REDESIGN.md, and
docs/tools/<NAME>.md for detail.
"""


def _read_version() -> str:
    """Read VERSION sitting next to the repo root. Falls back gracefully."""
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


# ---------------------------------------------------------------------------
# `--exec` dispatch
# ---------------------------------------------------------------------------


def _exec_void(args: Sequence[str]) -> int:
    """Run VOID's standalone client one-shot.

    Pre-v2 this was the default `babel void` path. In v2 it's
    accessible only via `--exec` for scripted use (e.g. printing a
    void:// invite from a shell pipeline). Interactive VOID still
    lives behind the menu's `[1]` entry which re-launches the same
    client (see ``VoidHomeView.action_launch``).
    """
    from tools.void.client.app import main as void_main
    sys.argv = ["void"] + list(args)
    void_main()
    return 0


def _exec_strip(args: Sequence[str]) -> int:
    from tools.strip.cli import main as strip_main
    return strip_main(list(args))


def _exec_carrier(args: Sequence[str]) -> int:
    from tools.carrier.cli import main as carrier_main
    return carrier_main(list(args))


def _exec_mask(args: Sequence[str]) -> int:
    from tools.mask.cli import main as mask_main
    return mask_main(list(args))


def _exec_mirage(args: Sequence[str]) -> int:
    from tools.mirage.cli import main as mirage_main
    return mirage_main(list(args))


_EXEC_TABLE: dict[str, Callable[[Sequence[str]], int]] = {
    "void":    _exec_void,
    "strip":   _exec_strip,
    "carrier": _exec_carrier,
    "mask":    _exec_mask,
    "mirage":  _exec_mirage,
}


def _run_exec(args: Sequence[str]) -> int:
    """Dispatch ``babel --exec <tool> [args...]``."""
    if not args:
        sys.stderr.write(
            "babel --exec: missing tool name. "
            f"Choices: {', '.join(sorted(_EXEC_TABLE))}.\n"
        )
        return 2
    tool, *tail = args
    handler = _EXEC_TABLE.get(tool)
    if handler is None:
        sys.stderr.write(
            f"babel --exec: unknown tool {tool!r}. "
            f"Choices: {', '.join(sorted(_EXEC_TABLE))}.\n"
        )
        return 2
    return handler(tail)


# ---------------------------------------------------------------------------
# Menu (with VOID launch hand-off)
# ---------------------------------------------------------------------------


def _run_menu() -> int:
    """Launch the suite app. Handle VOID's transitional launch hand-off.

    Today MASK / STRIP / CARRIER / MIRAGE live fully in the chrome.
    VOID still has its own ``VoidApp`` with screens that haven't been
    ported into the chrome's content slot yet (v2.1.0 work). When the
    user presses ``[Enter]`` on VOID's home view, ``ChromeApp`` exits
    with ``return_value=("launch_void", argv)``; we run VOID
    standalone with those argv and then re-launch the menu.
    """
    from babel.menu import MainMenuView
    from babel.shell import ChromeApp

    version = _read_version()
    while True:
        app = ChromeApp(initial_view=MainMenuView(), version=version)
        app.run()
        result = getattr(app, "return_value", None)
        if isinstance(result, tuple) and len(result) >= 1 and result[0] == "launch_void":
            argv = list(result[1]) if len(result) > 1 and result[1] else []
            try:
                _exec_void(argv)
            except SystemExit:
                # void_main() may raise SystemExit; consume it so we
                # come back to the menu rather than aborting babel.
                pass
            continue
        return 0


def _run_setup() -> int:
    """Aggregate every tool's ``setup_check.run()``."""
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
        if isinstance(result, tuple) and len(result) == 2:
            code, lines = result
            for line in lines:
                sys.stdout.write(line + "\n")
        else:
            code = int(result)
        worst = max(worst, code)
    return worst


# ---------------------------------------------------------------------------
# Top-level argv parser
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = list(argv)

    # ``--ascii`` is a global modifier; consume it before dispatch so
    # tools never see it.
    from babel import theme
    if "--ascii" in args:
        args = [a for a in args if a != "--ascii"]
        theme.force_ascii_fallback(True)
    else:
        theme.detect_ascii_fallback()

    if not args:
        return _run_menu()

    if args[0] in ("--help", "-h"):
        sys.stdout.write(SUITE_HELP)
        return 0
    if args[0] in ("--version", "-V"):
        sys.stdout.write(f"babel {_read_version()}\n")
        return 0
    if args[0] == "--setup":
        return _run_setup()
    if args[0] == "--exec":
        return _run_exec(args[1:])

    # Legacy `babel <tool>` and `babel <tool> <op>` dispatch is gone in
    # v2.0.0. Tell the user where it went.
    head = args[0]
    if head in KNOWN_TOOLS:
        sys.stderr.write(
            f"babel: `babel {head} ...` was removed in v2.0.0.\n"
            f"       Interactive: run `babel` and pick {head.upper()} from the menu.\n"
            f"       Scripting:   run `babel --exec {head} ...`.\n"
        )
        return 2

    sys.stderr.write(
        f"babel: unknown argument {head!r}. Run `babel --help` for "
        f"the suite usage.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
