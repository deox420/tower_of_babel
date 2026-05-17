"""Temp-mail adapters.

Two providers, same contract:

- ``mail.tm``    -- preferred, JSON REST, supports custom usernames.
- ``guerrillamail`` -- fallback, JSON REST, addresses are auto-assigned.

Both adapters return the same ``MailHandle`` dataclass. MASK never
polls either inbox -- the user opens ``inbox_url`` in their own
browser. Polling would be detectable and adds nothing the user
cannot do themselves.

Tor SOCKS5 is mandatory by default (``tor=True``). The CLI's
``--clearnet`` path is the only way to set ``tor=False`` and it
requires an explicit ``--i-know`` flag (or interactive `y`
confirmation in the TUI).

The httpx client is created per-call so the proxy setting is
deterministic and there's no global state across acquisitions.
"""
from __future__ import annotations

import json
import os
import random
import secrets
from dataclasses import dataclass
from typing import Protocol


# Public REST endpoints. mail.tm and guerrillamail both have stable
# v1 APIs documented at the URLs below.
MAILTM_BASE = "https://api.mail.tm"
MAILTM_INBOX_BASE = "https://mail.tm"
GUERRILLA_BASE = "https://api.guerrillamail.com"
GUERRILLA_INBOX_BASE = "https://www.guerrillamail.com"

DEFAULT_TIMEOUT_S = 15.0


class MailUnavailable(RuntimeError):
    """Both primary and fallback providers failed or refused the request."""


class TorRequired(RuntimeError):
    """``tor=True`` was requested but no SOCKS5 port answered."""


@dataclass(frozen=True)
class MailHandle:
    """A disposable mail address handed back to the user.

    The user reads the inbox themselves at ``inbox_url``; MASK does
    not poll. ``provider`` is the adapter name; ``expires_in_s`` is
    advisory (mail.tm accounts are token-protected, guerrillamail
    sessions time out after ~60 minutes).
    """

    address: str
    provider: str
    inbox_url: str
    expires_in_s: int | None


class MailProvider(Protocol):
    name: str

    async def acquire(self, alias_handle: str, *, tor: bool) -> MailHandle:
        ...


# ---------------------------------------------------------------------------
# httpx client factory
# ---------------------------------------------------------------------------


