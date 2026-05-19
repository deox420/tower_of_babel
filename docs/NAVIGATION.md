# NAVIGATION

This document is the navigation spec for the Tower of Babel suite.
The code in `babel/shell.py`, `babel/menu.py`, `babel/views.py`,
and `shared/ui/overlay.py` matches what is described here. If the
behaviour ever drifts, this document is the source of truth --
update it first, then the code.

Suite-wide invariant: after `babel` starts, the user never has to
read documentation to navigate. The hints bar, the help overlay
(`F1`), and the slot switcher (`Alt+M`) together carry the cognitive
load.

---

## 1 - Views, screens, and overlays

The chrome (`babel.shell.Chrome`) is a single Textual `Screen`. The
"navigation" inside it is movement between **views** mounted in
the chrome's content slot, plus a small set of **overlays** that
float on top of whatever view is current.

| Surface | Kind | Source | Notes |
|---|---|---|---|
| Main menu | View | `babel/menu.py` `MainMenuView` | Always at the bottom of the view stack. Never popped. |
| VOID home | View (SERVICE) | `tools/void/client/app.py` `VoidView` | Owns a `VoidService` -- registered in the slot table. |
| MASK home | View (ACTION) | `tools/mask/app.py` `MaskView` | No slot. Torn down on `Esc`. |
| STRIP home | View (ACTION) | `tools/strip/app.py` `StripView` | No slot. Torn down on `Esc`. |
| CARRIER home | View (ACTION) | `tools/carrier/app.py` `CarrierView` | No slot. Torn down on `Esc`. |
| MIRAGE home | View (SERVICE) | `tools/mirage/app.py` `MirageView` | Owns a `MirageService`. |
| Help overlay | Overlay | `shared/ui/overlay.py` `HelpOverlay` | Modal. Bound to `F1` / `Alt+H`. |
| Slot switcher | Overlay | `shared/ui/overlay.py` `SlotSwitcherOverlay` | Modal. Bound to `Alt+M`. |

The Chrome itself owns the outer frame, the slot bar (top), the
hints line (above footer), and the indicator footer. None of those
participate in navigation -- they reflect state, they don't host
content.

### 1.1 - SERVICE vs ACTION flavour

A view declares its flavour with a class attribute `flavour =
"SERVICE"` or `"ACTION"`. The chrome reads it on `enter_tool` to
decide:

- **SERVICE** views are kept alive when the user goes back to the
  menu. They occupy a numbered slot, are reachable with
  `Alt+<digit>`, and contribute to the footer's aggregate state.
  Their backing `Service` object lives in `ServiceRegistry`.
- **ACTION** views run a one-shot operation foreground-only. They
  occupy no slot. `Esc` tears them down; opening a different
  action replaces the current one in place.

The five v1.0 tools split as:

```
SERVICE  : VOID  MIRAGE
ACTION   : MASK  STRIP  CARRIER
```

---

## 2 - Keybindings

The chrome registers every key in this section as a priority
binding so a view's own bindings never shadow them. Per-view keys
(e.g. STRIP's `[a]` for aggressive mode) are local.

### 2.1 - Suite-level (always active)

| Key            | Effect                                                              |
|----------------|---------------------------------------------------------------------|
| `F1` / `Alt+H` | Open the help overlay listing suite + view bindings.                |
| `Alt+M`        | Open the slot-switcher overlay.                                     |
| `Alt+0`        | Return to the menu. SERVICE views stay alive in their slots.        |
| `Alt+1` .. `Alt+9` | Jump to the SERVICE in slot N. No-op if the slot is empty.      |
| `Alt+]`        | Cycle to the next active SERVICE.                                   |
| `Alt+[`        | Cycle to the previous active SERVICE.                               |
| `Ctrl+W`       | Close the current SERVICE (purge + free its slot). No-op elsewhere. |
| `Ctrl+C`       | Quit the suite. Purges every SERVICE; 4-second budget.              |
| `Ctrl+Q`       | Alias for `Ctrl+C`.                                                 |

### 2.2 - Main menu

| Key       | Effect                                                                 |
|-----------|------------------------------------------------------------------------|
| `1`..`5`  | Enter the corresponding tool (mounts its View; registers Service if SERVICE-flavoured). |
| `Shift+1`..`Shift+5` | Enter a NEW instance of the corresponding tool. For SERVICE tools this opens a second VOID / second MIRAGE in the next free slot (subject to `BABEL_MAX_SERVICES`). For ACTION tools, identical to `1`..`5` (actions can't have two foreground copies anyway). |
| `q`       | Quit the suite (calls the same purge path as `Ctrl+C`).                |
| `Esc`     | No-op. The menu is the root view; there is nowhere to go back to.      |
| `p`       | (Termux 60-col floor only.) Open the paste sub-screen for `void://` / `mask://` / `carrier://` links. On wider terminals the paste field is inline at the bottom of the menu. |

### 2.3 - SERVICE view (VOID, MIRAGE)

| Key            | Effect                                                       |
|----------------|--------------------------------------------------------------|
| `Esc`          | Return to the menu. The service stays in its slot.           |
| `Alt+0`        | Same as `Esc` (canonical suite-level binding).               |
| `Ctrl+W`       | Purge the service, free the slot, return to the menu.        |
| per-view keys  | The tool's own bindings (e.g. MIRAGE's `[s] [p] [r]`).       |

### 2.4 - ACTION view (MASK, STRIP, CARRIER)

| Key            | Effect                                                       |
|----------------|--------------------------------------------------------------|
| `Esc`          | Return to the menu. The action's view is torn down.          |
| `Alt+0`        | Same as `Esc`.                                               |
| `Ctrl+W`       | Same as `Esc` (action has no slot, so close == leave).       |
| per-view keys  | The tool's own bindings (e.g. STRIP's `[a]`, `[w]`).         |

