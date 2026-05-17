"""Invite links: ``void://...`` self-contained one-paste join string.

The encoded payload is base64url(JSON {onion, room, password, [fp]}).
We deliberately keep the contents in plaintext after the base64
decoding — the link IS the secret. Anyone who sees the link can join,
so it must be shared over a trusted side channel just like the
three fields would be.

The optional ``fp`` (8 hex chars of a peer's IK) lets users pin
who they expect; if present, the client refuses to render messages
from any other identity until SAS is re-run.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Optional


SCHEME = "void://"

# v3 onions are exactly 56 lowercase base32 chars (v2 was removed in Tor 0.4.7).
_ONION_RE = re.compile(r"^[a-z2-7]{56}\.onion(?::\d+)?$")


@dataclass
class Invite:
    onion: str          # e.g. "xxxxx.onion:8765"
    room: str
    password: str
    expected_fp: Optional[str] = None


def encode(invite: Invite) -> str:
    if ":" not in invite.onion:
        onion = invite.onion + ":8765"
    else:
        onion = invite.onion
    payload = {"o": onion, "r": invite.room, "p": invite.password}
    if invite.expected_fp:
        payload["fp"] = invite.expected_fp
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return SCHEME + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode(s: str) -> Invite | None:
    s = s.strip()
    if not s.startswith(SCHEME):
        return None
    body = s[len(SCHEME):]
    # Re-add base64 padding.
    body += "=" * (-len(body) % 4)
    try:
        raw = base64.urlsafe_b64decode(body.encode("ascii"))
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    onion = obj.get("o")
    room = obj.get("r")
    pw = obj.get("p")
    if not isinstance(onion, str) or not isinstance(room, str) or not isinstance(pw, str):
        return None
    # Strip any URL prefix the user may have pasted by accident.
    for pfx in ("ws://", "wss://", "http://", "https://"):
        if onion.startswith(pfx):
            onion = onion[len(pfx):]
    # Canonical onions are lowercase; reject mixed-case as a transcription error.
    if not _ONION_RE.match(onion):
        return None
    fp = obj.get("fp")
    if fp is not None and not (isinstance(fp, str) and re.fullmatch(r"[0-9a-fA-F]{8}", fp)):
        fp = None
    return Invite(onion=onion, room=room, password=pw, expected_fp=fp)
