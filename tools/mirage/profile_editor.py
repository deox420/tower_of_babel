"""MIRAGE profile editor — a Container mounted into MirageView.

Lets the user tweak the timing knobs of a profile and pick a
``sites_key`` from the built-in catalogs. On `[ Save ]` the spec is
written to ``USER_PROFILES_DIR`` and a callback notifies the parent
MirageView so it can adopt the new spec as active.

Fields that aren't usefully user-editable in a TUI (the full UA
pool, the per-locale Accept-Language map) are inherited from the
seed profile or fall back to the standard defaults. The user can
edit them by hand in the resulting TOML if they really want.
"""
from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Input, Static

from babel import theme

from tools.mirage.profile import (
    ProfileSpec, _ACCEPT_LANGUAGE, _COMMON_UAS, save_user_profile,
)
from tools.mirage.sites import PROFILE_SITES


class MirageProfileEditView(Container):
    """Editor for a MIRAGE profile. Saves to USER_PROFILES_DIR."""

    DEFAULT_CSS = f"""
    MirageProfileEditView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: auto;
        width: 100%;
        padding: 1 2;
        border: solid {theme.GREEN_DEEP};
        margin-top: 1;
    }}
    MirageProfileEditView .title {{
        color: {theme.CYAN};
        text-style: bold;
    }}
    MirageProfileEditView .hint {{
        color: {theme.MUTE};
        text-style: dim italic;
    }}
    MirageProfileEditView .field-label {{
        color: {theme.GREEN};
        margin-top: 1;
    }}
    MirageProfileEditView .row {{
        height: auto;
        width: 100%;
    }}
    MirageProfileEditView .row Input {{
        width: 1fr;
        margin-right: 1;
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    MirageProfileEditView .status {{ color: {theme.MUTE}; }}
    MirageProfileEditView .status.err {{ color: {theme.RED}; }}
    MirageProfileEditView .status.ok {{ color: {theme.GREEN}; }}
    MirageProfileEditView #profile-buttons {{
        height: auto;
        margin-top: 1;
    }}
    MirageProfileEditView #profile-buttons Button {{
        margin-right: 1;
    }}
    """

    BINDINGS = [
        Binding("escape", "close", "back", show=True, priority=True),
    ]

    can_focus = True

    def __init__(
        self,
        seed: ProfileSpec | None,
        on_saved: Callable[[ProfileSpec], None],
    ) -> None:
        super().__init__()
        self._seed = seed
        self._on_saved = on_saved
        self._inputs: dict[str, Input] = {}
        self._status: Static | None = None
        self._sites_cycle_index = 0
        # Pre-fill defaults from the seed (or sensible blanks).
        s = seed
        self._defaults = {
            "name": s.name if s else "",
            "description": s.description if s else "",
            "rpm_low": str(s.rpm_typical[0]) if s else "5",
            "rpm_high": str(s.rpm_typical[1]) if s else "12",
            "dwell_low": str(s.dwell_seconds[0]) if s else "5.0",
            "dwell_high": str(s.dwell_seconds[1]) if s else "12.0",
            "sites_key": s.sites_key if s else "office_worker",
        }

    def compose(self) -> ComposeResult:
        title = "EDIT PROFILE" if self._seed is not None else "NEW PROFILE"
        yield Static(f"  {title}", classes="title")
        yield Static(
            "  Tweak the timing window and site catalog. accept_language "
            "and user_agents inherit from the seed (edit the TOML for "
            "fine control).",
            classes="hint",
        )

        yield Static("  name (saved as ~/.babel/mirage_profiles/<name>.toml):",
                     classes="field-label")
        n = Input(value=self._defaults["name"], placeholder="my_profile",
                  id="pe-name")
        self._inputs["name"] = n
        yield n

        yield Static("  description (one-line summary):",
                     classes="field-label")
        d = Input(value=self._defaults["description"],
                  placeholder="what this profile pretends to be",
                  id="pe-description")
        self._inputs["description"] = d
        yield d

        yield Static("  rpm_typical  (low, high — requests per minute):",
                     classes="field-label")
        with Horizontal(classes="row"):
            for key, ph in (("rpm_low", "low"), ("rpm_high", "high")):
                ip = Input(value=self._defaults[key], placeholder=ph,
                           id=f"pe-{key}")
                self._inputs[key] = ip
                yield ip

        yield Static("  dwell_seconds  (low, high — seconds between fetches):",
                     classes="field-label")
        with Horizontal(classes="row"):
            for key, ph in (("dwell_low", "low"), ("dwell_high", "high")):
                ip = Input(value=self._defaults[key], placeholder=ph,
                           id=f"pe-{key}")
                self._inputs[key] = ip
                yield ip

        yield Static(
            f"  sites_key  (one of: {', '.join(sorted(PROFILE_SITES))}):",
            classes="field-label",
        )
        sk = Input(value=self._defaults["sites_key"],
                   placeholder="office_worker", id="pe-sites_key")
        self._inputs["sites_key"] = sk
        yield sk

        with Horizontal(id="profile-buttons"):
            yield Button("[ Save ]", id="pe-save", variant="success")
            yield Button("[ Cancel ]", id="pe-cancel")

        self._status = Static("", classes="status")
        yield self._status

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "pe-save":
            self._save()
        elif bid == "pe-cancel":
            self.action_close()

    def _save(self) -> None:
        try:
            name = self._inputs["name"].value.strip()
            if not name:
                self._set_status("name is required", "err")
                return
            sites_key = self._inputs["sites_key"].value.strip()
            if sites_key not in PROFILE_SITES:
                self._set_status(
                    f"unknown sites_key {sites_key!r}; pick one of "
                    f"{sorted(PROFILE_SITES)}", "err",
                )
                return

            rpm_low = int(self._inputs["rpm_low"].value)
            rpm_high = int(self._inputs["rpm_high"].value)
            dwell_low = float(self._inputs["dwell_low"].value)
            dwell_high = float(self._inputs["dwell_high"].value)
        except (KeyError, ValueError) as e:
            self._set_status(f"invalid input: {e}", "err")
            return

        if rpm_low > rpm_high:
            self._set_status("rpm low must be <= high", "err")
            return
        if dwell_low > dwell_high:
            self._set_status("dwell low must be <= high", "err")
            return

        # Inherit accept_language and user_agents from the seed if
        # present, otherwise use the standard defaults.
        accept_language = (
            dict(self._seed.accept_language) if self._seed
            else dict(_ACCEPT_LANGUAGE)
        )
        user_agents = (
            tuple(self._seed.user_agents) if self._seed
            else _COMMON_UAS
        )

        spec = ProfileSpec(
            name=name,
            description=self._inputs["description"].value.strip(),
            rpm_typical=(rpm_low, rpm_high),
            dwell_seconds=(dwell_low, dwell_high),
            sites_key=sites_key,
            accept_language=accept_language,
            user_agents=user_agents,
        )
        try:
            path = save_user_profile(spec)
        except Exception as e:
            self._set_status(
                f"save failed: {type(e).__name__}: {e}", "err",
            )
            return
        self._set_status(f"saved -> {path}", "ok")
        try:
            self._on_saved(spec)
        finally:
            self.action_close()

    def action_close(self) -> None:
        try:
            self.remove()
        except Exception:
            pass

    def _set_status(self, text: str, cls: str) -> None:
        if self._status is None:
            return
        self._status.update(text)
        self._status.set_classes(f"status {cls}".strip())


__all__ = ["MirageProfileEditView"]
