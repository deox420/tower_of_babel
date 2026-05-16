# Architecture

[← back](../README.md) · [Install](INSTALL.md) · [Usage](USAGE.md) · **Architecture** · [Security](SECURITY.md) · [FAQ](FAQ.md)

---

## Stack

```
TUI                       Textual
Application protocol      publish_bundle / fetch_bundle / presence /
                          ratchet_init / msg / join / leave
Identity & ratchet        X3DH initial AKE
                          Double Ratchet (per-message keys)
                          Ed25519 signatures on each ciphertext
Symmetric crypto          AES-256-GCM
                          HKDF-SHA256 (root + message chains, IV derivation)
                          ISO/IEC 7816-4 padding to 1024-byte chunks
Memory hygiene            SecureBytes: mmap+mlock / VirtualAlloc+VirtualLock
                          zero-on-free
Transport                 WebSocket (RFC 6455) framed JSON
                          Tor SOCKS5 (RFC 1928)
                          Tor v3 onion (rendezvous)
```

## Identity model

Every session generates a fresh ephemeral identity. There is no
long-term key material. SAS is the only way to bind "the person I
verified" to "the person I'm talking to" — and only for this session.

- **IK** (Ed25519 seed, 32 B) — signs every outbound message. Stored
  in a `SecureBytes` buffer. Derived to Curve25519 for X3DH's DH steps.
- **SPK** (X25519) — signed by IK at generation time.
- **OPKs** (X25519 × 10) — one-time prekeys, consumed during X3DH,
  auto-refilled below threshold.

Bundle published to the server:

```json
{
  "ik":      "<base64 32B IK pub>",
  "spk":     "<base64 32B SPK pub>",
  "spk_sig": "<base64 64B Ed25519 sig of SPK by IK>",
  "opks":    ["<b64 32B>", "<b64 32B>", ...]
}
```

## X3DH (initial key agreement)

When Alice initiates with Bob:

```
SK = HKDF-SHA256(
        DH(IK_A,  SPK_B)
     || DH(EK_A,  IK_B)
     || DH(EK_A,  SPK_B)
     || DH(EK_A,  OPK_B),
     info = b"VOID-X3DH-v3"
)
```

`EK_A` is a fresh ephemeral key for this handshake. `OPK_B` is one of
Bob's one-time prekeys; the server marks it used so it isn't reused.

`SK` is the **root key** of the Double Ratchet that follows.

Alice sends Bob:

```json
{
  "type": "ratchet_init",
  "to":   "<Bob's opaque uid>",
  "x3dh": {"ik":"<A.IK>", "ek":"<A.EK>", "spk":"<B.SPK>", "opk":"<B.OPK>"},
  "dr":   {"rpub":"...", "n":0, "pn":0, "ct":"<initial DR ciphertext>"},
  "sig":  "<Ed25519 sig by A.IK over rpub||ct>"
}
```

Implementation: Syndace's [`x3dh`](https://pypi.org/project/x3dh/)
library, with a thin `VoidX3DHState` subclass that supplies the
abstract hooks.

## Double Ratchet

Two ratchets:

- **DH ratchet** — each side carries a current X25519 keypair. On
  receipt of a message with a new ratchet pubkey, derive a fresh
  shared secret via DH and feed it into the root chain. Generate a
  new sending pubkey for replies.
- **Symmetric ratchet** — sending and receiving chains advance one
  step per message. Each step yields a fresh 32-byte message key for
  the AEAD.

Wiring (`client/ratchet.py`):

| Slot | Implementation |
|---|---|
| `diffie_hellman_ratchet_class` | `VoidDR` (X25519 via xeddsa) |
| `root_chain_kdf` | HKDF-SHA256, `salt=root_key`, `info=b"VOID-Root"` |
| `message_chain_kdf` | HKDF-SHA256, `salt=chain_key`, `info=b"VOID-Msg"` |
| `aead` | `VoidAEAD` — AES-256-GCM, IV via HKDF |
| `dos_protection_threshold` | 100 (max skipped keys per single decrypt) |
| `max_num_skipped_message_keys` | 1000 (cache size) |

Implementation: Syndace's [`doubleratchet`](https://pypi.org/project/doubleratchet/);
we supply the four primitives above.

## Per-message envelope

On the wire (server-side, after relay):

```json
{
  "type":    "msg",
  "roomId":  "<sha256(room_key||password)[:16]>",
  "from":    "<sender opaque uid>",     ← server adds this; can't be forged
  "to":      "<recipient opaque uid>",
  "dr": {
    "rpub":  "<base64 32B sender DH ratchet pub>",
    "n":     <int sending-chain length>,
    "pn":    <int previous sending-chain length>,
    "ct":    "<base64 ciphertext>"
  },
  "sig":     "<base64 Ed25519 sig over rpub||ct>"
}
```

Ciphertext shape:

```
ct = AES-GCM(
    key = HKDF(msg_key)[0:32],
    iv  = HKDF(msg_key)[32:44],
    plaintext = padded_plaintext,
    aad = sender_ik || recipient_ik || ratchet_pub || n || pn
)
```

The plaintext before encryption:

```
plaintext_bytes = json.dumps({"v":3, "text":"…"}).encode()
padded          = plaintext_bytes + 0x80 + 0x00... up to next 1024 multiple
```