### 2.5 - Help overlay

| Key            | Effect                                                       |
|----------------|--------------------------------------------------------------|
| `Esc`          | Close the overlay; return to whatever view was current.      |
| `F1` / `Alt+H` | Close the overlay (toggle).                                  |
| arrow keys     | Scroll if the overlay does not fit (60x20 fallback).         |

### 2.6 - Slot switcher overlay

| Key            | Effect                                                       |
|----------------|--------------------------------------------------------------|
| `Enter`        | Jump to the highlighted slot's SERVICE.                      |
| arrow keys     | Move the highlight.                                          |
| `Ctrl+W`       | Close the highlighted slot's SERVICE.                        |
| `Esc`          | Close the overlay; return to whatever view was current.      |
| `Alt+M`        | Close the overlay (toggle).                                  |

### 2.7 - Why `Shift+<digit>` for new-instance?

Termux's F-Droid build maps `Shift+<digit>` to the corresponding
symbol on US/UK keymaps (`!`, `@`, `#`, ...). We bind the symbols
too, so both spellings work:

```
new-instance bindings : shift+1  exclamation_mark
                        shift+2  at
                        shift+3  hash
                        shift+4  dollar_sign
                        shift+5  percent_sign
```

On Termux a user can type `!`, `@`, `#`, `$`, `%` from the symbol
row to spawn a new instance even if their keyboard cannot send
`Shift+<digit>`.

---

## 3 - State diagram

The minimum complete picture. Boxes are views/overlays; arrows
are keybindings (suite-level unless noted).

```
                       +------------------+
                       |  babel <argv...> |
                       +--------+---------+
                                |
                                v
                       +------------------+
                  +----| Main menu        |<-------------+
                  |    +------------------+              |
                  |     |  ^   ^   ^   ^                 |
                  |  1-5|  |Esc|Esc|Esc|Esc              |
                  |     v  |   |   |   |                 |
                  |    +----+----+----+----+             |
                  |    |VOID|MASK|STRIP|...|             |
                  |    +----+----+----+----+             |
                  |       |       |                      |
                  |  Alt+0|       |Esc / Alt+0           |
                  |  (svc)|       |(action: tear down)   |
                  |       v       v                      |
                  |   +-------+   +------+               |
                  +-->|       |   | menu |---------------+
                      | menu  |   +------+
                      | (svc  |
                      |  alive|       Ctrl+W
                      |  in   |---> purge + return to menu
                      |  slot)|
                      +-------+

   (always available, modal over whatever view is current)
   +--------------------+        +----------------------+
   |    Help overlay    |        |  Slot switcher       |
   |   (F1 / Alt+H)     |        |    (Alt+M)           |
   +--------------------+        +----------------------+
       Esc/F1 closes                 Enter/Esc closes
```

`Alt+1`..`Alt+9` jump directly into the SERVICE living in that
slot (skipping the menu). `Alt+]` / `Alt+[` cycle. The menu is
always the root: every `Esc` and every `Alt+0` lands here.

---

## 4 - SERVICE flow (VOID, MIRAGE)

A SERVICE-flavour view is reachable through three paths:

1. **First entry.** User presses `1` (VOID) on the menu. The
   chrome looks up `VoidView`, instantiates it, pulls
   `view.service` (a `VoidService` constructed by the view), and
   inserts that into `ServiceRegistry` at the next free slot.
   The view is `push_view`'d into the content slot. The header
   slot bar repaints; the hints line switches to the SERVICE
   variant.
