"""``mask://`` codec -- thin wrapper over ``shared.link.invite``.

Per MASTER.md Section 5.6, every scheme lives in the shared codec.
This module exposes the two operations MASK actually performs --
``build(identity)`` and ``parse(url)`` -- so callers do not have to
remember the scheme constant.
"""
from __future__ import annotations

from shared.link.invite import SCHEME_MASK, decode, encode

from tools.mask.bundle import Identity, from_dict


def build(identity: Identity) -> str:
    """Return the canonical ``mask://...`` URL for ``identity``."""
    return encode(SCHEME_MASK, identity.to_dict())


def parse(url: str) -> Identity:
    """Decode a ``mask://`` URL into an ``Identity``.

    Raises ``shared.link.invite.InvalidInvite`` for malformed input.
    The avatar PNG is regenerated locally from the alias handle (the
    wire form carries only the SHA-256 of the SVG, not the pixels).
    """
    link = decode(url)
    if link.scheme != SCHEME_MASK:
        from shared.link.invite import InvalidInvite
        raise InvalidInvite(f"expected mask:// scheme, got {link.scheme}")
    return from_dict(link.body)


__all__ = ["build", "parse"]
