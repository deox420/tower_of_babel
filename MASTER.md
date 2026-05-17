# TOWER OF BABEL — master blueprint
```
       ████████╗ ██████╗  ██╗    ██╗ ███████╗ ██████╗
       ╚══██╔══╝██╔═══██╗ ██║    ██║ ██╔════╝ ██╔══██╗
          ██║   ██║   ██║ ██║ █╗ ██║ █████╗   ██████╔╝
          ██║   ██║   ██║ ██║███╗██║ ██╔══╝   ██╔══██╗
          ██║   ╚██████╔╝ ╚███╔███╔╝ ███████╗ ██║  ██║
          ╚═╝    ╚═════╝   ╚══╝╚══╝  ╚══════╝ ╚═╝  ╚═╝
                ██████╗   █████╗  ██████╗  ███████╗ ██╗
                ██╔══██╗ ██╔══██╗ ██╔══██╗ ██╔════╝ ██║
                ██████╔╝ ███████║ ██████╔╝ █████╗   ██║
                ██╔══██╗ ██╔══██║ ██╔══██╗ ██╔══╝   ██║
                ██████╔╝ ██║  ██║ ██████╔╝ ███████╗ ███████╗
                ╚═════╝  ╚═╝  ╚═╝ ╚═════╝  ╚══════╝ ╚══════╝
              ── confusion of tongues, by design ──
```
This file is **the development bible** for the Tower of Babel suite.
Read it before writing a line of code in any tool that lives here.
The order of the sections matters: vision and aesthetics come before
architecture, architecture comes before per-tool specs, and the AI
generator prompt comes at the end because it presupposes everything
above.
---
## 1 - Vision
Tower of Babel is a privacy and anti-surveillance suite for the
terminal. Not a single app — a small federation of single-purpose
tools that share a shell, an aesthetic, a build system, and a moral
posture.
The **biblical metaphor** is load-bearing: the Tower of Babel is
where humanity's languages were confused so that no single power
could read everything. That is the project's thesis in one image.
Each tool inside the tower is a different "room" with a different
function, but they all share the same architecture, the same locks,
and the same view from the parapet.
The **moral posture** is the one inherited from VOID:
> "I hand you the hammer. How you use it is your business."
The tools have specific functions. They ship with honest threat
models that say what they protect and what they don't. They do not
moralize, do not gate features behind "intended use" disclaimers,
and do not log who used them for what. The 0BSD license makes this
explicit: do whatever you want, no strings.
What the suite **categorically refuses to build**:
- Tooling whose only plausible function is targeting a specific,
  identifiable individual (stalkerware, doxxing, CSAM).
- Anything that breaks the no-persistence, no-telemetry rule.
- Persuasive content that puts words in real public figures' mouths.
Everything else, including use cases the maintainers personally
disagree with, is in scope.
---
## 2 - Suite identity
| Name | Tower of Babel |
|---|---|
| Launcher command | `babel` |
| Repo | `tower_of_babel` |
| Tagline | *confusion of tongues, by design* |
| License | 0BSD |
The tagline is canonical. It appears, verbatim and italic, in:
- The main menu, below the ASCII logo, framed by `───` em-dashes.
- The first line under the title in `README.md`.
- The first panel of the first-time wizard.
- The header strip of every `docs/tools/<NAME>.md`, small and muted,
  one line above the per-tool title.
It is the project's thesis. Do not paraphrase it.
| | |
|---|---|
| Language | Python 3.11+ |
| Min platforms | Linux, macOS (x86_64 + arm64), Windows, Android (Termux F-Droid) |
| Versioning | suite-level `MAJOR.MINOR.PATCH`; tools share the suite version |
| Language | Python 3.11+ |
| Min platforms | Linux, macOS (x86_64 + arm64), Windows, Android (Termux F-Droid) |
| Versioning | suite-level `MAJOR.MINOR.PATCH`; tools share the suite version |
The current contents of the tower:
| Tool | One-line role |
|---|---|
| **VOID** | ephemeral encrypted messenger over Tor (X3DH + Double Ratchet) |
| **MASK** | disposable identity generator (alias + avatar + bio + temp mail) |
| **STRIP** | metadata laundry (EXIF, XMP, IPTC, Office, PDF) |
| **CARRIER** | steganography (hide encrypted payload in cover file) |
| **MIRAGE** | cover traffic generator (plausible network noise) |
Future rooms are welcome. Each must clear the vision in Section 1 and the
architectural rules in Section 4–Section 6 before going in.
---
## 3 - Aesthetic — the look and the rules
The look is the load-bearing part of what makes this feel like a
single suite. The rules below are non-negotiable across every tool.
### 3.1 - Continuous chrome
Every tool runs inside the same outer frame. The frame is rendered
once, on launch, and **stays visible through every screen**:
```
╔══════════════════════════════ TOWER OF BABEL ═════════════ v0.6.0 ══╗
║                                                                       ║
║                       <screen content lives here>                     ║
║                                                                       ║
╠─── TOR ● ─── MEM ● ─── CRYPTO ● ─── SWAP ○ ─── 14:32:09 UTC ───────╣
╚══════════════════════════════════════════════════════════════════════╝
```
Implementation: a Textual `App` with a top-level `Container` whose
border is owned by `babel.shell.Chrome`. Screens push and pop inside
that container; the chrome never repaints.
The top bar shows: project name, current tool ("/ VOID" once you
enter one), build version. The bottom bar shows the **same five
indicators always**:
- **TOR** — circle filled green if Tor SOCKS5 reachable, red if not
- **MEM** — green if mlock works on this platform, amber if fallback
- **CRYPTO** — green if all key material has been initialised, dim
  otherwise (nothing pending)
- **SWAP** — amber if swap is active (with mlock fallback), green
  otherwise
- **CLOCK** — UTC, monospaced, updates every second (real time
  from the system clock, not animated)
