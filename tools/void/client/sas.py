"""Short Authentication Strings using the PGP word list.

The SAS is derived from both public keys. As long as Alice and Bob both
hash min(pubA, pubB) || max(pubA, pubB), the result is identical and
order-independent, and both can read it aloud to compare.
"""
from __future__ import annotations

import hashlib

from .sas_wordlist import bytes_to_words

SAS_WORD_COUNT = 5


def sas_hash(pub_a: bytes, pub_b: bytes) -> bytes:
    lo, hi = (pub_a, pub_b) if pub_a <= pub_b else (pub_b, pub_a)
    return hashlib.sha256(lo + hi).digest()


def sas_words(pub_a: bytes, pub_b: bytes, n: int = SAS_WORD_COUNT) -> list[str]:
    h = sas_hash(pub_a, pub_b)
    return bytes_to_words(h[:n])
