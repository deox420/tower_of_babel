"""Locale-coherent alias + bio generation.

Loads the per-locale JSON catalog at first use (`importlib.resources`
so editable installs and PyInstaller bundles both find the data) and
draws a given name, family name, and bio fragment from it.

The handle is the lowercase, ASCII-folded `given_family` string with
optional digit suffix to defang the obvious "common name" collision.
The handle is the **only** part that flows into network requests
(mail.tm address), so it must round-trip through ASCII without a
diacritic in sight.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from importlib import resources
from random import Random
from typing import Any


LOCALES = ("en", "es", "fr", "de", "neutral")
PROFILES = ("default", "writer", "trader", "researcher")


@dataclass(frozen=True)
class AliasSpec:
    """A locale-coherent disposable alias.

    ``handle`` is the network-safe form: lowercase, ASCII-folded, no
    whitespace, optional 2-digit suffix for collision avoidance. It is
    what we feed mail.tm.
    """

    given: str
    family: str
    handle: str
    locale: str
    profile: str

    def display(self) -> str:
        return f"{self.given} {self.family}"


_CATALOG_CACHE: dict[str, dict[str, Any]] = {}


def _load_catalog(locale: str) -> dict[str, Any]:
    if locale not in LOCALES:
        raise ValueError(f"unknown locale: {locale!r}; choose from {LOCALES}")
    cached = _CATALOG_CACHE.get(locale)
    if cached is not None:
        return cached
    pkg = resources.files("tools.mask.data")
    raw = (pkg / f"{locale}.json").read_text(encoding="utf-8")
    catalog = json.loads(raw)
    _CATALOG_CACHE[locale] = catalog
    return catalog


def _ascii_fold(s: str) -> str:
    """Strip diacritics so handles like `Munoz` become `munoz`."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).encode(
        "ascii", "ignore"
    ).decode("ascii")


def _handle_from(given: str, family: str, rng: Random) -> str:
    """Build a network-safe handle from given + family.

    Lowercase, ASCII-folded, spaces -> underscore. With probability ~1/3
    a two-digit suffix is appended to defang very common combinations.
    The suffix is drawn from ``rng`` so callers can reproduce it from
    a deterministic seed.
    """
    base = f"{_ascii_fold(given)}_{_ascii_fold(family)}".lower()
    base = "_".join(base.split())   # collapse internal whitespace
    base = "".join(c for c in base if c.isalnum() or c == "_")
    if rng.random() < 0.33:
        base = f"{base}{rng.randint(10, 99)}"
    return base


def generate_alias(locale: str, profile: str, rng: Random) -> AliasSpec:
    """Draw a fresh ``AliasSpec`` from the locale catalog.

    ``rng`` is the caller's ``random.Random`` instance. MASK seeds it
    from ``os.urandom`` per generation; tests pass a seeded one for
    determinism. ``profile`` is validated but only used by the bio
    templater downstream (alias picking is profile-agnostic).
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile!r}; choose from {PROFILES}")
    catalog = _load_catalog(locale)
    given = rng.choice(catalog["given"])
    family = rng.choice(catalog["family"])
    handle = _handle_from(given, family, rng)
    return AliasSpec(
        given=given, family=family, handle=handle,
        locale=locale, profile=profile,
    )


def generate_bio(alias: AliasSpec, rng: Random) -> str:
    """Compose a 2-3 line bio for ``alias`` from its locale catalog.

    Picks one fragment from the profile-tagged pool. When that pool
    is short or the profile is ``default``, may also append one
    ``interests`` clause for variety; both choices use the same
    ``rng`` so the output is reproducible from the seed.
    """
    catalog = _load_catalog(alias.locale)
    pool_key = f"bio_{alias.profile}"
    pool = catalog.get(pool_key) or catalog.get("bio_default") or [""]
    line = rng.choice(pool)
    if rng.random() < 0.4 and catalog.get("interests"):
        n = min(2, len(catalog["interests"]))
        clauses = rng.sample(catalog["interests"], n)
        # Keep bio under ~240 chars; one clause for short pools, two
        # for the longer ones.
        if len(line) + len(" / ".join(clauses)) + 6 < 240:
            line = f"{line} ({', '.join(clauses)})"
    return line


__all__ = ["AliasSpec", "LOCALES", "PROFILES",
           "generate_alias", "generate_bio"]