Plus the build label on the right. The indicators are **real, not
decorative**: each one corresponds to a callable that returns the
state. The footer is wired to those callables and renders whatever
they return. No fake green dots, ever.
### 3.2 - Animation policy
The word "animation" in this project means **state changes the user
can see while real work is happening**. It does not mean fake
loading sequences.
**Allowed:**
| Animation | Tied to |
|---|---|
| Progress bar with real bytes/s | bulk encrypt, embed, strip |
| Step indicator marking phases done as they finish | Tor handshake, X3DH+DR setup |
| Cursor blink in inputs | terminal default |
| Single-frame glitch on screen transition | actual screen change |
| Spinner on input field while awaiting a network reply | the actual await |
| Status footer state changes | the actual state change |
| `/burn` countdown re-rendering as the timer ticks | the actual timer |
**Forbidden:**
| Anti-pattern | Why |
|---|---|
| Decorative "hacking…" sequences | dishonest, adds latency |
| Text appearing letter-by-letter for no reason | wastes the user's time |
| Spinners that spin without anything blocking | lies about state |
| Matrix-rain on idle screens | performance + battery on mobile |
| Looping ASCII animations in headers | distracts from real content |
| Sound effects | terminals don't beep gratuitously |
If you can't point at a real operation, the animation does not ship.
### 3.3 - Palette
Inherited from VOID, consolidated for the suite:
| Token | Hex | Use |
|---|---|---|
| `--green` | `#00ff9c` | primary text, success, ready states |
| `--green-deep` | `#003a25` | inactive scanlines, dim borders |
| `--cyan` | `#6cdcff` | hints, secondary labels, selected items |
| `--amber` | `#ffd166` | warnings, pending states, "burn" indicator |
| `--red` | `#ff3860` | errors, blocked actions, clearnet warning |
| `--mute` | `#7a7a7a` | placeholders, separators, timestamps |
| `--bg` | `#000000` | background everywhere |
The only color allowed for the outer frame is `--green` at 55%
opacity. Nothing else owns that line.
### 3.4 - Glyph vocabulary
A short shared alphabet of status glyphs. Use consistently across
tools so the user learns once.
| Glyph | Meaning |
|---|---|
| `●` | active, healthy, on |
| `○` | inactive, off, not initialised |
| `◐` | pending, partial, in progress |
| `✦` | trusted (peer SAS confirmed; signed identity) |
| `⚠` | warning, soft-fail |
| `✗` | hard error, blocked |
| `↻` | rotating, regenerating |
| `▸` | input prompt |
| `·` | separator |
Compact mode (terminals <80 cols, e.g. Termux portrait) replaces
indicator labels with single letters but **keeps the same glyphs**:
`T*  M*  C*  S.  14:32` (using the ASCII fallbacks below if the
terminal can't render the Unicode set).
### 3.5 - Character and resolution compatibility
The suite is built to be **usable on Termux first** and on full
desktop terminals second. If a character or layout breaks Termux,
it doesn't ship. This section is non-negotiable.
**Minimum supported resolution: 60 columns x 20 rows.** That is
Termux portrait on a small phone with the default font size. Every
screen, including the menu, has to remain legible and operable at
that size. Anything wider is gravy.
**Tiered character set.** Three tiers, ordered by safety. Use the
narrowest tier that does the job.
- **Tier 1 (ASCII only, always safe)**: `! " # $ % & ' ( ) * + , -
  . / 0-9 : ; < = > ? @ A-Z [ \ ] ^ _ ` `` `` ` a-z { | } ~`. Every
  character that must survive on a 1980s VT100 lives here.
- **Tier 2 (CP437 / Box drawing, safe on Termux + every modern
  terminal)**: `- = | + . * o # @ ' " ` and the Unicode box-drawing
  block `U+2500..U+257F` (`- = | + + + + + + + + + + + + + +` etc.
  including `╔ ╗ ╚ ╝ ║ ═ ╠ ╣ ╦ ╩ ╬ │ ─ ┐ └ ┌ ┘ ├ ┤ ┬ ┴ ┼`).
  Heavy chrome can use these.
- **Tier 3 (status glyphs, conditional)**: `● ○ ◐ ✦ ⚠ ✗ ↻ ▸ · —`.
  Allowed only when paired with an ASCII fallback that the renderer
  swaps in automatically when `babel --setup` detects a terminal
  that can't render them.
**ASCII fallback map.** When `babel.theme.use_ascii_fallback` is
true (forced via `--ascii`, auto-detected from `$LANG`, `$TERM`,
and a width probe), the renderer substitutes:
| Tier 3 | ASCII fallback |
|---|---|
| `●` | `*` |
| `○` | `.` |
| `◐` | `o` |
| `✦` | `+` |
| `⚠` | `!` |
| `✗` | `x` |
| `↻` | `~` |
| `▸` | `>` |
| `·` | `\|` (pipe) when used as separator |
| `—` | `-` |
| `╔ ╗ ╚ ╝ ║ ═ ╠ ╣ ╦ ╩ ╬ ├ ┤` | `+ + + + \| - + + + + + + +` |
| `─` | `-` |
| `│` | `\|` |
The same map is used to draft documentation that has to print on
paper or copy-paste outside a terminal: README, RELEASE_NOTES, and
CHANGELOG are written entirely in Tier 1.
**Banned everywhere in the suite.** No matter what tier:
- `§` (section sign). Replaced by `Section N` or `## N`.
- Emoji. None. Not even one. The glyph table in 3.4 is the entire
  decorative icon set, and that table is bounded.
- Variation selectors (`U+FE0E`, `U+FE0F`). They turn glyphs into
  emoji on some renderers without notice.
- Zero-width characters (`U+200B`, `U+200C`, `U+200D`, `U+FEFF`).
  Zero exceptions; they're invisible smuggle channels.
- Right-to-left override (`U+202E`) and other bidi controls.
- Combining diacritics layered on ASCII to fake characters
  (`U+0300..U+036F` on a Latin letter).
**Layout rules tied to the resolution floor.**
1. The menu's per-tool line fits in 58 columns of content (after
   accounting for the chrome border). Anything longer wraps and
   the wrap is ugly. Keep tool descriptions and the muted
   secondary tag combined under that budget.
2. The status footer collapses to compact mode automatically when
   the terminal reports width less than 80. Glyphs remain. Labels
   become single letters: `T*  M*  C*  S.  HH:MM`.
3. ASCII-art logos have two variants. The wide one (used at >=80
   cols) and the narrow one (used at <80 cols). The narrow one is
   a one-line block:
   ```
   T O W E R   O F   B A B E L
   ```
   Or a sparser graphic if there's vertical room. Both variants
   are pre-rendered in `babel/art.py`, chosen by the renderer at
   mount time. Never compute the logo dynamically.
4. Tables in TUI screens are rendered with the ASCII pipe-and-dash
   set (`| - +`) on compact mode, with the box-drawing set on
   wide mode. The data is the same.
5. No screen ever depends on horizontal scroll. If content
   doesn't fit at 60 cols, restructure it; don't push it off
   screen.
**Testing the floor.** Every screen is manually checked in:
- Termux portrait on a phone with the F-Droid Termux build, default
  font, default size. This is the resolution floor.
- A real `xterm` with `LANG=C` and `TERM=xterm`. This is the ASCII
  floor.
- An 80x24 stock terminal (the historical baseline).
- A wide modern terminal (`>= 120` cols). Everything must still
  look good when there's room to spare.
If a tool can't be operated on Termux portrait, the tool fails the
suite's gate and does not release.
### 3.6 - Typography and density
- Monospaced fonts only. The terminal owns the choice.
- Two visual weights: bold for headers, prompts, and identifiers;
  regular for everything else. No italic except in the rotating
  tagline lines.
- One blank line between logical groups. Never two. Never zero
  between unrelated groups.
