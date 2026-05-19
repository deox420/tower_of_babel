"""Modal overlays for the babel chrome -- help + slot switcher.

Two surfaces (MASTER.md 4.4, docs/NAVIGATION.md sections 7 + 8):

* The **help overlay** lists the suite-level bindings, the visible
  view's own bindings (auto-discovered from its ``BINDINGS`` attr),
  and a one-line "what is this view" tagline.  Triggered by ``F1``
  / ``Alt+H`` anywhere in the chrome.
* The **slot switcher** lists every live service slot plus the
  current foreground ACTION view (if any), each annotated with its
  ``Alt+<digit>`` shortcut.  Triggered by ``Alt+M`` anywhere.

Pure-string renderers come first (``render_help`` /
``render_slot_switcher``) so the pentest harness can drive every
behaviour without Textual.  Textual ``ModalScreen`` wrappers come
second behind a lazy import; importing this module never imports
Textual.

Suite invariant: every character emitted must be Tier 1 ASCII or
in the Tier 2 / Tier 3 vocabulary committed in MASTER.md 3.5.
Glyphs go through ``babel.theme.glyph`` so the ASCII-fallback
switch flips this widget too.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from babel import theme


# ---------------------------------------------------------------------------
# Data shapes shared by both overlays.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeyBinding:
    """One row in the help overlay.  Pure data, no Textual import."""

    key: str            # "F1", "Ctrl+W", "Alt+0", "Esc", "1..5", ...
    description: str    # "open help", "close service", ...


@dataclass(frozen=True)
class SlotRow:
    """One row in the slot switcher.

    ``index`` is the slot number for SERVICEs (1..BABEL_MAX_SERVICES)
    or ``0`` for the foreground ACTION pseudo-row.  ``alt_hint`` is
    the ``Alt+N`` text to show on the right; for the ACTION row it
    is rendered as ``-- `` (no jump shortcut).
    """

    index: int
    name: str           # "VOID", "MIRAGE", "MASK", ...
    status: str         # "2 peers", "18 rpm", "foreground action", ...
    is_action: bool = False
    highlighted: bool = False


# ---------------------------------------------------------------------------
# Help overlay renderer.
# ---------------------------------------------------------------------------


_HELP_HEADER = "HELP"
_HELP_FOOTER_WIDE   = "<Esc> / <F1> / <Alt+H> close"
_HELP_FOOTER_COMPAT = "<Esc> close"

_SECTION_SUITE   = "suite bindings"
_SECTION_VIEW    = "view bindings"
_SECTION_TAGLINE = "view"

# Max width consumed for the "key" column of a binding table.  Anything
# wider gets truncated with an ellipsis so the description column is
# still visible at 60 cols.
_KEY_COL_WIDE    = 18
_KEY_COL_COMPACT = 12


def _border(width: int, glyph_key: str = "hbar_light") -> str:
    return theme.glyph(glyph_key) * max(0, width)


def _fit_col(text: str, width: int) -> str:
    """Truncate ``text`` to ``width`` characters with an ASCII '...' if needed.

    Width is measured in code points; the suite only uses single-cell
    characters per MASTER.md 3.5, so code points and columns match.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text + " " * (width - len(text))
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _render_binding_row(b: KeyBinding, key_col: int) -> str:
    return f"  {_fit_col(b.key, key_col)}  {b.description}"


def _render_section(title: str, lines: Iterable[str]) -> str:
    out: list[str] = [f"-- {title} --"]
    for line in lines:
        out.append(line)
    return "\n".join(out)


