"""Session-shape helpers for the MIRAGE engine.

Two responsibilities live here, both keep their hands off real
clocks so tests can drive them deterministically:

  * ``zipf_draw`` -- pick a site from a per-profile catalog using
    a 1/rank weighted draw.  The caller supplies the ``random.Random``
    instance, which gives tests a seed and the engine its production
    randomness.
  * ``dwell_for`` -- compute the next inter-request sleep from a
    profile's ``dwell_seconds`` range, *combined with* the user's
    rate ceiling.  The engine always honours whichever floor is
    higher: the profile-preferred dwell or the rate-ceiling-imposed
    minimum.

The token-bucket actually enforces the ceiling at request time;
``dwell_for`` is the *planner's* hint about how long to wait.  The
two together produce a stream whose average rate sits inside the
profile envelope and never exceeds the user cap.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from tools.mirage.profile import ProfileSpec


@dataclass(frozen=True)
class PlannedFetch:
    """One scheduled outgoing request, before the token bucket weighs in."""

    host: str
    path: str
    rank: int


def _weights(catalog: tuple[tuple[str, str, int], ...]) -> list[float]:
    return [1.0 / rank for _h, _p, rank in catalog]


def zipf_draw(
    catalog: tuple[tuple[str, str, int], ...],
    rng: random.Random,
) -> PlannedFetch:
    """Pick a (host, path) from ``catalog`` weighted by ``1/rank``."""
    if not catalog:
        raise ValueError("zipf_draw: empty catalog")
    weights = _weights(catalog)
    # ``random.Random.choices`` returns a single-element list when k=1.
    host, path, rank = rng.choices(catalog, weights=weights, k=1)[0]
    return PlannedFetch(host=host, path=path, rank=rank)


def dwell_for(
    profile: ProfileSpec,
    rate_rpm_cap: int,
    rng: random.Random,
) -> float:
    """Inter-request sleep in seconds.

    The dwell is the *larger* of:
      * a uniform draw from the profile's ``dwell_seconds`` range, and
      * ``60 / rate_rpm_cap`` -- the rate ceiling expressed as a
        minimum gap.

    This means a profile that prefers 3-8 second dwells but is run
    with ``--rate-rpm 6`` will average 10s between requests, not 5s.
    The user's cap always wins on the upper bound of frequency.
    """
    low, high = profile.dwell_seconds
    if high < low:
        low, high = high, low
    natural = rng.uniform(low, high)
    cap_floor = 60.0 / max(1, rate_rpm_cap)
    return max(natural, cap_floor)


def jitter_ms(rng: random.Random, base_ms: float, spread_ms: float) -> float:
    """Small additive jitter for engine sleeps.

    Keeps the engine from aligning to integer multiples of the
    profile dwell, which would itself be a fingerprint.  Positive
    spread only -- we never sleep less than the planner asked for,
    because that would erode the rate cap.
    """
    return base_ms + rng.uniform(0.0, max(0.0, spread_ms))


__all__ = ["PlannedFetch", "zipf_draw", "dwell_for", "jitter_ms"]