- No emoji. Glyph table above is the entire icon set.
### 3.7 - Hints and copy voice
Inherited from VOID's `art.HINTS`. Short, slightly menacing,
laconic, occasional `_` after a word in lower case. Rotating in the
lobby, never animated mid-line.
Examples to clone the tone:
- "follow the rabbit_."
- "the only winning move is not to play."
- "trust the math, not the network."
- "every door in this tower has a different lock."
- "hello, friend."
- "we are fsociety. we are silent."
When a user takes an irreversible action ("/burn", "purge", overwrite
in STRIP, embed in CARRIER), the confirmation text is one short
declarative line. No exclamation marks. No "Are you sure?!". Just:
`this cannot be undone. press enter to proceed, esc to cancel.`
---
## 4 - Repository architecture
```
tower_of_babel/
├── babel/                       ← suite launcher + shared shell
│   ├── __main__.py
│   ├── app.py                   ← top-level Textual App (the chrome)
│   ├── menu.py                  ← MainMenuScreen
│   ├── shell.py                 ← Chrome widget (frame + footer)
│   ├── nav.py                   ← screen-stack helpers, keybinds
│   ├── setup.py                 ← `babel --setup` aggregated diagnostic
│   ├── theme.py                 ← palette tokens, glyphs
│   ├── art.py                   ← logos, hints, scanlines
│   └── style.tcss
├── shared/                      ← reusable across tools
│   ├── crypto/
│   │   ├── secure_mem.py        ← lifted from VOID
│   │   ├── padding.py           ← ISO/IEC 7816-4
│   │   ├── kdf.py               ← HKDF/Argon2id helpers
│   │   └── aead.py              ← AES-256-GCM helpers
│   ├── tor/
│   │   ├── control.py           ← lifted from VOID's client/host.py
│   │   ├── socks_detect.py
│   │   └── ephemeral_onion.py
│   ├── ui/
│   │   ├── borders.py           ← box-drawing primitives
│   │   ├── progress.py          ← real progress bar widget
│   │   ├── step_indicator.py
│   │   ├── hex_view.py
│   │   ├── diff_view.py         ← before/after tables (STRIP, CARRIER)
│   │   └── compact.py           ← <80col adapters
│   ├── install/
│   │   ├── package_detect.py
│   │   ├── torrc_writer.py
│   │   └── path_patcher.py
│   └── link/
│       └── invite.py            ← void://, mask://, carrier:// shared codec
├── tools/
│   ├── void/                    ← current client/ + server/, moved here
│   ├── mask/
│   ├── strip/
│   ├── carrier/
│   └── mirage/
├── docs/
│   ├── README.md
│   ├── INSTALL.md
│   ├── ARCHITECTURE.md          ← suite-level
│   ├── SECURITY.md              ← suite-level threat-model frame
│   ├── HACKING.md
│   ├── FAQ.md
│   └── tools/
│       ├── VOID.md
│       ├── MASK.md
│       ├── STRIP.md
│       ├── CARRIER.md
│       └── MIRAGE.md
├── pentest/                     ← every attack script; one shared REPORT.md
│   ├── REPORT.md
│   ├── void/
│   ├── mask/
│   ├── strip/
│   ├── carrier/
│   └── mirage/
├── install.sh
├── install.ps1
├── install-termux.sh
├── build.sh
├── build.ps1
├── Dockerfile.build
├── babel.spec                   ← PyInstaller spec for the unified binary
├── .github/workflows/release.yml
├── SOURCE_DATE_EPOCH
├── VERSION
├── CHANGELOG.md
├── RELEASE_NOTES.md
├── LICENSE
├── pyproject.toml
└── requirements.txt
```
### 4.1 - Entry points
- `babel` — launches the suite into the main menu.
- `babel <tool>` — jumps straight to a tool, skipping the menu
  (`babel void`, `babel strip`, etc).
- `babel <tool> --setup` — that tool's diagnostic.
- `babel --setup` — aggregated diagnostic across all tools.
- `babel --make-invite` — kept as a convenience alias for `babel void
  --make-invite`, because that command is documented all over the
  README of VOID's predecessor.
Per-tool CLIs live under `babel <tool> …`. Each tool also installs
a top-level shortcut script for old habits: `void`, `mask`, `strip`,
`carrier`, `mirage`. These all just call `babel <tool> …`
internally.
### 4.2 - The shell (`babel.shell.Chrome`)
The Chrome is a Textual widget that:
- Draws the outer frame as a single `Static` block updated only on
  resize.
- Owns the footer and queries the indicator callables every second.
- Hosts a `ContentSlot` widget into which tool screens mount.
- Catches `Ctrl+C` and `Ctrl+Q` globally and routes them to the
  active tool's purge handler. If the active surface is the main
  menu, `Ctrl+C` exits the suite.
- Exposes `app.enter_tool("void")` / `app.return_to_menu()` so tools
  don't need to know about each other.
Tool screens are normal Textual `Screen` instances pushed onto the
content slot. They never repaint outside the slot. They never draw
their own outer border.
### 4.3 - Tool isolation rules
- A tool cannot import from another tool. Period.
- Tools may only import from `shared/` and `babel/`.
- Tools may not write to disk except under `~/.config/babel/<tool>/`
  and only when the user explicitly opts in (e.g. exporting a
  STRIP'd file to a chosen path, saving an offline MASK identity
  bundle). No implicit caches.
### 4.4 - Service tools vs action tools (the multiplex model)
The babel shell is a **multiplexer**, not a launcher. The user can
have several tools alive at the same time in the same terminal,
switching between them with hotkeys. This is non-negotiable: VOID
(a chat) and MIRAGE (a noise generator) both have to be runnable
in the background while the user uses STRIP or browses the menu.
**Two tool flavours.** Every tool declares one in `app.py`:
| Flavour | Lifecycle | Examples |
|---|---|---|
| **Service** | starts, keeps running, occupies a slot until the user `/leave`s | VOID, MIRAGE, future HOLLOW, future DRIFT |
| **Action** | runs one operation and returns to the menu | STRIP, CARRIER, MASK |
**Slots.** The shell hosts up to `BABEL_MAX_SERVICES` concurrent
services (default 4, configurable). Each running service owns one
numbered slot, visible as a badge in the top chrome:
`[1:VOID 2 peers]  [2:MIRAGE 12 KB/s]`. The badge summary text is
generated by the service itself via `service.status_line() -> str`.
Actions never own a slot. They live in the **foreground slot**
(the central panel) and yield it back when they finish.
**Hotkeys (uniform across the suite).**
| Key | Effect |
|---|---|
| `Alt+1` .. `Alt+N` | jump to service N |
| `Alt+0` | jump to the main menu (services keep running) |
| `Alt+M` | open the menu as an overlay without leaving the current view |
| `Alt+]` / `Alt+[` | cycle to next / previous active service |
| `Ctrl+W` | close the current service (calls its `purge_local()` first) |
| `Ctrl+C`, `Ctrl+Q` | quit the suite (calls `purge_local()` on EVERY service) |
The hotkey set is registered globally by `babel.shell.Chrome`. Tools
never bind `Alt+<digit>` themselves.
**Aggregated footer state.** The five status indicators
(TOR / MEM / CRYPTO / SWAP / CLOCK) reflect the union of all live
services, not the foreground:
- `TOR`: green if any service has an active Tor circuit. The
  trailing label shows `N svcs` when multiple use it.
- `MEM`: green if any service holds an mlock'd buffer; the label
  shows total live `SecureBytes` instances.
- `CRYPTO`: green if any service has live key material.
- `SWAP`: amber if any service warned about swap+mlock failure.
- `CLOCK`: always real UTC.
Each service exports a `service.footer_contribution() -> dict` that
the shell merges. Actions contribute nothing while idle.
**Resource contract.** A service must:
1. Be cooperative under `purge_local()` — when called, it returns
   in under 1 second with all in-RAM secrets zeroed and all open
   sockets / processes closed.
2. Yield CPU during idle: no busy loops. Use `asyncio.sleep` or
   real I/O `await`.
3. Cap its background bandwidth and CPU. MIRAGE has hard caps
   built in; every other service that goes near the network states
   its caps in its `docs/tools/<NAME>.md` and exposes them via
   `service.resource_caps()`.
4. Never block the shell's render loop. Long-running work goes in
   `asyncio.create_task` and reports back via the status line.
**Multiplex test.** Before any release, the shell is tested with:
- VOID + MIRAGE both running, user toggles to STRIP, processes a
  file, returns to VOID. Chat must not have lost frames; MIRAGE's
  rate must not have stalled.
- All four service slots full, fifth service launch attempt: shell
  refuses with a clear message, does not crash.
- `purge_local()` on quit zeros every buffer across every service
  in under 4 seconds total.
---
## 5 - Shared modules (`shared/`)
These exist because the tools genuinely overlap. Each module below
is named, scoped, and tied to which tools consume it.
### 5.1 - `shared/crypto/secure_mem.py`
Lifted verbatim from VOID's `client/secure_mem.py`. Used by every
tool that holds a secret in RAM:
- VOID: IK seed
- MASK: passphrases for offline-encrypted identity bundles
- CARRIER: AES key and Argon2id intermediate state
- STRIP, MIRAGE: not directly, but they import `mlock_status()` to
  decide whether to warn the user