def render_help(
    suite_bindings: Sequence[KeyBinding],
    view_bindings: Sequence[KeyBinding],
    view_name: str,
    view_tagline: str,
    *,
    width: int | None = None,
) -> str:
    """Render the help overlay as a single string.

    Layout (wide):

        ====== HELP -- <view_name> ======

        -- suite bindings --
          F1 / Alt+H        open this help
          Alt+M             slot switcher
          ...

        -- view bindings --
          n                 generate
          Esc               back to menu

        -- view --
          MASK -- one-line tagline taken from the View class docstring.

        <Esc> / <F1> / <Alt+H> close

    Layout (compact, <80 cols): same sections, narrower key column,
    short footer line.  Layout (60-col floor): identical to compact
    -- the chrome wraps the overlay in a scroll container.
    """
    compact = theme.is_compact(width)
    key_col = _KEY_COL_COMPACT if compact else _KEY_COL_WIDE

    header_text = f"{_HELP_HEADER} -- {view_name}" if view_name else _HELP_HEADER
    parts: list[str] = []
    parts.append(header_text)
    parts.append("")
    parts.append(_render_section(
        _SECTION_SUITE,
        (_render_binding_row(b, key_col) for b in suite_bindings),
    ))
    parts.append("")
    if view_bindings:
        parts.append(_render_section(
            _SECTION_VIEW,
            (_render_binding_row(b, key_col) for b in view_bindings),
        ))
        parts.append("")
    parts.append(_render_section(
        _SECTION_TAGLINE,
        [f"  {view_tagline or '(no docstring)'}"],
    ))
    parts.append("")
    parts.append(_HELP_FOOTER_COMPAT if compact else _HELP_FOOTER_WIDE)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Slot switcher renderer.
# ---------------------------------------------------------------------------


_SWITCHER_HEADER = "SWITCH"
_SWITCHER_FOOTER_WIDE   = "<Enter> jump   <Ctrl+W> close   <Esc> back"
_SWITCHER_FOOTER_COMPAT = "<Ent> jump  <CtrlW> close  <Esc> back"

_EMPTY_WIDE    = "  (no live services -- press 1..5 from the menu)"
_EMPTY_COMPACT = "  (no live services)"


def _fmt_alt_hint(index: int, is_action: bool, *, compact: bool) -> str:
    if is_action:
        return "( -- )" if not compact else "( -)"
    return f"(Alt+{index})" if not compact else f"(A{index})"


def _short_name(name: str, *, compact: bool, narrow: bool) -> str:
    if narrow:
        # 60-col floor: prefer one-letter (V/M) for SERVICE rows and
        # two-letter (MK/ST/CR) for ACTION rows; chosen so VOID/MIRAGE
        # collapse to the same glyphs the slot bar uses.
        return name[:2] if len(name) > 1 and name[:1] in {"M", "S", "C"} else name[:1]
    if compact:
        return name[:6]
    return name


