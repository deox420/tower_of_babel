"""Generate-identity orchestration.

Walks the four phases (alias -> avatar -> mail -> bundle) and emits
a ``Step`` callback per transition so the TUI's ``StepIndicator``
can repaint as real work finishes. The CLI's non-interactive path
re-uses the same orchestration and ignores the callback.

Failure modes:

- ``TorRequired``    -- propagated; the CLI maps to exit 5.
- ``MailUnavailable`` -- swallowed if ``--no-mail`` was passed
                          (treated as the user opting out); otherwise
                          propagated to the caller, who returns exit 4
                          if no fallback succeeded.

The pipeline is async because both mail adapters are. Everything
else (alias, avatar, bundle assembly) is synchronous and runs in
the event loop's thread.
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from shared.ui.step_indicator import Step

from tools.mask.alias import (
    LOCALES, PROFILES, generate_alias, generate_bio,
)
from tools.mask.avatar import generate_avatar
from tools.mask.bundle import Identity, _round_ts
from tools.mask.mail import (
    MailHandle, MailUnavailable, TorRequired, acquire_handle,
)


StepCallback = Callable[[int, Step], None]


@dataclass
class GenerateOpts:
    """User-facing knobs for one ``generate_identity`` call."""

    locale: str = "en"
    profile: str = "default"
    use_tor: bool = True
    fetch_mail: bool = True
    seed: bytes | None = None    # tests pass a fixed seed for determinism


PHASE_LABELS = ("alias", "avatar", "mail", "bundle")


def initial_steps(opts: GenerateOpts) -> list[Step]:
    """Return the initial ``[pending, pending, pending, pending]`` block.

    Callers usually drop the ``mail`` phase when ``fetch_mail=False`` so
    the UI does not show an obviously-skipped step.
    """
    steps = [Step(label, "pending") for label in PHASE_LABELS]
    if not opts.fetch_mail:
        steps = [s for s in steps if s.label != "mail"]
    return steps


async def generate_identity(
    opts: GenerateOpts,
    on_step: StepCallback | None = None,
) -> Identity:
    """Produce a coherent ``Identity`` from ``opts``.

    Phases:
      0: alias  (synchronous)
      1: avatar (synchronous; Pillow render)
      2: mail   (async; mail.tm -> guerrillamail fallback)
      3: bundle (synchronous; assemble the Identity dataclass)

    If ``opts.fetch_mail`` is False, phase 2 is skipped and the
    callback's indices drop by one for phases 3 onward.
    """
    if opts.locale not in LOCALES:
        raise ValueError(f"unknown locale: {opts.locale!r}")
    if opts.profile not in PROFILES:
        raise ValueError(f"unknown profile: {opts.profile!r}")

    rng = random.Random(opts.seed) if opts.seed else random.Random(os.urandom(16))
    cb = on_step or (lambda _i, _s: None)

    idx = 0
    cb(idx, Step("alias", "active"))
    alias = generate_alias(opts.locale, opts.profile, rng)
    bio = generate_bio(alias, rng)
    cb(idx, Step("alias", "done", detail=alias.handle))
    idx += 1

    cb(idx, Step("avatar", "active"))
    avatar = generate_avatar(alias.handle.encode("utf-8"))
    cb(idx, Step("avatar", "done", detail=f"sha256:{avatar.sha256[:8]}"))
    idx += 1

    mail: MailHandle | None = None
    if opts.fetch_mail:
        cb(idx, Step("mail", "active"))
        try:
            mail = await acquire_handle(alias.handle, tor=opts.use_tor)
            cb(idx, Step("mail", "done", detail=f"{mail.provider} {mail.address}"))
        except TorRequired:
            cb(idx, Step("mail", "failed", detail="Tor SOCKS5 not reachable"))
            raise
        except MailUnavailable as e:
            cb(idx, Step("mail", "failed", detail=str(e)[:48]))
            # The caller decides whether this is fatal; we still
            # return an identity without a mail handle.
            mail = None
        idx += 1

    cb(idx, Step("bundle", "active"))
    identity = Identity(
        alias=alias, bio=bio, avatar=avatar, mail=mail,
        ts=_round_ts(int(time.time())),
    )
    cb(idx, Step("bundle", "done"))
    return identity


__all__ = ["GenerateOpts", "PHASE_LABELS",
           "initial_steps", "generate_identity", "StepCallback"]
