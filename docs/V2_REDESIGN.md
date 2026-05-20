# Tower of Babel v2.0.0 — Monolithic App Redesign

**Status:** design + Phase 1/2/3/4 implementation done. Awaiting on-device smoke test + review. See §8 for what's in / what's deferred.

> **Note on prior art.** When this doc was drafted, the redesign was
> framed as "starting from scratch." A closer read of `babel/shell.py`
> and `babel/views.py` shows the monolithic shell **mostly already
> exists** in v1.0: `ChromeApp` is the `BabelApp` from §4.1,
> `ServiceRegistry` (`babel/shell.py:97`) matches §4.3 almost
> exactly, `ToolHomeView` (`babel/views.py:42`) plays the role of
> `ToolScreen` from §4.2, and `MainMenuView` is the menu screen.
> Phase 1 is therefore much smaller than originally estimated: the
> only genuinely new module is `babel/vault.py` (§4.4). Phase 2 still
> needs to do the heavy lifting — replacing each tool's standalone
> `<Tool>App(App)` with in-chrome interactive screens.
>
> Where this doc refers to `BabelApp` or `ToolScreen`, those names
> map onto the existing `ChromeApp` and `ToolHomeView` classes.
> They were not renamed in Phase 1 to avoid breaking imports across
> the codebase for cosmetic reasons.

This document specifies the v2.0.0 redesign of the suite navigation:
a single monolithic Textual app (`BabelApp`) where each tool is a
`Screen` (or a stack of screens for tools that have natural multi-step
flows like VOID). The legacy CLI surface (top-level `void`/`mask`/etc.
and `babel <tool> <subcommand>`) is removed; the only retained
scripting hook is `babel --exec <tool> <op> [args...]`.

This is a **breaking change** and ships as v2.0.0.

---

## 1. Goals

1. **Unified app**: one Textual app, one event loop, one process. Tools
   are screens inside it, not standalone subprocesses.
2. **Cross-platform parity**: Termux (Android), Windows, macOS — all
   first-class. Inherited from Textual; per-platform smoke tests gate
   each phase.
3. **Long-running services keep state**: VOID and MIRAGE survive
   navigating away. `Alt+N` foregrounds the n-th active service.
4. **Cross-tool state sharing**: a `Vault` holds identities,
   capsules, and other small artifacts that one tool produces and
   another consumes (e.g. MASK identity → VOID join).
5. **Scripting**: `babel --exec <tool> <op> [args...]` for shell
   pipelines and batch use. No interactive UI; one-shot, exits with
   tool's status code.
6. **No legacy surface**: top-level aliases and per-tool subcommands
   are deleted. `babel` is the only entry point.

## 2. Non-goals (for v2.0.0)

- Promoting MASK/STRIP/CARRIER to multi-screen apps. They stay
  single-screen because their workflows are honestly single-screen.
- Web UI or remote UI.
- Plugin/extension system.
- New crypto primitives (this is a navigation refactor only).

---

## 3. Wireframes

ASCII renderings of the major screens at 80×24. Real implementation
uses Textual widgets; these are layout sketches.

### 3.1 Main menu (boot screen)

