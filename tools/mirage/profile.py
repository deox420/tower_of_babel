"""MIRAGE behavioural profiles.

A profile is a static, version-pinned blueprint for what cover
traffic should look like.  It carries:

* ``rpm_typical`` -- the (low, high) request-rate window the engine
  *prefers*.  The actual rate is clamped further down by the user's
  ``--rate-rpm`` ceiling, so a profile that "wants" 20 rpm but runs
  with ``--rate-rpm 10`` will obey the ceiling.
* ``dwell_seconds`` -- the (low, high) range from which the engine
  uniformly draws between consecutive fetches.  Inverse of rpm.
* ``sites_key`` -- the key into ``tools/mirage/sites.py``
  PROFILE_SITES that selects the per-profile catalog.
* ``accept_language`` -- locale -> ``Accept-Language`` header value
  the engine sends with each request.
* ``user_agents`` -- a small pool of plausible UA strings rotated
  per request.  Public values; do NOT add anything fingerprinting.

The four shipped profiles match MASTER.md Section 7.5.  Adding a
profile is a one-tuple entry plus a ``PROFILE_SITES`` row in
``sites.py``; tests guard the registry shape (see
``pentest/mirage/test_profile_registry.py``).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


# Locales recognised by both MASK and MIRAGE.  Kept in sync with
# ``tools.mask.alias.LOCALES`` deliberately -- the user expects the
# locale string to mean the same thing across the suite.
LOCALES: tuple[str, ...] = ("en", "es", "fr", "de", "neutral")


# Where user-saved profiles live. One TOML file per profile, named
# after `spec.name`. The directory is created on first save.
USER_PROFILES_DIR = Path.home() / ".babel" / "mirage_profiles"


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    description: str
    rpm_typical: tuple[int, int]
    dwell_seconds: tuple[float, float]
    sites_key: str
    accept_language: dict[str, str]
    user_agents: tuple[str, ...]

    def rpm_clamped(self, cap_rpm: int) -> tuple[int, int]:
        """Profile's preferred rpm range, intersected with the user cap."""
        low = max(1, min(self.rpm_typical[0], cap_rpm))
        high = max(low, min(self.rpm_typical[1], cap_rpm))
        return (low, high)

    def language_for(self, locale: str) -> str:
        return self.accept_language.get(locale, self.accept_language.get("en", "en-US"))


# A small, public, *plausibly browser-ish* UA pool.  These are all
# common values that show up in real telemetry; the goal is "boring"
# not "evasive".  Update only when a UA family obviously stops being
# representative; do not chase the latest patch number.
_COMMON_UAS: tuple[str, ...] = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 "
    "Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
)


_ACCEPT_LANGUAGE: dict[str, str] = {
    "en":      "en-US,en;q=0.9",
    "es":      "es-ES,es;q=0.9,en;q=0.5",
    "fr":      "fr-FR,fr;q=0.9,en;q=0.5",
    "de":      "de-DE,de;q=0.9,en;q=0.5",
    "neutral": "en-US,en;q=0.5",
}


PROFILES: dict[str, ProfileSpec] = {
    "office_worker": ProfileSpec(
        name="office_worker",
        description="news, search, mail web-UIs, weather, maps",
        rpm_typical=(6, 12),
        dwell_seconds=(5.0, 12.0),
        sites_key="office_worker",
        accept_language=dict(_ACCEPT_LANGUAGE),
        user_agents=_COMMON_UAS,
    ),
    "developer": ProfileSpec(
        name="developer",
        description="docs, package indexes, repo READMEs",
        rpm_typical=(8, 20),
        dwell_seconds=(3.0, 8.0),
        sites_key="developer",
        accept_language=dict(_ACCEPT_LANGUAGE),
        user_agents=_COMMON_UAS,
    ),
    "casual_browser": ProfileSpec(
        name="casual_browser",
        description="news, video front pages, social public",
        rpm_typical=(4, 10),
        dwell_seconds=(6.0, 18.0),
        sites_key="casual_browser",
        accept_language=dict(_ACCEPT_LANGUAGE),
        user_agents=_COMMON_UAS,
    ),
    "researcher": ProfileSpec(
        name="researcher",
        description="wikipedia, journal abstracts, archives",
        rpm_typical=(3, 8),
        dwell_seconds=(8.0, 22.0),
        sites_key="researcher",
        accept_language=dict(_ACCEPT_LANGUAGE),
        user_agents=_COMMON_UAS,
    ),
}


