# Security

[← back](../README.md) · [Install](INSTALL.md) · [Usage](USAGE.md) · [Architecture](ARCHITECTURE.md) · **Security** · [FAQ](FAQ.md)

---

## What VOID protects

| Property | How |
|---|---|
| **End-to-end confidentiality** | X3DH + Double Ratchet. Server only sees AES-GCM ciphertext. |
| **Forward secrecy** | Each message has its own key from a one-step-advanced symmetric ratchet. |
| **Post-compromise security** | After the next DH ratchet step, future messages are secure again. |
| **Replay rejection** | DR's message counter rejects re-seen frames (`DuplicateMessageException`). |
| **Out-of-order tolerance** | Up to 1000 cached skipped keys; max 100 skipped per single decrypt (DoS guard). |
| **Authentication** | Every msg / ratchet_init is Ed25519-signed by the sender's IK. |
| **MITM detection** | 5-word PGP-list SAS over `SHA-256(min(IK_a, IK_b) || max(IK_a, IK_b))`. |
| **Anonymous transport** | Tor v3 onion routing. Server bound to `127.0.0.1`. |
| **Length hiding** | Every ciphertext is a 1024-byte multiple + 16-byte GCM tag. |
| **Idle/busy decorrelation** | 15–45 s cover dummies + 50–350 ms server-side forwarding jitter. |
| **Memory hygiene** | IK seed in `mlock`'d / `VirtualLock`'d pages, zeroed on free. |
| **Disappearing local messages** | `/burn N` zeros the local bytearray and re-renders the line as `[BURNED]`. |
| **Ephemeral identities** | Fresh IK / SPK / OPKs per session. No long-term key material. No disk. |
| **Build provenance** | Reproducible PyInstaller builds; rebuild from source and compare SHA256. |

## What VOID does NOT protect

### Endpoint compromise
Keyloggers, screen capture, malicious terminal emulators, RAM
scrapers, terminal scrollback — all out of scope. Plaintext lives in
process RAM while the TUI renders it.

### `/burn` is best-effort, local-only
Burn zeros the bytearrays we hold and flips the entry kind. It does
NOT affect the peer's screen, terminal scrollback, screenshots,
ratchet skipped-key cache copies, or anything outside the current
process.

### Onion authenticity is TOFU
The `.onion` arrives in an invite link. VOID does not pin it. A wrong
.onion connects to an attacker's server. SAS still catches active
MITM, but only after both sides compare words.

### Quantum (HNDL)
X25519 and Ed25519 are not post-quantum. Ciphertext captured today
could be decrypted by a future quantum adversary. Phase 5+: hybrid
Kyber/ML-KEM over X25519.

### Global passive adversary
Tor + padding + jitter + cover help against most realistic adversaries
but not against a GPA that watches both endpoints. Mixnets are the
real fix.

### Wire-rate asymmetry
A talker emits ~30 % more bytes than a silent peer over a 30 s
window. A token-bucket rate cap would equalise at the cost of slower
real sends. Phase 5+.

### Server availability
The server is a single point of failure for *delivery*. No
federation, no store-and-forward. If it's down, no chat. Workaround:
self-host with `void --make-invite`.

### Social attacks
Anyone who knows the `void://` link can read everything. Pick strong
secrets. Treat the invite distribution channel as your weakest link.

### SAS grinding
5 PGP words = 40 bits. An adversary who can grind ~10¹² IK pairs per
session could match SAS words. Per-session ephemeral identities cap
the value of such an attack.

## Cryptographic dependencies

| Library | Role | Notes |
|---|---|---|
| [`cryptography`](https://pypi.org/project/cryptography/) (PyCA) | AES-GCM, HKDF, X.509 | Well-audited |
| [`xeddsa`](https://pypi.org/project/XEdDSA/) + `libxeddsa` | X25519 / Ed25519 / XEdDSA | Author-maintained |
| [`doubleratchet`](https://pypi.org/project/doubleratchet/) | Double Ratchet | Signal-spec reference; not formally audited |
| [`x3dh`](https://pypi.org/project/x3dh/) | X3DH | Same author, same status |
| [`websockets`](https://pypi.org/project/websockets/) | wire | Mature |
| [`python-socks`](https://pypi.org/project/python-socks/) | SOCKS5 | Mature |
| [`textual`](https://pypi.org/project/textual/) | TUI | Maintained |

Versions are pinned in `requirements.txt`; releases are tested via the
reproducible Docker build pipeline.

## Reporting issues

| Type | How |
|---|---|
| Non-security bug | GitHub Issue (use the template) |
| Security bug (discussable in public) | GitHub Issue tagged `security`, no exploit data |
| Severe RCE-class issue | Contact the maintainer privately before public disclosure |

## Roadmap (Phase 5+)

Explicit holes we deferred:

1. Hybrid PQ KEM (Kyber/ML-KEM over X25519) for HNDL resistance.
2. Mixnet transport (Loopix-style) instead of single-hop Tor.
3. Token-bucket rate cap for wire-rate symmetry.
4. 6-word SAS (48 bits) — one extra word in exchange for 256× more grinding.
5. Random pad within the 1024-byte chunk.
6. Out-of-band onion fingerprint pinning in the invite.
7. Bundled Tor in the binary (no separate install).

---

[← Architecture](ARCHITECTURE.md) · [FAQ →](FAQ.md)