2. **Re-entry while alive.** User backgrounded the service with
   `Alt+0` and now presses `1` again. The chrome sees a registry
   entry whose service `.name == "VOID"`, calls
   `chrome.show_existing(svc.view)`, focuses it, and refreshes
   the chrome. No new instance.
3. **Force new instance.** User presses `Shift+1` (or the
   symbol-row equivalent on Termux). The chrome instantiates a
   second `VoidView` + `VoidService` and registers it in the
   next free slot. Both VOIDs are alive in parallel, both shown
   in the slot bar, both reachable by their own `Alt+<digit>`.

If the registry is already at `BABEL_MAX_SERVICES` capacity
(default 4, set with the `BABEL_MAX_SERVICES` env var):

- Pressing `1` for a SERVICE tool already in the registry still
  focuses the existing slot -- no failure.
- Pressing `Shift+1` (or any new-instance attempt) when full
  surfaces a one-line "slots full -- close one with Ctrl+W"
  status in the chrome hints line. No exception.

Backgrounding a SERVICE (`Alt+0` / `Esc`): the chrome hides the
view (display: False) but leaves it mounted. The Service stays in
the registry. Slot bar still shows the entry.

Closing a SERVICE (`Ctrl+W` while focused, or `Ctrl+W` in the
slot switcher overlay): the chrome calls
`registry.close(idx)`, which awaits `service.purge_local()` under
the 1-second cooperative budget (MASTER.md 4.4), removes the
service from the registry, unmounts the view, and returns to the
menu. Other services keep running.

---

## 5 - ACTION flow (MASK, STRIP, CARRIER)

ACTION-flavour views are foreground-only. The chrome enforces
"at most one ACTION view at a time".

1. User presses `2` on the menu. The chrome instantiates
   `MaskView`, `push_view`s it. The hints line switches to the
   ACTION variant. No registry insert; no slot bar entry.
2. User opens a different ACTION (e.g. presses `3`). The chrome
   notices there is already an ACTION view alive. It tears the
   first one down (calls `view.remove()`), then pushes the new
   one. A one-line "MASK closed -- opening STRIP" message lands
   in the chrome's hints/status row.
3. User opens a SERVICE (`1` or `5`) while in an ACTION view.
   The ACTION view is torn down first, then the SERVICE is
   mounted. The user can return to the menu and re-open the
   ACTION; it starts fresh.
4. `Esc` / `Alt+0` / `Ctrl+W` all tear the action down and
   return to the menu.

ACTION views never appear in the slot bar. The slot bar is for
SERVICEs only.

---

## 6 - Paste-aware menu

The menu hosts a small `Input` widget at the bottom, placeholder:

```
//  paste a void:// / mask:// / carrier:// link to autofill ...
```

The field is **not** auto-focused. Digit keys (`1`..`5`),
`Shift+<digit>`, and `q` still work without clicking the field
first. The user clicks (or `Tab`s) into the field, pastes a link,
and presses `Enter`.

On `Enter`:

1. Strip the value and pass it to
   `shared.link.invite.looks_like`. If it returns `None`, show
   `unknown scheme; expected void:// / mask:// / carrier://` in
   the chrome's hints/status row and stop.
2. Otherwise:

   - `void://...`    -> mount `VoidView` and call
     `view.prefill_invite(link)`. The lobby's invite input is
     populated; the user reviews and presses Enter to join.
   - `mask://...`    -> mount `MaskView` in decode mode and
     call `view.prefill_link(link)`. The decoded bundle is shown.
   - `carrier://...` -> mount `CarrierView` in inspect mode and
     call `view.prefill_link(link)`. The header is shown.

The codec is `shared.link.invite.decode` / `looks_like`. The
menu does not write its own prefix detection.

On Termux's 60-col floor there is no room for an inline `Input`
under the menu card. Pressing `p` opens a sub-screen with just
the input field; everything else above continues to behave the
same.

---

## 7 - Help overlay (F1 / Alt+H)

The overlay is a modal layered over the current view. It renders
three sections in this order:

1. **Suite-level bindings** (Section 2.1 of this doc).
2. **View-local bindings.** Auto-discovered from the visible
   view's `BINDINGS` attribute via reflection. Hidden bindings
   (`show=False`) are filtered out unless the binding's action
   has no other entry point (so the user can still see how to
   trigger it).
3. **What this view is.** The first sentence of the visible
   view's class docstring (`view.__doc__`), or `(no docstring)`
   if missing.