def render_slot_switcher(
    rows: Sequence[SlotRow],
    *,
    width: int | None = None,
) -> str:
    """Render the slot-switcher overlay as a single string.

    Layout (wide):

        ====== SWITCH ======

        > [1] VOID    -- 2 peers, ratchet ready    (Alt+1)
          [2] MIRAGE  -- 18 rpm, 41 KB/min         (Alt+2)
          [3] MASK    -- foreground action         ( -- )

        <Enter> jump   <Ctrl+W> close   <Esc> back

    The ``>`` marker is on the highlighted row.  The wide form has
    aligned columns; the compact and narrow forms collapse names
    and hints.
    """
    w = width if width is not None else theme.terminal_width()
    compact = theme.is_compact(w)
    narrow = theme.is_very_compact(w)

    parts: list[str] = [_SWITCHER_HEADER, ""]
    if not rows:
        parts.append(_EMPTY_COMPACT if compact else _EMPTY_WIDE)
        parts.append("")
        parts.append(
            _SWITCHER_FOOTER_COMPAT if compact else _SWITCHER_FOOTER_WIDE
        )
        return "\n".join(parts)

    # Column widths: [N] takes 4 cols ("[1] "); the name column is
    # padded to the widest name (capped at 8 wide, 6 compact, 2
    # narrow); the status column gets what's left.
    name_cap = 2 if narrow else (6 if compact else 8)
    name_width = min(
        name_cap,
        max((len(_short_name(r.name, compact=compact, narrow=narrow))
             for r in rows), default=0),
    )

    for r in rows:
        marker = ">" if r.highlighted else " "
        idx_label = f"[{r.index}]" if not r.is_action else "[--]"
        if narrow:
            idx_label = idx_label.replace("[--]", "[F]")
            # 60-col room budget: marker(2) + idx(4) + name(2 + pad 1)
            # + status(<=N) + altHint(<=4).
            parts.append(
                f"{marker} {idx_label} "
                f"{_fit_col(_short_name(r.name, compact=True, narrow=True), name_width)} "
                f"{_fit_col(r.status, max(8, w - 22))} "
                f"{_fmt_alt_hint(r.index, r.is_action, compact=True)}"
            )
        else:
            parts.append(
                f"{marker} {idx_label} "
                f"{_fit_col(_short_name(r.name, compact=compact, narrow=False), name_width)}  "
                f"{_fit_col(r.status, max(10, w - (name_width + 22)))}  "
                f"{_fmt_alt_hint(r.index, r.is_action, compact=compact)}"
            )

    parts.append("")
    parts.append(
        _SWITCHER_FOOTER_COMPAT if compact else _SWITCHER_FOOTER_WIDE
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Auto-discovery helpers (also pure-Python).
# ---------------------------------------------------------------------------


def bindings_from_class(cls: type) -> list[KeyBinding]:
    """Walk ``cls.BINDINGS`` and return a list of ``KeyBinding`` rows.

    Accepts Textual's three binding shapes without importing Textual:

      * a ``Binding`` object with ``.key`` and ``.description`` attrs
      * a 2-tuple ``(key, description)`` or 3-tuple
        ``(key, action, description)``
      * a plain string ``"key,action,description"`` (Textual's
        shorthand)

    Hidden bindings (``show=False``) are kept -- the help overlay
    is exactly where the user wants to see them.  Caller-side
    filtering (e.g. dropping ``Alt+digit`` because it's already in
    the suite list) happens above this function.
    """
    raw = getattr(cls, "BINDINGS", None) or []
    out: list[KeyBinding] = []
    for entry in raw:
        key = None
        desc = ""
        # textual.binding.Binding (or anything that quacks)
        for attr_key, attr_desc in (("key", "description"),):
            if hasattr(entry, attr_key) and hasattr(entry, attr_desc):
                key = getattr(entry, attr_key)
                desc = getattr(entry, attr_desc) or ""
                break
        if key is None:
            if isinstance(entry, tuple):
                if len(entry) >= 2:
                    key = entry[0]
                if len(entry) == 2:
                    desc = entry[1]
                elif len(entry) >= 3:
                    # (key, action, description)
                    desc = entry[2]
            elif isinstance(entry, str):
                bits = entry.split(",")
                if len(bits) >= 1:
                    key = bits[0]
                if len(bits) >= 3:
                    desc = bits[2]
        if not key:
            continue
        out.append(KeyBinding(key=str(key), description=str(desc)))
    return out


def tagline_from_docstring(cls: type) -> str:
    """Return the first sentence of ``cls.__doc__``, or empty string."""
    doc = (cls.__doc__ or "").strip()
    if not doc:
        return ""
    # First sentence ends at the first '.' / '\n\n'; we accept either.
    for end in (".", "\n\n"):
        i = doc.find(end)
        if i != -1:
            return doc[: i + (1 if end == "." else 0)].strip()
    # Single-line docstring or no terminator: return the first line.
    return doc.splitlines()[0].strip()


# ---------------------------------------------------------------------------
# Textual widget wrappers (lazy -- only created when actually requested).
# ---------------------------------------------------------------------------


def _HelpOverlay():    # noqa: N802 -- factory, not class
    from textual.binding import Binding
    from textual.containers import Container, ScrollableContainer
    from textual.screen import ModalScreen
    from textual.widgets import Static

    class HelpOverlay(ModalScreen):    # type: ignore[misc]
        """F1 / Alt+H help overlay.

        Renders the suite-level + view-local bindings of the chrome's
        currently-visible view, plus a one-line tagline taken from
        the view class's docstring.
        """

        DEFAULT_CSS = f"""
        HelpOverlay {{
            align: center middle;
            background: {theme.BG} 70%;
        }}
        HelpOverlay #help-card {{
            width: 80%;
            max-width: 80;
            height: auto;
            max-height: 90%;
            padding: 1 2;
            background: {theme.BG};
            border: round {theme.GREEN} 55%;
            color: {theme.GREEN};
        }}
        HelpOverlay #help-body {{
            height: auto;
            max-height: 18;
            overflow-y: auto;
        }}
        """

        BINDINGS = [
            Binding("escape", "dismiss", "close", show=False, priority=True),
            Binding("f1",     "dismiss", "close", show=False, priority=True),
            Binding("alt+h",  "dismiss", "close", show=False, priority=True),
        ]

        def __init__(
            self,
            suite_bindings: Sequence[KeyBinding],
            view_bindings: Sequence[KeyBinding],
            view_name: str,
            view_tagline: str,
        ) -> None:
            super().__init__()
            self._text = render_help(
                suite_bindings, view_bindings, view_name, view_tagline,
            )

        def compose(self):
            yield Container(
                ScrollableContainer(
                    Static(self._text, id="help-text"),
                    id="help-body",
                ),
                id="help-card",
            )

        def action_dismiss(self) -> None:
            self.app.pop_screen()

    return HelpOverlay


def _SlotSwitcherOverlay():    # noqa: N802
    from textual.binding import Binding
    from textual.containers import Container, ScrollableContainer
    from textual.screen import ModalScreen
    from textual.widgets import Static

    class SlotSwitcherOverlay(ModalScreen):    # type: ignore[misc]
        """Alt+M slot switcher overlay.

        Renders one row per live SERVICE plus, on its own line, the
        foreground ACTION view (if any).
        """

        DEFAULT_CSS = f"""
        SlotSwitcherOverlay {{
            align: center middle;
            background: {theme.BG} 70%;
        }}
        SlotSwitcherOverlay #switch-card {{
            width: 80%;
            max-width: 70;
            height: auto;
            max-height: 90%;
            padding: 1 2;
            background: {theme.BG};
            border: round {theme.CYAN} 55%;
            color: {theme.GREEN};
        }}
        SlotSwitcherOverlay #switch-body {{
            height: auto;
            max-height: 14;
            overflow-y: auto;
        }}
        """

        BINDINGS = [
            Binding("escape",       "dismiss",   "close",     show=False, priority=True),
            Binding("alt+m",        "dismiss",   "close",     show=False, priority=True),
            Binding("up",           "move(-1)",  "up",        show=False, priority=True),
            Binding("down",         "move(1)",   "down",      show=False, priority=True),
            Binding("enter",        "jump",      "jump",      show=False, priority=True),
            Binding("ctrl+w",       "close_slot","close slot",show=False, priority=True),
        ]

        def __init__(self, rows: Sequence[SlotRow]) -> None:
            super().__init__()
            # Highlight defaults to the first row, if any.
            self._rows: list[SlotRow] = []
            for i, r in enumerate(rows):
                self._rows.append(
                    SlotRow(
                        index=r.index, name=r.name, status=r.status,
                        is_action=r.is_action, highlighted=(i == 0),
                    )
                )
            self._highlight = 0

        def compose(self):
            self._body = Static(self._text(), id="switch-text")
            yield Container(
                ScrollableContainer(self._body, id="switch-body"),
                id="switch-card",
            )

        def _text(self) -> str:
            return render_slot_switcher(self._rows)

        def _redraw(self) -> None:
            self._body.update(self._text())

        def action_move(self, step: int) -> None:
            if not self._rows:
                return
            self._highlight = (self._highlight + step) % len(self._rows)
            self._rows = [
                SlotRow(
                    index=r.index, name=r.name, status=r.status,
                    is_action=r.is_action, highlighted=(i == self._highlight),
                )
                for i, r in enumerate(self._rows)
            ]
            self._redraw()

        def action_jump(self) -> None:
            if not self._rows:
                self.app.pop_screen()
                return
            row = self._rows[self._highlight]
            self.app.pop_screen()
            jump = getattr(self.app, "slot_switcher_jump", None)
            if callable(jump):
                jump(row)

        def action_close_slot(self) -> None:
            if not self._rows:
                return
            row = self._rows[self._highlight]
            self.app.pop_screen()
            close = getattr(self.app, "slot_switcher_close", None)
            if callable(close):
                close(row)

        def action_dismiss(self) -> None:
            self.app.pop_screen()

    return SlotSwitcherOverlay


def __getattr__(name: str):
    """Lazy textual import.  The pure renderers above never import textual."""
    if name == "HelpOverlay":
        return _HelpOverlay()
    if name == "SlotSwitcherOverlay":
        return _SlotSwitcherOverlay()
    raise AttributeError(name)


__all__ = [
    "KeyBinding", "SlotRow",
    "render_help", "render_slot_switcher",
    "bindings_from_class", "tagline_from_docstring",
    "HelpOverlay", "SlotSwitcherOverlay",
]