Resulting ciphertext is always 1040 / 2064 / 3088 / ... / 8208 bytes
(a 1024 multiple plus a 16-byte GCM tag).

## Wire protocol

### Client → Server

| Type | Fields | Effect |
|---|---|---|
| `publish_bundle` | `bundle` | Server stores bundle in RAM under sender's uid |
| `fetch_bundle` | `target` | Server replies with the target's bundle (or `missing:true`) |
| `join` | `roomId` | Add sender to the room |
| `leave` | (none) | Remove sender from the room |
| `ratchet_init` | `to`, `x3dh`, `dr`, `sig` | Relay to `to` (validated) |
| `msg` | `roomId`, `to`, `dr`, `sig` | Relay to `to` (same room only) |

### Server → Client

| Type | Fields | When |
|---|---|---|
| `presence` | `users` | After every publish/disconnect |
| `bundle` | `target`, `bundle` or `missing:true` | Reply to `fetch_bundle` |
| `ratchet_init` | `from`, `to`, `x3dh`, `dr`, `sig` | Relayed |
| `msg` | `roomId`, `from`, `to`, `dr`, `sig` | Relayed |

### Server-side enforcement

| Constraint | Limit | Violation |
|---|---|---|
| Frame size | 32 KB | close 1009 |
| Per-connection rate | 20 frames/s | close 1008 |
| Global connections | 512 | close 1013 |
| Room size | 16 peers | close 1013 on join |
| Bundle shape | ik/spk = 32B, spk_sig 32–128B, opks list of 32B (≤200) | silent drop |
| `dr` shape | rpub 32B, n/pn ≥ 0, ct = 1024-multiple+16, ≤ 8208 | silent drop |
| Signature | 32–128B base64 | silent drop |
| `to` uid | 32 lowercase hex | silent drop |
| Cross-room delivery | refused | silent drop |

## Memory hygiene

Long-lived material — the Ed25519 IK seed — sits in `SecureBytes`:

- POSIX: `mmap(-1, size, MAP_PRIVATE | MAP_ANONYMOUS, PROT_READ|WRITE)` then `mlock(ptr, size)`. `memset(ptr, 0, size)` on free.
- Windows: `VirtualAlloc(MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE)` then `VirtualLock`. `memset` + `VirtualUnlock` + `VirtualFree` on close.
- mlock denied (Termux without root, hardened kernels): plain
  `bytearray`, one-time stderr warning, continue.

Not in SecureBytes: ratchet message/root/chain keys (they live inside
the `doubleratchet` library) and transient Python `str`/`bytes`
plaintexts (immutable, can't be overwritten in place). Best-effort
cleanup on `/leave`: drop references; chat log uses `bytearray` text
buffers that `/burn` zeros.

## Tor — ephemeral v3 onions

`void --make-invite`:

1. Opens TCP to `127.0.0.1:9051` (or `9151`).
2. `PROTOCOLINFO 1` — learns auth methods.
3. SAFECOOKIE: `AUTHCHALLENGE`, verify `SERVERHASH` via HMAC-SHA256, send `CLIENT_HASH`.
4. `ADD_ONION NEW:ED25519-V3 Flags=DiscardPK Port=8765,127.0.0.1:<random>` — Tor generates a v3 key, returns the `.onion`, discards the private key.
5. Embed `void-server` in the same process at `127.0.0.1:<random>`.
6. Ctrl+C: `DEL_ONION` + close. The onion is dead.

## Cover traffic

`client/cover.py` runs an async task that wakes every 15–45 s. If no
real message was sent in the interval, it encrypts and sends a dummy
`{"v":3,"dummy":true,"noise":"..."}` to each peer. Dummies are padded
and encrypted identically to real messages; on the wire they're
indistinguishable. Receivers decrypt, see `dummy:true`, drop.

Talker sends more bytes than a silent peer (~30 % more in a 30 s
window). A token-bucket rate cap would equalise but slow real sends —
deferred to Phase 5+.

## Server jitter

`server/main.py:_route_to` sleeps `uniform(50, 350) ms` before
forwarding each msg. Each forward is its own asyncio task, so jitter
doesn't serialise group delivery.

## Group routing

Each pair of peers shares its own Double Ratchet. One outbound user
message is encrypted N-1 times (once per peer) and the server
fans out the N-1 frames by routing on the recipient's opaque uid.

Bandwidth is O(N²) per message. Room is hard-capped at 16 peers.
No Megolm-style sender keys (intentional — simpler model).

## File layout

```
void/
├── client/                Textual TUI + crypto wiring + Tor control
├── server/                blind relay, validators, jitter, room cap
├── docs/                  this manual
├── packaging/             PyInstaller specs, Dockerfile.build, build.sh, SOURCE_DATE_EPOCH
├── pentest/               internal attack scripts (developer surface)
├── .github/               CI workflows, issue templates, release notes
├── install.sh             Linux / macOS / Termux installer
├── install.ps1            Windows installer
├── Makefile               run-server / run-client / build / build-docker
├── pyproject.toml
├── requirements.txt
├── VERSION
├── CHANGELOG.md
├── LICENSE                0BSD
└── README.md
```

---

[← Usage](USAGE.md) · [Security →](SECURITY.md)