`Esc`, `F1`, and `Alt+H` all close the overlay. The overlay
restores focus to the underlying view.

On 60x20 the overlay's content area scrolls if the binding list
doesn't fit. Suite-level bindings are always shown first so the
user never has to scroll to see how to close the overlay.

---

## 8 - Slot switcher overlay (Alt+M)

Renders one row per live SERVICE plus, on its own line, the
current ACTION view if any:

```
[1] VOID    -- 2 peers, ratchet ready          (Alt+1)
[2] MIRAGE  -- 18 rpm, 41 KB/min               (Alt+2)
[3] MASK    -- foreground action               (  -- )
```

- `Enter` on a row jumps to that view.
- `Ctrl+W` on a row closes that slot (SERVICE only; on an
  ACTION row, `Ctrl+W` returns to the menu, same semantics as
  pressing `Ctrl+W` on the ACTION view itself).
- `Esc` and `Alt+M` close the overlay without changing focus.

On 60x20 the row format collapses to:

```
[1] V   2 peers          (A1)
[2] M   18 rpm           (A2)
[3] MK  fg action        ( -)
```

The (A1) etc. is the Alt+1 hint with the obvious shortening.

---

## 9 - Hints line nudge for slot hotkeys

For the first 5 seconds after a session start, the chrome's hints
line shows the additional line:

```
Alt+1..4 jump   Alt+0 menu   Ctrl+W close
```

This nudges the first-time user into discovering the multiplex
hotkeys. After 5 seconds the line reverts to the view-specific
hints (Section 2.x). The nudge is suppressed entirely on the
Termux 60-col floor (no room).

The nudge only fires on the menu view -- once the user has
already entered a tool they have demonstrated discovery.

---

## 10 - Layout downgrades for the 60x20 (Termux) floor

| Surface | Wide form | Compact (<80 col) | Termux floor (60 col) |
|---|---|---|---|
| Slot bar | `[1:VOID 2 peers]  [2:MIRAGE 18 rpm]` | `[1:VOID] [2:MIRAGE]` | `[1:V] [2:M]` |
| Hints line | `<Esc> back  <Alt+1..N> slot  <Ctrl+W> close ...` | abbreviated | `<Esc> menu  <Ctrl+W> close` |
| Menu paste field | inline `Input` under the menu card | inline | sub-screen reached with `p` |
| Help overlay | full table | full table | scrolls if too tall |
| Slot switcher | wide row format | wide row format | collapsed row format |
| Hotkey nudge | shown for 5s on menu | shown for 5s on menu | suppressed |
| First-time wizard | three panels (post-1.0) | three panels (post-1.0) | three panels stacked (post-1.0) |

The compact threshold is `theme.COMPACT_THRESHOLD = 80` cols.
The Termux-floor threshold is 60 cols (the MASTER.md 3.5
non-negotiable floor). Between those, behaviour is identical.

Compact mode is *width* only. Height < 20 rows is unsupported by
design -- the user is on something smaller than a phone in
portrait, and the chrome's footer + header + content cannot
co-exist below that.

### 10.1 - Smoke verification (Phase 7)

The pure-string renderers are verified at three widths against
the layouts above:

```
width=200  : slot bar shows full status text; help-overlay key
             column is 18 cols wide; switcher rows are widely
             spaced with (Alt+1) / (Alt+2) Alt-hints; footer
             "* TOR :9050 -- * MEM mlock -- . CRYPTO idle -- ..."

width=80   : same wide layout (the compact threshold is `< 80`,
             so 80 itself is still wide); contents fit within
             80 cols.

width=60   : slot bar collapses to `[1:VOID] [2:MIRAGE]`;
             footer collapses to `T* -- M* -- C. -- S* -- HH:MM`;
             help-overlay key column is 12 cols and the bottom
             line shortens to `<Esc> close`; slot switcher uses
             `(A1)` / `(A2)` / `( -)` Alt-hints and the short
             footer `<Ent> jump  <CtrlW> close  <Esc> back`.
             Every output line is <= 60 cols.
```

The pentest suite (`pentest/babel/test_termux_60col.py`) walks
every renderable surface and asserts the 60-col line-length
invariant.

---

## 11 - Out of this doc

- Wire formats (`void://`, `mask://`, `carrier://`) are in
  `shared/link/invite.py` and per-tool docs.
- Crypto, file parsers, network engines: per-tool docs.
- First-time wizard (MASTER.md 6.2): deferred post-1.0.
- HOLLOW, DRIFT (MASTER.md 7.6): planned post-1.0 SERVICE-flavour
  additions. They slot into Sections 1, 2.1, 4, and 8 here
  with no structural changes.