```
┌─[ tower of babel — confusion of tongues, by design ]─────────────────────────┐
│                                                                              │
│   ████████ ██████  ██     ██ ████████ ██████                                 │
│     ██    ██    ██ ██     ██ ██       ██    ██                               │
│     ██    ██    ██ ██  █  ██ ██████   ██████                                 │
│     ██     ██████   █████   ██████   ██    ██                                │
│                                                                              │
│   [1] VOID      ephemeral terminal messenger over Tor      ◉ service          │
│   [2] MASK      generate a disposable identity bundle      ▸ action           │
│   [3] STRIP     scrub metadata + steganographic markers    ▸ action           │
│   [4] CARRIER   embed / extract steganographic payloads    ▸ action           │
│   [5] MIRAGE    cover-traffic engine (decoy network noise) ◉ service          │
│                                                                              │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Active services: (none)                                          v2.0.0 babel │
│ [1-5] enter tool   [F1] help   [Q] quit                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

Key binding `[N]` (1..5) calls `app.push_screen(<ToolHomeScreen>())`.
Selecting an item never exits the app. `[Q]` triggers a graceful
purge_local + exit prompt.

### 3.2 Tool screen — ACTION tool (MASK)

```
┌─[ MASK — disposable identity bundle ]────────────────── back: Esc ───────────┐
│                                                                              │
│  Locale   [ es_AR ▾ ]      Profile  [ alpine-hiker ▾ ]                       │
│  Use Tor  [ x ]            Mail     [ x ]                                    │
│                                                                              │
│  ┌─ bundle ──────────────────────────────────────────────────────────────┐   │
│  │ Name:    Lautaro Méndez                                               │   │
│  │ Born:    1987-04-12  · Bariloche, AR                                  │   │
│  │ Email:   lautaro.mendez+9f3a@protonmail.com  (Tor inbox)              │   │
│  │ Phone:   (sim only — see SECURITY.md before use)                      │   │
│  │ Fingerprint (Ed25519): ed25519:F7Z2…JK9P                              │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Active services: (none)                                          v2.0.0 babel │
│ [R] re-roll   [S] save to vault   [C] copy fingerprint   [X] export   [Esc]   │
└──────────────────────────────────────────────────────────────────────────────┘
```

`[S] save to vault` calls `app.vault.put(IdentityArtifact(...))`. The
artifact becomes selectable in VOID's join screen and in CARRIER's
"sign payload" screen. `Esc` calls `app.pop_screen()` → back to menu.

### 3.3 Tool screen — SERVICE tool (VOID lobby)

VOID is the multi-screen case. Lobby → Connecting → Chat.

```
┌─[ VOID — ephemeral terminal messenger ]────────────────── back: Esc ─────────┐
│                                                                              │
│  Invite URL  [ void://7bxq4...@server.onion:443/ar3-xelf3a              ]    │
│   ─ or ─                                                                     │
│  Host new   [ ⏵ create void:// link ]                                        │
│                                                                              │
│  Identity   [ alpine-hiker (es_AR) — F7Z2…JK9P  ▾ ]   ← from Vault            │
│              [ + new disposable (generate now)      ]                         │
│              [ + paste fingerprint                  ]                         │
│                                                                              │
│  Cover traffic [ x ]   Clearnet fallback [ ]                                 │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Active services: (none)                                          v2.0.0 babel │
│ [Enter] join   [H] host   [Esc] back                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

The identity dropdown is populated by `app.vault.list(kind=IdentityArtifact)`.

After Enter:

```
┌─[ VOID — connecting ]────────────────────────────────────────────────────────┐
│                                                                              │
│      [✓] Tor circuit established                                             │
│      [✓] Server reachable (server.onion:443)                                 │
│      [✓] X3DH key exchange complete                                          │
│      [⏳] Joining room…                                                       │
│                                                                              │
│                                                                              │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Active services: VOID(connecting)                                v2.0.0 babel │
│ [Esc] cancel                                                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

Then Chat:

```
┌─[ VOID — ar3-xelf3a · 3 peers ]──────── peers: F7…P, Q1…M, R9…X ─────────────┐
│ 23:14 < alpine-hiker > listo che, llegamos                                   │
│ 23:14 < Q1…M       > dale, ya estoy entrando                                 │
│ 23:15 < R9…X       > ok, 2 min                                               │
│ 23:15 * R9…X is typing…                                                      │
│                                                                              │
│                                                                              │
│                                                                              │
│ > _                                                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ Active services: VOID(ar3-xelf3a, 3 peers)                       v2.0.0 babel │
│ [Enter] send   [Ctrl+L] leave   [Alt+M] star map   [Alt+0] background         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Background mode — Alt+0 from inside a service

User presses `Alt+0` while in VOID Chat. Service goes to background,
keeps WebSocket + ratchet alive, returns to menu:

```
┌─[ tower of babel — confusion of tongues, by design ]─────────────────────────┐
│                                                                              │
│   [1] VOID      …                                          ◉ service ●●●     │
│   [2] MASK      …                                          ▸ action           │
│   …                                                                          │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Active services: [1] VOID(ar3-xelf3a, 3 peers, 12 unread)        v2.0.0 babel │
│ [1-5] enter tool   [Alt+1] resume VOID   [F1] help   [Q] quit                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

`[1]` (when no service exists) enters the tool home view fresh.
`[Alt+1]` resumes the active VOID session. The dot row `●●●` next to
VOID in the menu indicates it has a live session.

### 3.5 Vault picker — CARRIER signing with a Vault identity

```
┌─[ CARRIER — embed ]──────────────────────────── back: Esc ───────────────────┐
│  Cover image  [ ~/photos/IMG_1234.jpg                             ▾ ]        │
│  Payload      [ ~/secret.txt                                      ▾ ]        │
│  Sign with    [ <pick from vault>                                 ▾ ]        │
│                ┌────────────────────────────────────────────────┐            │
│                │  Identity from Vault                           │            │
│                ├────────────────────────────────────────────────┤            │
│                │ ◉ alpine-hiker (es_AR)   F7Z2…JK9P   12 min    │            │
│                │   silver-fox  (en_US)    A0K3…M2X1   2 h       │            │
│                │   ─                                            │            │
│                │   ✕ none (unsigned)                            │            │
│                └────────────────────────────────────────────────┘            │
│  Passphrase   [ ●●●●●●●●●●●●●●                                      ]        │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Active services: [1] VOID(ar3-xelf3a, 3 peers)                   v2.0.0 babel │
│ [Enter] embed   [Esc] back                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. API contracts

### 4.1 `BabelApp(App)`

```python
class BabelApp(App):
    """Top-level Textual app — the only `App` instance in the suite."""

    CSS_PATH = "babel.tcss"
    BINDINGS = [
        Binding("ctrl+c", "request_quit", "quit", priority=True),
        Binding("f1", "help", "help"),
        Binding("alt+0", "background_current", show=False),
        # Alt+1..Alt+5 resume the Nth active service (see ServiceRegistry).
        *(Binding(f"alt+{n}", f"resume_service({n})", show=False)
          for n in range(1, 6)),
    ]

    # ---- public surface used by screens ----
    services: ServiceRegistry  # active long-running tools
    vault:    Vault            # cross-tool artifacts (identities, capsules)

    def on_mount(self) -> None: ...
    def push_tool(self, tool: str) -> None: ...      # menu calls this
    def action_background_current(self) -> None: ...  # Alt+0 hook
    def action_resume_service(self, slot: int) -> None: ...
```

Single instance. Owns the event loop. Mediates between screens
through `services` and `vault` only — no direct screen→screen handles.

### 4.2 `ToolScreen(Screen)` — base contract

```python
class ToolScreen(Screen):
    """Base for the *home* screen of any tool. Tools with multi-step
    flows (VOID) push deeper screens from here."""

    tool_name: ClassVar[str]            # "void", "mask", ...
    flavour:   ClassVar[Literal["ACTION", "SERVICE"]]

    # Footer / status contributions, rendered by the chrome.
    def status_line(self) -> RenderableType: ...
    def footer_contribution(self) -> str: ...

    # Called when the user quits the app or the screen is forcibly
    # dismissed (e.g. low-memory). Zeroize key material, close fds.
    async def purge_local(self) -> None: ...

    # Optional: if the tool is a SERVICE, this is called when the
    # screen is backgrounded. Tool keeps state, just hides its UI.
    async def on_backgrounded(self) -> None: ...
    async def on_foregrounded(self) -> None: ...
```

Tools place their home screen at `tools/<tool>/screens/home.py`,
exposing a `<Tool>HomeScreen` class. Deeper screens (`tools/void/screens/chat.py`)
push onto the stack but are NOT `ToolScreen` subclasses — they are
plain `Screen` subclasses pushed by their parent.

### 4.3 `ServiceRegistry`

```python
@dataclass(slots=True)
class ServiceSlot:
    slot: int                          # 1..5, stable for the session
    tool_name: str
    screen: ToolScreen                 # the foreground screen, when active
    title: str                         # short label for the status bar
    started_at: float
    state: Literal["foreground", "background"]

class ServiceRegistry:
    """Tracks long-running SERVICE tools across screen pushes/pops."""

    def register(self, screen: ToolScreen, title: str) -> ServiceSlot: ...
    def list_active(self) -> list[ServiceSlot]: ...
    def background(self, slot: int) -> None: ...
    def foreground(self, slot: int) -> ToolScreen: ...
    def shutdown(self, slot: int) -> None: ...   # called by tool when session ends
    async def shutdown_all(self) -> None: ...    # called on app quit
```

Constraints:

- At most one slot per tool (you can't have two VOIDs).
- Slot numbers map to `Alt+1..Alt+5` for fast resume.
- A registered service's screen is NOT popped when the user navigates
  away; it's hidden. The chrome holds a strong ref so GC doesn't drop it.

### 4.4 `Vault`

```python
class ArtifactKind(StrEnum):
    IDENTITY = "identity"      # MASK output
    CAPSULE  = "capsule"       # CARRIER stego container metadata
    INVITE   = "invite"        # VOID void:// link, for sharing across screens

@dataclass(slots=True, frozen=True)
class Artifact:
    kind: ArtifactKind
    label: str                 # user-visible name ("alpine-hiker")
    fingerprint: str           # short id ("F7Z2…JK9P")
    payload: bytes             # serialized, zeroizable
    created_at: float
    expires_at: float | None   # for ephemeral artifacts

class Vault:
    """In-memory only. Never touches disk. Cleared on app quit."""

    def put(self, artifact: Artifact) -> None: ...
    def list(self, kind: ArtifactKind | None = None) -> list[Artifact]: ...
    def get(self, fingerprint: str) -> Artifact | None: ...
    def drop(self, fingerprint: str) -> None: ...
    async def purge_all(self) -> None: ...   # zeroize all payloads
```

Constraints:

- **Memory only.** No persistence between app runs. If the user wants
  to keep an identity, they `[X] export` from the MASK screen.
- Payloads are bytes (serialized); each tool owns its own
  serializer. Vault is dumb storage.
- On app quit, `purge_all()` overwrites every payload buffer with
  zeros before releasing.

### 4.5 `babel --exec <tool> <op> [args...]`

```
babel --exec mask new --locale es_AR --profile alpine-hiker
babel --exec strip embed cover.jpg payload.txt -o out.jpg --aggressive
babel --exec strip extract out.jpg -o recovered.bin
babel --exec void --make-invite                         # one-shot, prints void://
babel --exec carrier capacity cover.jpg
babel --exec mirage start --profile lurking-laptop --duration 10m
```

Implementation: `babel/__main__.py` checks `--exec`. If present,
dispatches to `babel.exec.dispatch(tool, op, args)` which calls each
tool's `tools/<tool>/exec.py:run(op, args) -> int`. Each tool exposes
a small subset of operations (the same ones that used to be argparse
subcommands), but the entry point is centralized and the alias
aliases (`void`, `mask`, ...) do NOT exist as separate scripts.

Exit code: tool's status. Stdout: tool's output (machine-friendly when
practical). Stderr: errors. No Textual app boots.

---

## 5. Module layout (after redesign)

```
babel/
    __main__.py          # ~80 lines; parses --exec / launches BabelApp
    app.py               # BabelApp class (replaces shell.py's ChromeApp)
    services.py          # ServiceRegistry
    vault.py             # Vault, Artifact, ArtifactKind
    screens/
        menu.py          # MainMenuScreen
        help.py          # HelpScreen
    theme.py             # unchanged
    art.py               # unchanged
    babel.tcss           # global stylesheet

tools/
    <tool>/
        screens/
            home.py      # <Tool>HomeScreen (the entry screen)
            …            # any deeper screens (VOID has lobby/chat/etc.)
        exec.py          # run(op, args) -> int  ← for `babel --exec`
        core/            # tool logic (unchanged from v1, mostly)
        tests/

shared/                  # unchanged

docs/
    V2_REDESIGN.md       # this file
    ARCHITECTURE.md      # updated in Phase 4
    USAGE.md             # rewritten in Phase 4
```

Deleted in Phase 3:
- `babel/menu.py`         → merged into `babel/screens/menu.py`
- `babel/shell.py`        → split into `app.py` + `services.py`
- `babel/views.py`        → tool home views replaced by `<Tool>HomeScreen`
- `tools/<tool>/cli.py`   → argparse parsers + `_cmd_*` + `_run_interactive`
- `tools/<tool>/app.py`   → standalone `<Tool>App` wrapper
- `tools/void/client/app.py:VoidApp`  → only the App wrapper; screens stay

---

## 6. Cross-platform notes

| Concern | Termux | Windows | macOS | Strategy |
|---|---|---|---|---|
| Alt-modifier bindings | flaky in some terminals | `Alt` = `Esc` prefix in cmd.exe; works in Windows Terminal | OK | use `Binding("alt+N", ...)` (Textual normalizes); fall back to `Ctrl+N` if a smoke test fails on a target terminal |
| File pickers | tiny screen | path separator `\` | OK | `pathlib.Path`; let user paste or type; provide arrow-key picker; no native file dialog |
| Tor | `pkg install tor`, uses `$PREFIX/etc/tor` | `tor.exe` via install.ps1, %APPDATA% | `brew install tor` | `install.{sh,ps1}` already handle this; no change in v2 |
| Backgrounding (Alt+0) | Termux suspends app when terminal loses focus — services may stall | Windows Terminal stays alive | OK | document termux quirk in CHANGELOG; recommend `pkg install termux-services` for users who want VOID to keep running |
| Color / emoji | full support in Termux:Style | depends on terminal; Windows Terminal yes, cmd.exe no | OK | Textual auto-detects; provide `BABEL_NO_EMOJI=1` env var for ASCII fallback |
| Keyboard quirks | hardware keyboards rare on Termux; many users use Hacker's Keyboard | Ctrl+C used to copy in some terminals | OK | always offer a no-modifier alternative (`Q` quits in addition to `Ctrl+C`) |

**Smoke test matrix** per phase:

- Linux (Ubuntu 22.04, xterm)         — primary dev
- Termux (latest, Hacker's Keyboard)  — Phase 1, 2 (per tool), 3, 4
- Windows 11 (Windows Terminal)       — Phase 1, 2 (VOID + MIRAGE), 4
- macOS (iTerm2)                      — Phase 1, 2 (VOID), 4

Smoke test = launch `babel`, navigate to each tool, do one primary
action, background it if SERVICE, return, quit cleanly. Document
findings in the PR.

---

## 7. Migration strategy by tool

### 7.1 MASK (Phase 2, day 1-2)

- `MaskApp` → delete.
- `MaskView(Container)` → port into `MaskHomeScreen(ToolScreen)`.
- Subcommands `new`/`decode`/`import` → `tools/mask/exec.py:run`.
- New: `[S] save to vault` button calls `app.vault.put(IdentityArtifact)`.
- Tests: unit tests on `core/` keep working; `tools/mask/tests/test_cli.py` is rewritten as `test_exec.py`.

### 7.2 STRIP (Phase 2, day 3-4)

- `StripApp` → delete.
- `StripView(Container)` → `StripHomeScreen(ToolScreen)`.
- Subcommands `embed`/`extract`/`capacity`/`inspect` → `tools/strip/exec.py:run`. Note: STRIP doesn't HAVE multi-screen needs; its single screen + flag toggles stay.
- No Vault interaction.

### 7.3 CARRIER (Phase 2, day 5-6)

- `CarrierApp` → delete.
- `CarrierView(Container)` → `CarrierHomeScreen(ToolScreen)`. Mode switcher `[e]/[x]/[c]/[i]` is preserved within the single screen.
- Subcommands → `tools/carrier/exec.py:run`.
- New: "sign with" identity picker pulls from Vault (see §3.5).

### 7.4 MIRAGE (Phase 2, day 7-8)

- `MirageApp` → delete.
- `MirageView(Container)` → `MirageHomeScreen(ToolScreen, flavour="SERVICE")`.
- Engine async task already runs on the Textual worker pool; that's reused on the new app's worker pool.
- New: registers with `ServiceRegistry` when engine starts; deregisters on stop. Backgrounding keeps engine running.
- Subcommands → `tools/mirage/exec.py:run`.

### 7.5 VOID (Phase 2, day 9-12) — biggest

- `VoidApp(App)` → delete. Its screens move into `tools/void/screens/`.
- App-level state (`identity`, `net`, `peer_sessions`, `_cover`) → `VoidSession` dataclass owned by `VoidHomeScreen` (or registered as a "ghost slot" object in the registry that survives screen disposal).
- `LobbyScreen`/`ConnectingScreen`/`ChatScreen`/`StarMapScreen` stay as is; they're pushed by `VoidHomeScreen` rather than `VoidApp`.
- New: Lobby's "identity" field pulls from `Vault` (see §3.3). User can pick a MASK identity or generate fresh.
- New: `Alt+0` backgrounds the chat. WebSocket reader keeps running on `BabelApp`'s worker pool. `Alt+N` brings it back.
- Subcommand `--make-invite` → `tools/void/exec.py:run("make_invite", args)`.

---

## 8. Phases recap

1. **Phase 1** — `babel/vault.py` (`Vault`, `Artifact`, `ArtifactKind`),
   wired into `ChromeApp.__init__` and `action_purge_quit`. 18 stdlib
   `unittest` cases. The shell, registry, ToolHomeView base, and main
   menu were already in place from v1. **Status: ✓ done.**

2. **Phase 2** — tool migrations. MASK / STRIP / CARRIER / MIRAGE's
   `<Tool>View(Container)` widget trees were lifted into
   `<Tool>View(ToolHomeView)` in their existing `tools/<tool>/app.py`
   files; the standalone `<Tool>App(App)` wrappers are deleted; CLI
   `_run_interactive` fallbacks now print a redirect rather than
   launching a TUI. MASK additionally got `[s] save to vault` so
   identities flow into the cross-tool Vault. VOID's full migration
   is deferred to v2.1.0 (the screens are `textual.Screen` subclasses
   that would each need to become Containers; see §7.5). Transitional
   behaviour: `[Enter]` on VoidHomeView exits the suite app with
   `return_value=("launch_void", argv)` and `babel.__main__` re-execs
   VOID standalone, returning to the menu on exit. **Status: ✓ done
   for MASK/STRIP/CARRIER/MIRAGE; VOID transitional.**

3. **Phase 3** — `babel --exec <tool> [args...]` dispatch table in
   `babel/__main__.py`. Legacy top-level aliases (`void`, `mask`,
   `strip`, `carrier`, `mirage`) removed from `[project.scripts]` in
   `pyproject.toml`. `babel <tool>` and `babel <tool> <op>` now print
   a usage-error redirect. **Status: ✓ done.**

4. **Phase 4** — `VERSION` and `pyproject.toml` bumped to `2.0.0`.
   `CHANGELOG.md` has the v2.0.0 stanza with breaking-change list,
   additions, and known deviations. `README.md` "Use" section
   rewritten to point at `babel` + `--exec`. Install scripts left as
   is (they install via pip, which picks up the new `[project.scripts]`
   without changes). USAGE.md / ARCHITECTURE.md updates left for a
   follow-up release polish PR — the README + CHANGELOG already cover
   the user-facing changes. **Status: ✓ done for the v2.0.0 cut.**

### Smoke tests run

- `python -m unittest tests.test_vault -v` → 18/18 pass
- `python -m babel --version` → `babel 2.0.0`
- `python -m babel --help` → new help text (no legacy aliases)
- `python -m babel mask new` → expected v2 redirect error (exit 2)
- `python -m babel --exec mask --help` → forwards to mask argparse
- `python -m babel --exec` → lists valid choices, exits 2
- `python -m babel --exec bogus_tool` → lists valid choices, exits 2
- `view_class_for("<tool>")` resolves to the migrated view for
  mask/strip/carrier/mirage and to the transitional info card for void

UI smoke (chrome rendering, key bindings, identity flow MASK → Vault)
needs a real terminal — the dev container is headless. The user is
asked to run `babel` on Linux + Termux + Windows + macOS and confirm
the menu navigation matches the wireframes in §3.

---

## 9. Open questions (not blockers for Phase 1)

- **Persistence opt-in for Vault.** Currently spec'd as in-memory only. Should there be an explicit "keep identity on disk under a passphrase" flow? Out of scope for v2.0.0, but worth listing in CHANGELOG as future work.
- **Multiple VOID sessions.** Spec says one slot per tool. If a user wants two simultaneous VOID rooms, that's a v2.x feature.
- **`babel --exec` argument grammar.** Above sketch uses `--exec <tool> <op>`. Alternative: `babel exec <tool> <op>` (positional). The flag form keeps `--exec` reserved and avoids colliding with `<tool>` as a positional. Will lock down before Phase 3.