### 5.2 - `shared/crypto/aead.py`
AES-256-GCM with HKDF-derived IV from key. Used by VOID (already
through `ratchet.py`) and CARRIER (for the steganographic payload).
### 5.3 - `shared/crypto/kdf.py`
- `argon2id(passphrase, salt, time_cost, memory_cost) -> bytes` —
  for CARRIER and MASK (where a human passphrase derives a key).
- `hkdf(input, salt, info, length)` — for VOID's chain KDFs, also
  for any future tool that needs HKDF.
### 5.4 - `shared/tor/`
- `control.py` — the direct Tor control-port client lifted from
  VOID's `client/host.py`. Used by VOID's `--make-invite` and by
  MIRAGE (for `NEW_CIRCUIT` requests when the user wants fresh
  routing for the cover noise).
- `socks_detect.py` — auto-detect `9050 / 9150 / 9151`. Used by
  VOID, MASK (Tor-routed temp mail), and MIRAGE.
- `ephemeral_onion.py` — `ADD_ONION NEW:ED25519-V3 Flags=DiscardPK`
  wrapper. Used by VOID and any future room-style tool.
### 5.5 - `shared/ui/`
- `borders.py` — the box-drawing primitives that the Chrome uses.
- `progress.py` — `RealProgressBar` widget: takes an iterable that
  yields `(done_bytes, total_bytes, rate_bytes_per_sec)` and renders
  with no internal animation timer.
- `step_indicator.py` — the `[+]`/`[.]`/`[!]`/`[ ]` step block from
  VOID's `ConnectingScreen`, generalised. STRIP, CARRIER, MASK all
  use it.
- `diff_view.py` — two-column before/after renderer for STRIP and
  CARRIER capacity reports.