_BUILTIN_ORDER = ("office_worker", "developer", "casual_browser", "researcher")


def _spec_from_dict(data: dict) -> ProfileSpec:
    """Build a ProfileSpec from a TOML dict. Raises ValueError on bad input."""
    try:
        return ProfileSpec(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            rpm_typical=(int(data["rpm_typical"][0]),
                         int(data["rpm_typical"][1])),
            dwell_seconds=(float(data["dwell_seconds"][0]),
                           float(data["dwell_seconds"][1])),
            sites_key=str(data["sites_key"]),
            accept_language=dict(
                data.get("accept_language", _ACCEPT_LANGUAGE)
            ),
            user_agents=tuple(
                str(u) for u in data.get("user_agents", _COMMON_UAS)
            ),
        )
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ValueError(f"malformed profile TOML: {e}") from e


def _spec_to_dict(spec: ProfileSpec) -> dict:
    return {
        "name": spec.name,
        "description": spec.description,
        "rpm_typical": list(spec.rpm_typical),
        "dwell_seconds": list(spec.dwell_seconds),
        "sites_key": spec.sites_key,
        # accept_language and user_agents are persisted so a profile
        # is fully self-contained when the user edits them later.
        "accept_language": dict(spec.accept_language),
        "user_agents": list(spec.user_agents),
    }


def load_user_profiles() -> list[ProfileSpec]:
    """Read user-saved profiles from USER_PROFILES_DIR.

    Returns an empty list when the directory doesn't exist or is
    empty. Files that fail to parse are skipped silently (a future
    revision could surface a warning to the UI).
    """
    if not USER_PROFILES_DIR.is_dir():
        return []
    specs: list[ProfileSpec] = []
    for path in sorted(USER_PROFILES_DIR.glob("*.toml")):
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
            specs.append(_spec_from_dict(data))
        except (OSError, tomllib.TOMLDecodeError, ValueError):
            continue
    return specs


def save_user_profile(spec: ProfileSpec) -> Path:
    """Persist ``spec`` to ``USER_PROFILES_DIR/<spec.name>.toml``.

    Writes a hand-rolled minimal TOML (stdlib tomllib only reads,
    doesn't write). The directory is created on first save.
    """
    USER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_PROFILES_DIR / f"{spec.name}.toml"
    lines: list[str] = [
        f'name = "{_toml_escape(spec.name)}"',
        f'description = "{_toml_escape(spec.description)}"',
        f"rpm_typical = [{spec.rpm_typical[0]}, {spec.rpm_typical[1]}]",
        f"dwell_seconds = [{spec.dwell_seconds[0]}, {spec.dwell_seconds[1]}]",
        f'sites_key = "{_toml_escape(spec.sites_key)}"',
        "",
        "[accept_language]",
    ]
    for k, v in spec.accept_language.items():
        lines.append(f'{k} = "{_toml_escape(v)}"')
    lines.append("")
    lines.append("user_agents = [")
    for ua in spec.user_agents:
        lines.append(f'  "{_toml_escape(ua)}",')
    lines.append("]")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def list_profiles() -> list[ProfileSpec]:
    """Built-in profiles followed by user-saved ones (sorted by name)."""
    return [PROFILES[k] for k in _BUILTIN_ORDER] + load_user_profiles()


def get_profile(name: str) -> ProfileSpec:
    """Lookup by name across built-in + user profiles."""
    if name in PROFILES:
        return PROFILES[name]
    for spec in load_user_profiles():
        if spec.name == name:
            return spec
    raise ValueError(
        f"unknown MIRAGE profile {name!r}; "
        f"known: {sorted(PROFILES)} + user profiles in {USER_PROFILES_DIR}"
    )


def is_user_profile(name: str) -> bool:
    """True if ``name`` corresponds to a user-saved profile (not built-in)."""
    return name not in PROFILES


__all__ = [
    "ProfileSpec", "PROFILES", "LOCALES", "USER_PROFILES_DIR",
    "list_profiles", "get_profile", "is_user_profile",
    "load_user_profiles", "save_user_profile",
]
