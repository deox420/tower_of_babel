# HACKING

Working notes for contributors: how the suite hangs together, where
the load-bearing primitives live, and which external sources we have
(or have not) adopted along the way.

The canonical map of the codebase is in `MASTER.md` at repo root.
This file complements that with the things a new contributor needs
to know that do not fit the master blueprint: phase-by-phase
dependency log, decision-log pointers, the local development loop,
and the rules for proposing changes.

---

## A note on `pentest/`

`pentest/` is in `.gitignore` -- the adversarial harnesses live
locally, are run before merge, and never get pushed.  The Phase 7
suite (44 tests at the time of writing) lives at
`pentest/babel/test_*.py` + `pentest/babel/_helpers.py`.  It is
pure-Python (no Textual imports) and runs via `pytest pentest/`
from repo root.  The root `conftest.py` scrubs any sibling
editable install of the suite off `sys.path` so tests always
exercise the source tree.

Test files are pinned in this developer's notes (HACKING.md, where
you are reading this) so the next contributor knows what shape to
recreate when they clone fresh.

## Local development loop

1. Install with the appropriate `install.sh` / `install.ps1` /
   `install-termux.sh` for your platform. The installer drops a
   `babel` script on PATH and configures Tor where needed.
2. Run `babel --setup` to confirm Tor / mlock / xeddsa diagnostics
   pass on your box.
3. `babel` opens the suite menu; `babel <tool>` jumps into a tool;
   `babel <tool> --help` shows the per-tool CLI.
4. Tests live in `pentest/`. Run with `pytest pentest/` from repo
   root. The suite is structured so `pentest/<tool>/` covers each
   tool's threat-model assertions and `pentest/babel/` covers the
   suite-level chrome and multiplex contract.

The reproducible build runs through `Dockerfile.build`. See
`MASTER.md` Section 8.2 for the pinned toolchain.

---

## External dependencies adopted

This section records each phase's `/find-skills` (or
`npx skills find`) discovery pass per MASTER.md Section 11.2.
Recorded outcomes -- whether a skill was adopted or not -- protect
the suite against silently absorbing supply-chain risk.

### External dependencies adopted (Phase 7)

Phase 7 is the navigation / multi-instance UX pass. Searches:

- `npx skills find "textual screen stack multi instance"` -- top
  hit `johnlarkin1/claude-code-extensions@textual` at 161 installs;
  the rest below 100. None at the >=1K-installs / official-source
  bar from MASTER.md 11.2. Built inline.
- `npx skills find "tui slot manager multiplex"` -- top hit
  `hyperb1iss/hyperskills@tui-design` at 724 installs; below the
  1K bar and the topic is generic TUI design, not the slot model
  we need. Built inline.
- `npx skills find "tui keyboard shortcut overlay help"` -- top
  hit `lobehub/lobehub@hotkey` at 874 installs; below the 1K bar
  and scoped to a web app's keymap, not a Textual help overlay.
  Built inline.

Net: nothing adopted in Phase 7. The chrome's multiplex shell,
overlay widgets, and paste-aware menu are written against
Textual's own primitives + `shared/` helpers; no new runtime
dependency was introduced.

### External dependencies adopted (Phase 0)

Pre-Phase-1 extraction work. Searches:

- `python refactor monorepo` -- nothing >=1K from an official
  source; the move used plain `git mv` + import-path rewrites.
- `pyinstaller reproducible build` -- no qualifying skill; the
  Dockerfile.build + pinned wheel approach inherited from VOID is
  the source of truth.
- `textual app entry point` -- no qualifying skill; the entry
  shape (`babel/__main__.py` dispatcher) is bespoke for the
  suite's CLI / TUI duality.
- `termux pkg install` -- no qualifying skill; `install-termux.sh`
  is the canonical recipe.

Net: nothing adopted in Phase 0.

---

## Submitting changes

- One sprint = one phase from MASTER.md Section 10. Do not pile
  phases in a single PR.
- Every change passes the existing pentest suite. New behaviour
  requires a new pentest case; "I tested it locally" is not a
  substitute.
- Every change touching the chrome (`babel/shell.py`,
  `babel/menu.py`, `babel/views.py`) is re-verified at 60x20
  before merge. The Termux floor is non-negotiable (MASTER.md
  3.5).
- Reproducible-build regressions block release. A change that
  alters `SHA256SUMS` between two consecutive `make build-docker`
  runs on the same source MUST be diagnosed before merge.
- Decisions taken via FORGE (MASTER.md 11.3) get a one-line entry
  in `docs/ARCHITECTURE.md` "Decision log". Threat-model passes
  go into the affected tool's `docs/tools/<NAME>.md` "What this
  does NOT protect" section.

---

## Where the seams are

| Concern | Owner |
|---|---|
| Outer frame, footer, slot bar | `babel/shell.py` |
| Main menu, paste-routing | `babel/menu.py` |
| In-chrome tool surfaces | `babel/views.py` + `tools/<name>/app.py` (`*View`) |
| Help / slot-switcher overlays | `shared/ui/overlay.py` (renderers) + `babel/shell.py` (wiring) |
| Cross-tool primitives (crypto, Tor, UI) | `shared/` |
| Wire formats (`void://`, `mask://`, `carrier://`) | `shared/link/invite.py` |
| Per-tool legacy CLI | `tools/<name>/cli.py` + `tools/<name>/app.py` (`*App`) |

The `*View` classes are mounted in the chrome's content slot. The
`*App` wrappers exist only so `babel <tool>` (the legacy CLI entry
point) continues to launch a standalone Textual app. The menu
path never goes through `*App`.
