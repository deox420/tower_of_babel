"""Multi-scheme invite-link codec.

MASTER.md Section 5.6 promises a single codec the suite uses for
``void://`` (chat invite), ``carrier://`` (extraction hint), and
``mask://`` (disposable identity bundle). This module is that
codec.

The encoding is uniform across schemes:

    <scheme>://base64url( canonical_json(body) )

``canonical_json`` means ``json.dumps(body, sort_keys=True,
separators=(',', ':'))`` -- no whitespace, deterministic key order
-- so two encodings of the same body hash to byte-identical URLs.
The base64url is unpadded (`=` stripped on encode, re-padded on
decode) so the URLs survive copy-paste through chat clients that
treat `=` as significant.

Each scheme has a per-scheme schema in ``SCHEMAS``. Decoding rejects
bodies whose top-level keys are not a subset of the scheme's
declared keys. We do **not** type-check values here -- the calling
tool owns the deeper validation -- but the key-set check defangs
the obvious "wrong scheme pasted into the wrong tool" footgun.

Tools must not roll their own ``<scheme>://`` encoder. If a new
scheme is added, extend ``SCHEMES`` and ``SCHEMAS`` here, write
the tool-side helper in ``tools/<name>/link.py``, and add a test
under ``pentest/babel/test_invite_codec.py``.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any


SCHEME_VOID = "void://"
SCHEME_CARRIER = "carrier://"
SCHEME_MASK = "mask://"

SCHEMES = (SCHEME_VOID, SCHEME_CARRIER, SCHEME_MASK)


# Declared top-level keys per scheme. Decoding rejects unknown keys.
# Tools may also enforce required keys; this module only enforces the
# superset.
SCHEMAS: dict[str, frozenset[str]] = {
    SCHEME_VOID: frozenset({
        "v", "onion", "room", "password", "ik", "spk", "spk_sig", "opks",
        "ts",
    }),
    SCHEME_CARRIER: frozenset({
        "v", "fmt", "salt", "nonce", "size", "ts",
    }),
    SCHEME_MASK: frozenset({
        "alias", "bio", "avatar_sha", "mail_handle", "ts",
    }),
}


class InvalidInvite(ValueError):
    """Raised when a string is malformed, schema-violating, or unknown scheme."""


@dataclass(frozen=True)
class InviteLink:
    """A decoded invite link."""

    scheme: str            # one of SCHEMES, includes the trailing "://"
    body: dict[str, Any]   # the json-decoded payload
    raw: str               # the original URL as passed in


def encode(scheme: str, body: dict[str, Any]) -> str:
    """Build a ``<scheme>://base64url(canonical_json(body))`` URL.

    Raises ``InvalidInvite`` for unknown schemes or bodies with keys
    outside the per-scheme schema. Sorted-key JSON guarantees that
    two callers with the same body produce byte-identical URLs.
    """
    if scheme not in SCHEMES:
        raise InvalidInvite(f"unknown scheme: {scheme!r}")
    allowed = SCHEMAS[scheme]
    extra = set(body.keys()) - allowed
    if extra:
        raise InvalidInvite(
            f"{scheme} body has keys outside schema: {sorted(extra)}"
        )
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    payload = base64.urlsafe_b64encode(canonical).rstrip(b"=").decode("ascii")
    return f"{scheme}{payload}"


def decode(s: str) -> InviteLink:
    """Parse a ``<scheme>://...`` URL into an ``InviteLink``.

    Raises ``InvalidInvite`` for unknown schemes, malformed base64,
    non-json bodies, or bodies whose keys are not a subset of the
    scheme's schema.
    """
    if not isinstance(s, str):
        raise InvalidInvite(f"expected str, got {type(s).__name__}")
    text = s.strip()
    scheme = _detect_scheme(text)
    if scheme is None:
        raise InvalidInvite(f"unknown or missing scheme in {text[:32]!r}")
    payload = text[len(scheme):]
    # Re-pad base64url to a multiple of 4 before decoding.
    pad = (-len(payload)) % 4
    try:
        raw = base64.urlsafe_b64decode(payload + ("=" * pad))
    except (ValueError, TypeError) as e:
        raise InvalidInvite(f"{scheme} base64 decode failed: {e}") from e
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise InvalidInvite(f"{scheme} body is not utf-8 json: {e}") from e
    if not isinstance(body, dict):
        raise InvalidInvite(f"{scheme} body must be a json object")
    allowed = SCHEMAS[scheme]
    extra = set(body.keys()) - allowed
    if extra:
        raise InvalidInvite(
            f"{scheme} body has keys outside schema: {sorted(extra)}"
        )
    return InviteLink(scheme=scheme, body=body, raw=text)


def looks_like(s: str) -> str | None:
    """Return the matching scheme if ``s`` starts with one, else ``None``.

    The babel lobby's paste-autofill calls this on every clipboard
    paste so it can route to the right tool. Does not parse the body
    -- a positive answer only means "the prefix matches"; call
    ``decode()`` to actually consume the link.
    """
    if not isinstance(s, str):
        return None
    return _detect_scheme(s.strip())


def _detect_scheme(s: str) -> str | None:
    for scheme in SCHEMES:
        if s.startswith(scheme):
            return scheme
    return None


__all__ = [
    "SCHEME_VOID", "SCHEME_CARRIER", "SCHEME_MASK", "SCHEMES",
    "SCHEMAS",
    "InvalidInvite", "InviteLink",
    "encode", "decode", "looks_like",
]