def _build_client(*, tor: bool):
    """Create a per-call ``httpx.AsyncClient`` with the right proxy.

    The SOCKS5 port is auto-detected via ``shared.tor.socks_detect``;
    if none answer when ``tor=True``, raises ``TorRequired`` before
    any network call goes out.
    """
    try:
        import httpx
    except ImportError as e:    # pragma: no cover -- runtime dep
        raise RuntimeError(
            "httpx is required for MASK mail. "
            "Install with: pip install 'httpx[socks]>=0.27'"
        ) from e

    proxy = None
    if tor:
        from shared.tor.socks_detect import detect_socks_port
        port = detect_socks_port()
        if port is None:
            raise TorRequired(
                "Tor SOCKS5 required (default) but no port answered "
                "on 9050 / 9150 / 9151"
            )
        proxy = f"socks5h://127.0.0.1:{port}"
    return httpx.AsyncClient(
        proxy=proxy,
        timeout=DEFAULT_TIMEOUT_S,
        headers={"User-Agent": "babel-mask/0.6"},
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# mail.tm
# ---------------------------------------------------------------------------


class MailTm:
    """mail.tm REST adapter.

    Workflow:
      GET  /domains                        -> list of available domains
      POST /accounts {address, password}   -> creates the account
      Returned address is what we hand to the user.
    """

    name = "mail.tm"

    async def acquire(self, alias_handle: str, *, tor: bool) -> MailHandle:
        client = _build_client(tor=tor)
        try:
            domains_resp = await client.get(f"{MAILTM_BASE}/domains?page=1")
            domains_resp.raise_for_status()
            domains = self._parse_domains(domains_resp.text)
            if not domains:
                raise MailUnavailable("mail.tm returned zero domains")
            # Uniform random pick (rather than first-in-list) so MASK
            # does not fingerprint a per-install traversal order.
            domain = random.choice(domains)
            address = f"{alias_handle}@{domain}"
            # mail.tm requires a password; we generate one and discard
            # it -- the user reads the inbox via the web UI, which
            # would prompt for it, so we surface it inside the
            # MailHandle.expires/url is enough for the user to open
            # the web client. The password is included in inbox_url's
            # fragment so the user can paste it if needed.
            password = secrets.token_urlsafe(16)
            resp = await client.post(
                f"{MAILTM_BASE}/accounts",
                json={"address": address, "password": password},
            )
            if resp.status_code in (409, 422):
                # Username taken -- retry with a numeric suffix.
                address = f"{alias_handle}{secrets.randbelow(900) + 100}@{domain}"
                resp = await client.post(
                    f"{MAILTM_BASE}/accounts",
                    json={"address": address, "password": password},
                )
            resp.raise_for_status()
            return MailHandle(
                address=address,
                provider=self.name,
                inbox_url=f"{MAILTM_INBOX_BASE}/login#{address}:{password}",
                expires_in_s=None,
            )
        except Exception as e:
            if isinstance(e, (MailUnavailable, TorRequired)):
                raise
            raise MailUnavailable(f"mail.tm: {type(e).__name__}: {e}") from e
        finally:
            await client.aclose()

    @staticmethod
    def _parse_domains(text: str) -> list[str]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        # mail.tm wraps the collection in a HAL/JSON-LD envelope.
        items = payload.get("hydra:member") or payload.get("member") or payload
        if not isinstance(items, list):
            return []
        return [
            it["domain"] for it in items
            if isinstance(it, dict) and it.get("isActive", True)
            and isinstance(it.get("domain"), str)
        ]


# ---------------------------------------------------------------------------
# guerrillamail
# ---------------------------------------------------------------------------


class GuerrillaMail:
    """guerrillamail REST adapter (fallback).

    Workflow:
      GET /ajax.php?f=get_email_address    -> returns {email_addr, sid_token}
    The address is assigned by the server; the alias handle is set
    via ``set_email_user`` on a best-effort basis.
    """

    name = "guerrillamail"

    async def acquire(self, alias_handle: str, *, tor: bool) -> MailHandle:
        client = _build_client(tor=tor)
        try:
            resp = await client.get(
                f"{GUERRILLA_BASE}/ajax.php",
                params={"f": "get_email_address", "lang": "en", "agent": "babel"},
            )
            resp.raise_for_status()
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                raise MailUnavailable(f"guerrillamail: bad json: {e}") from e
            sid = data.get("sid_token")
            address = data.get("email_addr") or ""
            if not address or not sid:
                raise MailUnavailable("guerrillamail: empty address or sid")
            # Best-effort: try to set the username to the alias handle.
            try:
                rename = await client.get(
                    f"{GUERRILLA_BASE}/ajax.php",
                    params={
                        "f": "set_email_user", "email_user": alias_handle,
                        "lang": "en", "agent": "babel", "sid_token": sid,
                    },
                )
                if rename.status_code == 200:
                    new = rename.json().get("email_addr")
                    if isinstance(new, str) and "@" in new:
                        address = new
            except Exception:
                # Rename failed; the original auto-assigned address is fine.
                pass
            return MailHandle(
                address=address,
                provider=self.name,
                # Web inbox loads the sid_token via cookie when the user
                # logs in; we surface the address only.
                inbox_url=f"{GUERRILLA_INBOX_BASE}/inbox",
                expires_in_s=3600,
            )
        except Exception as e:
            if isinstance(e, (MailUnavailable, TorRequired)):
                raise
            raise MailUnavailable(f"guerrillamail: {type(e).__name__}: {e}") from e
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# Public entry point: try primary, fall back
# ---------------------------------------------------------------------------


PROVIDERS_ORDER: tuple[type[MailProvider], ...] = (MailTm, GuerrillaMail)


async def acquire_handle(alias_handle: str, *, tor: bool = True) -> MailHandle:
    """Return a ``MailHandle`` from the first provider that succeeds.

    Raises ``TorRequired`` if ``tor=True`` and no SOCKS5 port answered.
    Raises ``MailUnavailable`` if every provider in ``PROVIDERS_ORDER``
    failed. Caller decides how to surface the failure to the user.
    """
    if os.environ.get("BABEL_MASK_NO_MAIL") == "1":
        raise MailUnavailable("BABEL_MASK_NO_MAIL=1 set; skipping mail")
    errors: list[str] = []
    for cls in PROVIDERS_ORDER:
        provider = cls()
        try:
            return await provider.acquire(alias_handle, tor=tor)
        except TorRequired:
            raise   # Tor not running is a setup error, not a provider miss.
        except MailUnavailable as e:
            errors.append(f"{provider.name}: {e}")
            continue
    raise MailUnavailable("; ".join(errors) or "no providers tried")


__all__ = [
    "MailHandle", "MailProvider", "MailTm", "GuerrillaMail",
    "MailUnavailable", "TorRequired",
    "PROVIDERS_ORDER", "acquire_handle",
]