- `hex_view.py` — small hex dump widget (used by CARRIER's preview
  mode and by VOID's `/whoami` extended view).
- `compact.py` — helpers that decide whether to render compact and
  shorten labels.
### 5.6 - `shared/link/invite.py`
Generalises VOID's `void://` codec to a multi-scheme codec:
- `void://...` — chat invite (existing)
- `mask://...` — exported disposable-identity bundle (offline)
- `carrier://...` — extraction hint for a cover file (optional;
  CARRIER is normally header-less by design, but the user can
  choose to ship a hint out-of-band)
All three use the same `base64url(json)` body. The scheme prefix
disambiguates. Each tool's lobby autofills its own fields when a
matching scheme is pasted.
### 5.7 - `shared/install/`
Pulls the per-platform install logic that today lives in
`install.sh` / `install.ps1` into reusable Python helpers so
`babel --setup` can run the same checks the installer ran.
---
## 6 - The launcher (`babel/`)
### 6.1 - Main menu
The screen rendered in the canonical menu mockup. Behaviour:
| Key | Action |
|---|---|
| `1`–`5` | enter the corresponding tool |
| `s` | open the setup diagnostic |
| `h` | open the suite help wizard (3 panels, VOID-style) |
| `q`, `Ctrl+C`, `Ctrl+Q` | quit the suite |
Pressing a digit calls `app.enter_tool("<name>")`, which:
1. Pushes the tool's primary screen onto the content slot.
2. Updates the top chrome to `TOWER OF BABEL / <TOOL>`.
3. Routes future `Ctrl+C` to the tool's purge handler.
Returning to the menu via the tool's `/leave` or `Esc` (when on the
tool's home screen) calls `app.return_to_menu()`, which pops the
tool's screens and resets the chrome label.
### 6.2 - First-time wizard
Three panels, same shape as VOID's `WelcomeScreen` but suite-scoped:
1. **What is this?** — explanation of the suite as a federation of
   single-purpose hammers. The "I hand you the hammer" sentence
   appears verbatim.
2. **How do I use it?** — keyboard model, the menu, where logs and
   state live (mostly: nowhere).
3. **What this cannot do** — abbreviated, honest. Endpoint
   compromise, social attacks, screen-over-shoulder, quantum HNDL.
   Points to per-tool `SECURITY.md`.
### 6.3 - Setup aggregator
`babel --setup` runs every tool's diagnostic in sequence and prints
the aggregated result. Each tool exports a `setup_check.run()` that
returns `(int_exit_code, list_of_lines)`. The aggregator concatenates
and exits non-zero if any tool fails.
---
## 7 - Per-tool sketches
The full per-tool specs live in `docs/tools/<NAME>.md`. Below are
the locked one-pagers.
### 7.1 - VOID  *(service)*
Already implemented. Migration tasks only:
- Move `client/` → `tools/void/client/`, `server/` → `tools/void/server/`.
- Move `client/secure_mem.py` → `shared/crypto/secure_mem.py`,
  import from new path in `tools/void`.
- Move `client/host.py`'s Tor control logic into
  `shared/tor/control.py`; keep `tools/void/host.py` as the thin
  invite-link orchestrator.
- Move `client/screens/lobby.py`'s outer frame logic into
  `babel/shell.py`; VOID's lobby becomes a `Screen` that mounts
  inside the Chrome's content slot, no border of its own.
### 7.2 - MASK - disposable identity generator  *(action)*
**Scope** — given a region/culture and a usage profile, produces a
coherent disposable identity: alias, locally-generated geometric
avatar, 2–3 line bio (template-based), temp email (mail.tm /
guerrillamail over Tor), optional virtual-SMS pointer.
**Wire**
- Output `mask://base64url({alias, bio, avatar_sha, mail_handle, ts})`.
- Identities live in RAM only. Optional export: passphrase-encrypted
  blob the user saves themselves.
**Honest threat model**
- Avatars from public services are reused; reverse image search
  defeats them.
- Public SMS numbers are not yours and can be read by anyone.
- Behavioural fingerprinting is not addressed.
**Reused**: `shared/crypto/{aead, kdf, secure_mem}`, `shared/tor/socks_detect`, `shared/ui/{step_indicator, diff_view}`, `shared/link/invite`.
### 7.3 - STRIP - metadata laundry  *(action)*
**Scope** — removes declared metadata from files (EXIF/XMP/IPTC,
PDF properties, Office authorship and revision history, audio
tags, MP4 atoms). Shows a before/after diff of every removed field.
**Modes**
- Single file: drop in, see diff, write out.
- Batch: process a folder, never modifies originals, dumps results
  in a chosen output dir.
- Aggressive: also strips ICC profiles and software-version hints.
**Honest threat model**
- Steganographic traces in the file body (sensor noise, printer
  dots, codec quirks) are not addressed.
- Office "track changes" residue can survive in obscure XML; STRIP
  runs a normalisation pass but does not guarantee 100%.
- Filenames are not metadata of the file but they leak. Optional
  hash-rename available.
**Reused**: `shared/ui/{progress, diff_view}`, `shared/crypto/secure_mem` (passphrase for optional encryption-on-output, future).
### 7.4 - CARRIER - steganography  *(action)*
**Scope** — embed an AES-256-GCM-encrypted payload into a cover
file (PNG, WAV, PDF, MP4). The cover stays valid and visually /
aurally identical. No marker headers in the cover by design;
extraction either works with the passphrase or returns noise.
**Pipeline**
1. Passphrase → Argon2id (interactive params by default) → AES key.
2. Payload → optional compress → AES-256-GCM encrypt with random
   nonce.
3. Capacity check on cover; refuse if unsafe margin.
4. Embed using format-appropriate strategy (LSB for PNG/WAV;
   object-stream injection for PDF; metadata-free atoms for MP4).
5. Chi-square sanity check on the modified cover; warn or refuse
   if obvious LSB tampering signature.
**Honest threat model**
- Lossy re-encoding destroys LSB payloads.
- A forensic analyst with the original cover can detect tampering.
- Existence of the tool on disk plus a recently-modified PNG is
  itself a signal.
**Reused**: `shared/crypto/{aead, kdf, secure_mem}`, `shared/ui/{progress, hex_view, diff_view}`.
### 7.5 - MIRAGE - cover traffic generator  *(service)*
**Scope** — generates plausible background network activity from
configurable profiles ("office worker", "developer", "casual
browser", "researcher"). Real HTTP requests, real DNS lookups,
real session durations, drawn from Zipf-weighted site lists.
**Controls**
- Hard caps on bandwidth, request rate, CPU (defaults: ≤5% link,
  ≤30 req/min, ≤2% CPU averaged over a minute).
- Tor-routed or clearnet (decoy at ISP level vs at Tor-exit level).
- "Honest mode": shows each request as it fires.
**Honest threat model**
- Bot-like patterns are still distinguishable from real human
  browsing under sophisticated analysis.
- Running MIRAGE itself is a tell.
- ISP-level DPI may flag the absolute volume change from your
  baseline.
- Real traffic still happens. MIRAGE buries it; it does not delete
  it.
**Reused**: `shared/tor/{control, socks_detect}`, `shared/ui/progress`.
---
### 7.6 - Planned post-1.0 additions
The multiplex architecture is sized for growth. Two natural
additions fill gaps the current five do not cover; both are
**services** and slot in cleanly when their phase comes:
**HOLLOW - ephemeral file sharing**  *(service)*. The file-transfer
sibling of VOID. Host opens an ephemeral v3 onion (same control-port
flow as VOID's `--make-invite`), serves a single file pinned in RAM
or streamed from disk, prints a `hollow://` invite. Receiver pastes
the link, file streams through, host's Ctrl+C kills the onion. No
chunking metadata stored, no resumes (intentional: a partial leak
is no better than a full one).
**DRIFT - ephemeral paste service**  *(service)*. Pegabs text or a
short blob, get a `drift://` link with `?reads=N` and/or `?ttl=Ns`.
Local-only by default; the paste lives in the host's RAM until
either limit hits. Used for "send me the OTP" or "here's the
password" exchanges where VOID's persistent chat session is
overkill. Same X3DH per-fetch handshake as VOID (the reader's
client derives a single-message ratchet rather than a chat).
Neither ships before the suite hits 1.0. The architectural commitment
today is: the slot model, the chrome, the `shared/` modules, and
the install pipeline all have to accommodate them with zero rewrite.
## 8 - Install / build / release
The suite is one repo, one PyInstaller spec, one binary
(`babel`) per platform, and one release artefact set per tag.
### 8.1 - One-command install
The existing `install.sh`, `install.ps1`, and `install-termux.sh`
are kept and **adapted only to install `babel`** (which provides
all tools) instead of a per-tool entry point. Tor configuration,
Termux's libxeddsa build, the PATH patches, and the per-user torrc
all behave exactly as documented in VOID's docs/INSTALL.md.
Post-install:
```
babel              # menu
babel void         # straight into VOID
babel strip ./img.png   # strip a file from the CLI
babel --setup           # full diagnostic
```
### 8.2 - Reproducible build
The pin set is unchanged from VOID:
- `SOURCE_DATE_EPOCH` in repo root (pinned integer).
- `PYTHONHASHSEED=0`, `PYTHONDONTWRITEBYTECODE=1`, `TZ=UTC`,
  `LC_ALL=C.UTF-8`.
- Sorted PyInstaller analysis. `strip=True`.
- `Dockerfile.build`: pinned `python:3.11.10-slim-bookworm`,
  `pip==24.2`, `setuptools==75.1.0`, `wheel==0.44.0`,
  `pyinstaller==6.10.0`.
- Hash-locked `requirements.lock`.
Single PyInstaller spec, `babel.spec`, produces one binary that
contains all tools. The old `void.spec` and `void-server.spec`
remain as alternate entry points (so a server-only deployment can
ship without dragging in MIRAGE's HTTP client and CARRIER's PIL
dependency), but the headline deliverable is `babel`.
### 8.3 - Release flow
```
tag v0.6.0
  → release.yml builds babel-0.6.0-{linux,macos-x86_64,macos-arm64,windows}-x86_64
  → also rebuilds void-server-0.6.0-* for server-only deployments
  → SHA256SUMS attached
  → CHANGELOG.md and RELEASE_NOTES.md prepared per release
```
Server-only deployments (someone running `void-server` on a
hardened host) keep their narrow attack surface; everyday users
get the full suite in one binary.
### 8.4 - Verifying a release
The flow from VOID's HACKING.md applies unchanged:
```
sha256sum -c SHA256SUMS
# or, full reproduce:
docker build -f Dockerfile.build -t babel-build:0.6.0 .
docker run --rm -v "$PWD/dist:/src/dist" babel-build:0.6.0
diff <(sort SHA256SUMS) <(sort dist/SHA256SUMS)
```
---
## 9 - Documentation model
Each tool ships a `docs/tools/<NAME>.md` with the same sections in
the same order, so users can move between tools without re-learning
the doc layout:
1. **What this is** (≤3 paragraphs)
2. **What it protects** (table)
3. **What it does NOT protect** (table, equal weight)
4. **CLI flags** (every flag, no exceptions)
5. **In-app commands and keys**
6. **Worked walkthrough** (a real session, ASCII-captured)
7. **Architecture** (formats, wire format if any, dependencies)
8. **Reproducible build notes** (per-tool overrides, if any)
Suite-level docs in `docs/` cover the chrome, the menu, the install
flow, the threat-model frame that each tool elaborates, and the
FAQ.
---
## 10 - Development phases
### Phase 0 — extraction (1 sprint)
- Create `babel/`, `shared/`, `tools/` directory tree.
- Move VOID into `tools/void/` with no behaviour change.
- Lift `secure_mem.py`, `host.py`'s Tor control client, the lobby
  border, the connecting-screen step indicator, the rotating hints,
  and the palette into `shared/` and `babel/`.
- Wire `babel/__main__.py` to a stub menu that just launches VOID.
- Verify reproducible build still produces a byte-identical binary
  for the VOID code path. (This is the regression test for the
  whole refactor.)
### Phase 1 — the shell (1 sprint)
- Implement `babel.shell.Chrome` with the continuous frame and
  real-state footer.
- Implement `MainMenuScreen` with the five entries (four of them
  greyed out until the corresponding tool exists).
- First-time wizard, suite-scoped.
- `babel --setup` aggregator stub (VOID's diagnostic is the only
  contributor for now).
### Phase 2 — STRIP (1–2 sprints)
The simplest scope. Builds out the per-tool scaffolding (docs,
pentest, diff_view widget) on a low-risk target. No network. No
new crypto. Validates that `babel <tool>` invocation and the
chrome handoff work cleanly.
Deliverable: STRIP can handle JPG/PNG, PDF, DOCX, MP3 on the
happy paths; aggressive mode works; before/after diff renders.
### Phase 3 — CARRIER (2 sprints)
Reuses STRIP's file-handling spine. Adds the AES+Argon2id pipeline,
the capacity calculator, the chi-square check, the hex view, and
the format-specific embedders.
Deliverable: CARRIER round-trips a payload through PNG and WAV.
PDF and MP4 are stretch.
### Phase 4 — MASK (2 sprints)
Network re-enters. Tor SOCKS5 path, temp-mail integrations,
geometric avatar generator, alias/bio templates, `mask://` export.
Deliverable: a coherent disposable identity in one keystroke;
optional encrypted export to a file the user picks.
### Phase 5 — MIRAGE (2–3 sprints)
The heaviest. Profile DSL, scheduler, request engine with rate
caps, Tor / clearnet routing, "honest mode" UI, telemetry of its
own footprint so the user can see what it's emitting.
Deliverable: MIRAGE runs in the background of any other tool, with
visible token-bucket state in the footer.
### Phase 6 — polish + release v1.0
- Full pentest pass across all tools.
- Aggregated `pentest/REPORT.md`.
- 0.x → 1.0 cut. CHANGELOG locked.
---
## 11 - AI-assisted development workflow
This project is being built with significant AI assistance (Claude
Code). The workflow below is what works; deviating from it tends
to produce code that compiles but breaks the suite's invariants.
### 11.1 - One session per phase, one session per new tool
The phases in Section 10 are sized to fit one Claude Code session
each. Pass the full master doc as repo context, name the phase
explicitly, and state the exit criteria. Do not pile phases.
| Session | Loads | Exit criteria |
|---|---|---|
| Phase 0 — extract | MASTER.md sections 4, 10 | VOID under `tools/void/`, all VOID tests pass, two consecutive Docker builds produce identical `SHA256SUMS` |
| Phase 1 — shell | MASTER.md sections 3, 4.4, 6 | `babel` launches into menu, Chrome renders at 60x20 and 200x50, footer aggregates state, hotkeys work |
| Phase 2 — STRIP | MASTER.md sections 7.3, 11.3 (the generator prompt) | STRIP handles JPG/PNG/PDF/DOCX/MP3 round-trip, diff renders, pentest harness present |
| Phase 3 — CARRIER | MASTER.md sections 7.4, 11.3 | CARRIER round-trips PNG and WAV, chi-square check works, capacity calculator refuses unsafe embeds |
| Phase 4 — MASK | MASTER.md sections 7.2, 11.3 | one-keystroke disposable identity end-to-end, optional encrypted export, Tor path works |
| Phase 5 — MIRAGE | MASTER.md sections 7.5, 11.3, 4.4 (service caps) | profiles run with real caps, "honest mode" UI present, the multiplex test passes with MIRAGE + VOID concurrent |
| Phase 6 — release | MASTER.md sections 8, 9 | all pentest tests green, CHANGELOG locked, reproducible builds verified across all platforms |
### 11.2 - Skills discovery: standing rule
Before implementing any non-trivial subsystem, the agent must run
`/find-skills` (or `npx skills find <keywords>` directly) to
discover whether a vetted skill already covers the domain. Prefer
skill composition over reinvention.
**When to run it:**
- Before writing any file-format parser (EXIF, PDF, DOCX, MP3, WAV,
  PNG) → search for a metadata or stego-adjacent skill.
- Before writing any Textual widget that resembles something common
  (progress bar, hex view, diff view) → search for textual or tui
  skills.
- Before writing test scaffolding → search for pytest or hypothesis
  skills.
- Before adding a new packaging concern (entry points, PyInstaller
  spec, Termux build) → search for pyinstaller, packaging, or
  termux skills.
- Before any cryptographic helper that is not already in
  `shared/crypto/` → search for cryptography skills.
**Quality gate.** Apply the find-skills SKILL.md vetting rules:
prefer >=1K installs, official sources (`vercel-labs`,
`anthropics`, `microsoft`), and >=100 GitHub stars on the source
repo. Anything weaker, treat with skepticism — when in doubt,
build inline. Compromised supply chain is a privacy-suite-killer.
**Where to record the decision.** When a skill is adopted, add a
one-line entry to `docs/HACKING.md` under "External dependencies"
including the skill name, source, install command, and the date
of the decision. When a search returns nothing useful, note that
too: "searched for `exif metadata`, no suitable skill, built inline
in `tools/strip/exif.py`".
### 11.3 - Forge: the decision and threat-modelling helper
Forge is a thinking-tool generator. Not part of the suite's runtime
(it produces no privacy or anti-surveillance functionality). It
lives in this document as a development meta-tool — invoked by any
contributor (human or AI agent) who needs structure for a decision,
a brainstorm, or a threat-model pass on a new tool.
The philosophy is the same as the rest of the project: Forge hands
you the hammer (a framework, a set of trigger questions, a
red-team exercise), it does not decide for you. The user applies
it, the user owns the outcome, and the outcome gets logged.
**When to call Forge:**
- A design tradeoff with no obvious winner ("should babel/ import
  from tools/, or should tools self-register?").
- A threat-modelling pass for a new tool (Forge returns a STRIDE
  or LINDDUN worksheet seeded with the tool's actual surface).
- Stuck on how to test a contract ("how do I verify the multiplex
  resource caps without a real Tor circuit?").
- A prioritisation moment (Forge returns a decision matrix, not a
  ranking).
**The Forge prompt (codified, paste-ready):**
```
You are Forge. You generate thinking instruments. You do NOT solve
the problem in front of you. You hand the user the framework,
question set, or exercise that fits the problem, and stop.
Process:
1. Classify the input in one of these buckets:
   - GENERATIVE     — user needs ideas or options
   - DECISION       — user needs to choose between options
   - CLARITY        — user needs to understand a system or concept
   - STUCK          — user is blocked and needs an unblocking move
   - THREAT MODEL   — user needs to enumerate adversaries or risks
   - VALIDATION     — user needs to verify a property or contract
2. Pick ONE framework appropriate to that bucket. Examples:
   - GENERATIVE     -> SCAMPER, random stimulus, analogies
   - DECISION       -> premortem, inversion, decision matrix
   - CLARITY        -> 5 Whys, first principles, Feynman
   - STUCK          -> rubber duck, perspective shift, reframing
   - THREAT MODEL   -> STRIDE, LINDDUN, attack trees, kill chain
   - VALIDATION     -> specification by example, property-based test
3. Return the framework with:
   - Name and when it works best.
   - Step-by-step instructions (numbered).
   - A worked seed applied to the user's specific input.
   - Estimated time and group size.
4. End with: "How you use it is your business."
   Do not coach. Do not iterate. The user owns the next move.
Input: <paste the problem statement here>
```
**Where to record Forge outcomes:**
- Architectural decisions go in `docs/ARCHITECTURE.md` under
  "Decision log", one line per decision: date, question, framework
  used, outcome.
- Threat-modelling outcomes go directly into the tool's
  `docs/tools/<NAME>.md` under "What this does NOT protect" —
  Forge surfaces the risks; the doc absorbs them.
- "Stuck moments" don't need to be logged unless the framework
  yielded a structural change to the code.
**Quality gate.** Forge does not replace `/find-skills`. Always
check skills first for concrete capabilities; call Forge only for
problems where the answer is a decision, not a library.
### 11.4 - Master generator prompt (for new tools)
Use this prompt to generate or refine any single tool inside the
suite. It encodes everything above into instructions an LLM can
act on directly. Paste it, then paste the per-tool one-line scope
sentence; the model produces a project skeleton ready to drop in.
```
# TOWER OF BABEL — tool generator
You are extending the Tower of Babel suite with a new room (or
refining an existing one). Tower of Babel is a privacy and
anti-surveillance suite for the terminal. Tools share a chrome, an
aesthetic, a build system, and a moral posture.
The moral posture: "I hand you the hammer. How you use it is your
business." Tools do not moralize, do not lock features behind
intended-use disclaimers, and do not log who used them for what.
0BSD license throughout.
## CORE RULES — non-negotiable
1. SINGLE PURPOSE. The tool does ONE thing extremely well. Reject
   feature creep. If a feature does not serve the one-sentence
   scope, it does not ship.
2. EPHEMERAL BY DEFAULT. No persistent state unless the user
   explicitly opts in. No telemetry. No analytics. No phone-home.
   Process dies → tool's memory dies.
3. HONEST THREAT MODEL. Every tool ships docs/tools/<NAME>.md with
   two sections of equal weight: "What this protects" and "What
   this does NOT protect". Endpoint compromise, social attacks,
   quantum HNDL, GPA — listed even when unsolved.
4. REPRODUCIBLE BUILDS. SOURCE_DATE_EPOCH pinned, PYTHONHASHSEED=0,
   sorted PyInstaller analysis, pinned Docker base. Two consecutive
   builds = byte-identical executable.
5. ISOLATION. Tools cannot import from other tools. Only from
   shared/ and babel/. Disk writes only under
   ~/.config/babel/<tool>/ and only on explicit opt-in.
## TECHNICAL CONSTRAINTS
- Python 3.11+. No JS, no Electron. TUI via Textual.
- Memory hygiene via shared/crypto/secure_mem.SecureBytes.
- Crypto via pyca/cryptography, xeddsa, doubleratchet, x3dh. Never
  roll your own.
- Networking (when present) goes through Tor SOCKS5 by default;
  clearnet only behind an explicit --clearnet flag with a red
  warning in the UI.
- One-command install via existing install.sh / install.ps1 /
  install-termux.sh; do NOT introduce a new installer.
- Cross-platform: Linux, macOS x86_64 + arm64, Windows, Android
  via Termux (F-Droid only).
## AESTHETIC CONSTRAINTS
- The tool runs INSIDE the babel chrome. Do not draw an outer
  border. Mount your screens in babel.shell.Chrome's content slot.
- Animations only when tied to real work. No fake loaders, no
  decorative spinners, no Hollywood "hacking..." sequences.
- Palette: --green #00ff9c primary, --cyan #6cdcff hints, --amber
  #ffd166 warnings, --red #ff3860 errors, --mute #7a7a7a muted.
- Glyphs from the suite vocabulary: ● active, ○ off, ◐ pending,
  ✦ trusted, ⚠ warn, ✗ error, ↻ rotating, ▸ prompt, · separator.
- Tone: short, laconic, slightly menacing. No exclamation marks.
- Compact mode for <80col terminals (Termux portrait): preserve
  glyphs, shorten labels.
## CODE STYLE
- from __future__ import annotations at the top of every module.
- Type hints everywhere.
- Module docstrings explain the WHY.
- Dataclasses for state containers.
- asyncio for concurrency. No threads unless mandatory.
- Server-side code (if any) must SURVIVE any malformed input:
  silently drop frames, never crash the process.
## DELIVERABLE PER TOOL
tools/<name>/
  __main__.py
  app.py            # Screen mounted under babel chrome
  cli.py            # `babel <name> --flag` parser
  setup.py          # contributes to `babel --setup`
  screens/          # Textual screens
  <core>.py         # tool's actual logic
docs/tools/<NAME>.md
pentest/<name>/
  test_*.py
  REPORT.md fragment (appended to the suite-level REPORT.md)
## PROCESS
Before writing code:
1. Run `/find-skills` (or `npx skills find <keywords>`) for the
   domain of this tool. Vet results: prefer >=1K installs, official
   sources, >=100 stars on the source repo. If a suitable skill
   exists, compose with it; do not reinvent. Note the search in
   docs/HACKING.md regardless of whether you adopt anything.
2. State the one-sentence scope. Reject anything outside it.
3. Invoke FORGE (see section 11.3) with a THREAT MODEL classification
   for this tool. Apply the returned worksheet. Write
   docs/tools/<NAME>.md FIRST, with both "What this protects" and
   "What this does NOT protect" populated from the Forge output. The
   "does NOT protect" list shapes which features are worth building.
4. Declare the tool's flavour: SERVICE (slot-resident, background)
   or ACTION (one-shot, foreground-only). See section 4.4 of
   MASTER.md.
5. If networked: define the wire format as a table of frame types
   and server enforcement rules.
6. Identify which shared/ modules you reuse. Add new ones only if
   genuinely cross-tool.
7. Write pentest tests alongside the code, not after. For each
   item in the threat-model "protects" column, there must be a
   test that proves the protection holds.
8. When hitting a non-obvious tradeoff during implementation,
   invoke FORGE with a DECISION classification before guessing.
   Log the outcome in docs/ARCHITECTURE.md decision log.
## WHAT TO REFUSE
Refuse and explain if the request is:
- A tool whose only plausible function is targeting a specific,
  identifiable individual (stalkerware, doxxing, CSAM).
- A feature that breaks the no-persistence, no-telemetry rule.
- Anything that adds undisclosed metadata to user-facing output.
Everything else, including use cases you personally disagree with,
is in scope. Hand the user the hammer.
## INPUT FORMAT
I will provide:
- TOOL NAME: <single uppercase word>
- SCOPE: <one sentence>
- NOTES: <optional clarifications, threat-model nudges, format hints>
You produce: full project skeleton in the deliverable structure
above, with real code in the core modules (not placeholders),
re-using shared/ liberally and matching the suite aesthetic.
If anything in my input is unclear, ask up to 3 short questions
before producing the skeleton. If everything is clear, go.
```
---
## 12 - License
0BSD. Verbatim. Do whatever. No warranty.
---
## Appendix A - Phase 0 ready-to-paste prompt
The prompt below is what you paste into a fresh Claude Code session
to execute Phase 0 (extraction of VOID into the new suite layout).
It is self-contained. Do not edit it on a whim — it encodes the
gates that protect the byte-reproducible build.
```
# Tower of Babel - Phase 0 (Extraction)
## Context
You are working on Tower of Babel, a privacy and anti-surveillance
terminal suite. The full design lives in MASTER.md at the repo
root. Read it before doing anything substantive.
The repo currently contains ONE tool, VOID (an ephemeral encrypted
terminal messenger), in its pre-suite layout: client/, server/,
docs/, pentest/ all at the root. The pre-suite VOID is fully
functional and has a reproducible-build pipeline. Both must
survive this refactor untouched.
## Mission
Refactor the repository to the post-suite directory layout
described in MASTER.md Section 4. Do not change VOID's behaviour,
its wire format, its CLI surface, or its build output. This phase
is pure structural movement plus extraction of reusable code into
shared/ and babel/.
Out of scope for this phase:
- Implementing the babel chrome / multiplexer (Phase 1).
- Building any new tool (Phases 2-5).
- Refactoring crypto internals.
- Changing wire format.
- Changing the install-script user experience.
## Hard constraint: byte-exact reproducible build
Two consecutive `make build-docker` runs after this refactor MUST
produce SHA256SUMS identical to what the SAME source produced
before the refactor. This is the regression gate. If the binary
changed, the refactor has a bug — fix it before declaring Phase 0
done.
## Read first (in this order)
Open MASTER.md and read these sections:
1. Section 1 (Vision) - the moral posture
2. Section 3.5 (Character and resolution compatibility) - what
   characters are allowed anywhere in the codebase, including
   string literals; remove any banned ones you find while moving
   files
3. Section 4 (Repository architecture) - the target tree
4. Section 4.4 (Multiplex model) - Phase 0 only stubs this; the
   stub menu must launch VOID and nothing else
5. Section 5 (Shared modules) - exactly which bits get extracted
6. Section 7.1 (VOID migration tasks)
7. Section 10 (Development phases) - re-read Phase 0
8. Section 11.2 (Skills discovery rule)
9. Section 11.3 (Forge) - read but only invoke if you hit a real
   decision point during the move
## Pre-implementation steps
1. Snapshot the current reproducible build:
     make build-docker
     cp dist/SHA256SUMS dist/SHA256SUMS.baseline
   This is the ground truth. After the refactor, the new
   SHA256SUMS must match dist/SHA256SUMS.baseline byte for byte.
2. Run `/find-skills` (or `npx skills find <keywords>`) for these
   domains, in this order:
     - "python refactor monorepo"
     - "pyinstaller reproducible build"
     - "textual app entry point"
     - "termux pkg install"
   For each search, record the outcome in docs/HACKING.md under
   a new section "External dependencies adopted (Phase 0)":
     - If a skill at >=1K installs from an official source covers
       the need, adopt it and record the install command.
     - If no skill qualifies, record "searched for X, no suitable
       skill, kept inline".
3. If you encounter a non-obvious architectural sub-decision (e.g.
   "should shared/tor/control.py expose an asyncio class or a
   stem-style sync client?"), invoke FORGE per Section 11.3 with a
   DECISION classification. Apply the returned framework. Log the
   decision in docs/ARCHITECTURE.md "Decision log" with one line:
   date, question, framework, outcome.
## Execution plan
Execute in this exact order. Commit after each numbered step so
the history is bisectable.
1. Create the new directory tree empty:
     babel/, shared/, tools/, pentest/void/
2. `git mv` VOID files:
     client/   ->  tools/void/client/
     server/   ->  tools/void/server/
     pentest/*.py  ->  pentest/void/
     pentest/REPORT.md  ->  pentest/REPORT.md (stays at root,
       rewrite the table to use "void/" prefixes)
3. Extract shared/crypto/secure_mem.py:
     - Copy tools/void/client/secure_mem.py to
       shared/crypto/secure_mem.py verbatim.
     - Replace the original with an import shim:
         from shared.crypto.secure_mem import *  # noqa: F401,F403
     - Run grep to confirm no other place imports the old path
       except through the shim.
4. Extract shared/tor/control.py:
     - The Tor control-port client currently lives inside
       tools/void/client/host.py. Move the TorControl class and
       its helpers verbatim to shared/tor/control.py.
     - host.py keeps make_invite_main() and run(); it now imports
       TorControl from shared/tor/control.
5. Extract shared/tor/socks_detect.py:
     - tools/void/client/setup_check.py contains detect_socks_port
       and TOR_SOCKS_CANDIDATES. Move them to
       shared/tor/socks_detect.py.
     - setup_check.py re-imports from the new location.
6. Extract babel/art.py and babel/theme.py:
     - tools/void/client/art.py becomes babel/art.py (the suite
       owns the ASCII logos and rotating hints).
     - The colour tokens currently scattered in client/style.tcss
       and inline `style="bold #00ff9c"` strings get a single
       source of truth: babel/theme.py with named constants
       (GREEN, CYAN, AMBER, RED, MUTE, BG, GREEN_DEEP). The
       .tcss file stays in tools/void/client/ for now but its
       hex codes must match the theme.py constants character by
       character. No new colours.
7. Extract babel/shell.py stub:
     - Create the Chrome widget shell from MASTER.md Section 4.2,
       but in Phase 0 it is a thin pass-through that mounts the
       VOID LobbyScreen in its content slot.
     - The footer's indicator callables come from VOID's existing
       state-probe functions; they are wired in but only report
       what VOID alone knows.
8. Create babel/__main__.py and babel/menu.py:
     - babel/__main__.py: the new entry point. Parses argv. If
       `babel` with no args -> push MainMenuScreen. If `babel
       void <args>` -> bypass menu, run VOID directly with the
       given args.
     - babel/menu.py: a stub MainMenuScreen that shows the
       five-item list from MASTER.md Section 6.1, but only entry
       [1] VOID is enabled. The others render dimmed with the
       text "(not yet built)" and the keypress is ignored.
9. Update PyInstaller specs:
     - Rename void.spec to babel.spec; its entry point is now
       babel/__main__.py.
     - Keep void-server.spec for server-only deployments; update
       its path to tools/void/server/__main__.py.
     - Both specs keep sorted analysis inputs and strip=True.
10. Update pyproject.toml:
      - Project name: void-chat -> tower-of-babel.
      - Entry points:
          babel       = "babel.__main__:main"
          void        = "babel.__main__:main"  # alias
          void-server = "tools.void.server.main:main"
      - setuptools.packages.find: include babel*, shared*,
        tools.void*.
11. Update install.sh, install.ps1, install-termux.sh:
      - The new top-level command is `babel`. Old `void` becomes
        an alias.
      - PATH guidance unchanged.
      - All other installer behaviour (Tor configuration, Termux
        libxeddsa build, torrc snippets) unchanged.
12. Update .github/workflows/release.yml:
      - Build babel-<version>-<platform>-<arch>{,.exe} alongside
        the existing void-server-* artifacts.
      - SHA256SUMS includes both.
13. Update docs:
      - README.md: replace "VOID" branding with "Tower of Babel /
        VOID" in headings; install lines now end in `babel`.
      - CHANGELOG.md: add a "[0.6.0]" entry listing the refactor.
      - Copy MASTER.md to docs/MASTER.md or keep it at repo root
        (preferred: repo root, since it is the single source of
        truth referenced from everywhere).
14. Re-run the build twice:
      make build-docker
      cp dist/SHA256SUMS dist/SHA256SUMS.run1
      rm -rf dist build
      make build-docker
      cp dist/SHA256SUMS dist/SHA256SUMS.run2
      diff dist/SHA256SUMS.run1 dist/SHA256SUMS.run2
      diff dist/SHA256SUMS.baseline dist/SHA256SUMS.run2
   Both diffs MUST be empty (excluding the SHA of new files that
   did not exist before, e.g. a new babel-* artifact - for THESE
   files, only the run1-vs-run2 diff must be empty; their hashes
   are simply new entries in the baseline going forward).
15. Run the pentest suite unchanged. Every test in pentest/void/
    must still pass.
16. Final commit. Tag the snapshot as `phase-0-complete` locally
    (do not push the tag to origin yet - tag pushing happens at
    release time).
## Exit criteria - all must be true
- `babel` launches a stub menu with five entries, only VOID
  enabled.
- `babel void` launches the original VOID TUI verbatim.
- `babel void --make-invite` works exactly as before.
- `babel void --setup` returns identical output to the old
  `void --setup`.
- The reproducible-build verification in step 14 passes.
- All pentest/void/*.py pass unmodified.
- `git log --stat phase-0-start..HEAD` shows only file moves,
  import path changes, and the additions specified above; no
  behavioural code changes.
- docs/HACKING.md has an "External dependencies adopted (Phase 0)"
  section listing every find-skills search and its outcome.
- If FORGE was invoked, docs/ARCHITECTURE.md has matching entries
  in the decision log.
## Do NOT, under any circumstance
- Start Phase 1 (the real multiplex shell).
- Build any of MASK, STRIP, CARRIER, MIRAGE.
- Refactor crypto internals or change the wire format.
- Add new features, even small ones, even "while you're in there".
- Suppress an mlock fallback warning that previously fired.
- Introduce any character outside Tier 1 ASCII into source files,
  string literals, or docstrings (boxed UI art in
  client/style.tcss and babel/art.py is the only allowed
  exception, and it must use only the Tier 2 set from MASTER.md
  3.5).
When the exit criteria are all met, stop and report. Phase 1 is a
separate session with a separate prompt.
```
