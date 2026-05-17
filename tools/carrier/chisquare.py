"""Chi-square LSB-tampering detector.

Background: LSB embedding flips the lowest bit of each modified
sample. Over the value space, each pair ``(2k, 2k+1)`` is two
samples that differ only in their LSB. Untampered content (sensor
noise, encoder rounding) has unequal counts in each pair; LSB
embedding into a meaningful fraction of samples drives the counts
toward equality.

The test statistic, for paired counts ``a, b`` with expected
``e = (a+b)/2``::

    chi2 = sum over pairs of  (a - e)^2 / e  +  (b - e)^2 / e
         = sum over pairs of  (a - b)^2 / (2 (a + b))

The degrees of freedom equals the number of non-empty pairs. The
p-value is approximated via Wilson-Hilferty (good for df >= 30).
For small df the approximation overshoots; CARRIER uses it only
as a coarse "this cover looks tampered" gate, not as a publication
statistic.

This module is stdlib-only on purpose: pulling scipy for one CDF
call would dwarf every other dependency we have.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class ChiSquareResult:
    chi2: float          # the chi-square statistic
    df: int              # degrees of freedom (non-empty pairs)
    p_value: float       # P(X >= chi2) under chi2(df)
    n_samples: int       # number of bytes / samples consumed


def chi_square(samples: bytes | bytearray | memoryview) -> ChiSquareResult:
    """Compute the LSB chi-square statistic over ``samples``.

    Each byte counts as one sample; for multi-byte audio formats
    the caller should pass only the LSB-bearing byte of each frame
    (see ``core.wav`` for the WAV adapter).
    """
    if len(samples) < 32:
        return ChiSquareResult(chi2=0.0, df=0, p_value=1.0,
                               n_samples=len(samples))

    counts = [0] * 256
    for b in samples:
        counts[b] += 1

    chi2 = 0.0
    df = 0
    for k in range(0, 256, 2):
        a, b = counts[k], counts[k + 1]
        total = a + b
        if total == 0:
            continue
        df += 1
        diff = a - b
        chi2 += (diff * diff) / (2.0 * total)

    return ChiSquareResult(
        chi2=chi2, df=df,
        p_value=_chi2_sf(chi2, df) if df > 0 else 1.0,
        n_samples=len(samples),
    )


def _chi2_sf(x: float, df: int) -> float:
    """Survival function P(X >= x) for chi-square(df).

    Wilson-Hilferty cube-root normal approximation. For df >= 30
    the error is < 0.005 in the tails we care about. For smaller
    df it's noisier; CARRIER only checks a coarse threshold.
    """
    if df <= 0 or x <= 0:
        return 1.0
    # Wilson-Hilferty: Z = ((X/df)**(1/3) - (1 - 2/(9 df))) / sqrt(2/(9 df))
    a = (x / df) ** (1.0 / 3.0)
    mu = 1.0 - 2.0 / (9.0 * df)
    sigma = math.sqrt(2.0 / (9.0 * df))
    z = (a - mu) / sigma
    return 0.5 * math.erfc(z / math.sqrt(2.0))


__all__ = ["ChiSquareResult", "chi_square"]
