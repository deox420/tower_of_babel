# FAQ

[← back](../README.md) · [Install](INSTALL.md) · [Usage](USAGE.md) · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · **FAQ**

---

## Is VOID a replacement for Signal?

No. Signal has a real app, real contacts, and push notifications.
VOID is a terminal tool for short, intentional, private conversations
between people who can share an invite over a trusted side channel.

If you need "WhatsApp but private", use Signal. If you need "Signal
but harder", use SimpleX or Cwtch. VOID is a smaller niche.

## Why a terminal app?

A GUI forces you to trust a renderer, an OS framework, a system
clipboard, and probably a notification daemon. A TUI requires you to
trust your terminal emulator — one fewer attack surface.

## Why Tor?

VOID's server doesn't see plaintext, but it does see source IPs
without Tor. The server binds to `127.0.0.1` and is reachable only
through an onion service.

`--clearnet` still encrypts E2E, but the server learns who's talking
to whom by IP. Only use it for local testing.

## Why per-pair Double Ratchet instead of Megolm?

Megolm is faster in groups (O(N) per message) but harder to reason
about: every member holds the sender's chain key, and rotation needs
re-sharing. VOID picked simplicity. For 2–16 peers, O(N²) is fine.

## Can I host a permanent server?

Yes:

```bash
void-server --insecure --host 127.0.0.1 --port 8765
```

Plus a permanent Tor hidden service in `/etc/tor/torrc`:

```
HiddenServiceDir /var/lib/tor/void/
HiddenServicePort 8765 127.0.0.1:8765
```

`sudo cat /var/lib/tor/void/hostname` gives the stable `.onion`. Note
the private key is on disk; if the server is seized, the address can
be revived. For most chats, `void --make-invite` is better — the
onion dies with the host process.

## Do messages survive a server restart?

No. Everything is in RAM. Restart kills all rooms and bundles. Clients
get a disconnect and bounce back to the lobby with an error. By
design.

## Can a malicious server read my messages?

Content: no — the Double Ratchet's AES-GCM is end-to-end.

A malicious server CAN: drop messages, deliver selectively, attempt
MITM by swapping prekey bundles. The MITM attempt is detectable via
SAS: if 5 PGP words don't match between A and B, the server is
attacking. Selective delivery is harder to spot — just looks like an
unreliable network.

## What if my peer takes a screenshot?

VOID can't stop them. `/burn` only zeros YOUR copy. The peer's
screen is independent.

## What if I forget to run `/quit`?

When the process exits, OS reclaims memory and `mlock`'d pages are
freed. The chat's plaintext lives in RAM until the process dies —
short window. `/quit` explicitly zeros buffers first; closing the
terminal doesn't. Prefer `/quit` when you can.

## Why is the invite a long base64 blob?

It packs the .onion (56 chars), room key, password, and optional
fingerprint pin into one pasteable string. Without it, a user has
three separate strings to copy correctly. Future: QR code rendering
so a phone can scan it from a PC screen.

## Why no notifications?

Notifications require a background process polling for messages and
persisting state. Both break VOID's "no disk, ephemeral, intentional"
model. Run inside `tmux` and check manually.

## Why no contact list?

Same reason. Contacts persist. Persistence breaks the model. Every
session = fresh identities; SAS verification is a per-session ritual.
The friction is the point.

## Why F-Droid for Termux specifically?

The Play Store Termux is unmaintained and its `pkg` repos are
dead. The F-Droid build is current. Same app, different distribution.

## Can I run VOID over a corporate proxy?

Tor handles this if your proxy forwards SOCKS. If the proxy actively
blocks Tor, configure a bridge (`obfs4`) in your `torrc` — VOID uses
the same Tor instance.

## End-to-end encrypted group chat?

Yes. Rooms up to 16 peers. Every pair has its own DR session. The
server can't read any of them; it fans out N-1 ciphertexts per
message you send.

## How do I report a security issue?

See [Security → Reporting issues](SECURITY.md#reporting-issues).

---

[← Security](SECURITY.md) · [back to README →](../README.md)
