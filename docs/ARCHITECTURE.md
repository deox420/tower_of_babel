# Architecture

[<- back](../README.md) - [Install](INSTALL.md) - [Usage](USAGE.md) - **Architecture** - [Security](SECURITY.md) - [FAQ](FAQ.md)

---

Tower of Babel is a federation of five single-purpose terminal tools
under a shared chrome, build system, and moral posture.  This
document is the suite-wide architectural overview.  Per-tool detail
lives in `docs/tools/<NAME>.md`; the design constitution is
`MASTER.md` at the repo root.

## Layered view

```
+-----------------------------------------------------------------+
| babel/        chrome (Textual outer frame + 5-indicator footer) |
|               main menu + service registry + global hotkeys     |
|               (Alt+1..N service switch, Alt+0 menu, Ctrl+W close)|
+-----------------------------------------------------------------+
| tools/        VOID  MASK  STRIP  CARRIER  MIRAGE                |
|               service service action action service action      |
|               (slot-resident) (one-shot return to menu)         |
+-----------------------------------------------------------------+
| shared/       crypto (AEAD, KDF, SecureBytes)                   |
|               tor    (control, SOCKS5 detection)                |
|               ui     (progress, step indicator, hex view, diff) |
|               link   (void:// / mask:// / carrier:// codec)    |
+-----------------------------------------------------------------+
| stdlib +      Textual / Rich (TUI)                              |
| pinned deps   pyca/cryptography (AES-GCM, HKDF)                 |
|               argon2-cffi (Argon2id)                            |
|               xeddsa / doubleratchet / x3dh (VOID protocol)     |
|               python-socks / httpx[socks] (Tor SOCKS5)          |
|               Pillow (PNG cover), pypdf (PDF metadata)          |
+-----------------------------------------------------------------+
```

Hard isolation rule (`MASTER.md` 4.3): a tool may import only from
`shared/` and `babel/`.  Cross-tool imports are forbidden and
enforced at audit time.

## Suite chrome (`babel/`)

The chrome is one Textual `App` whose outer border is drawn once on
launch and **never repaints**.  Tool views mount and unmount inside
a content slot.  A bottom footer reports five live indicators backed
by real probe callables -- no fake green dots.

```
+========================== TOWER OF BABEL ============= v1.0.0 ==+
| [1:VOID 2 peers]  [2:MIRAGE 18 rpm 41 KB/min]                    |  <- slot bar
|                                                                  |
|   <view content mounts here (menu, tool home, etc.)>             |  <- content slot
|                                                                  |
|--- TOR *  --- MEM *  --- CRYPTO .  --- SWAP *  --- 14:32:09 ----|  <- footer
+==================================================================+
```

Five indicators (each a probe callable, not a decoration):

- **TOR**    -- green if any service has an active Tor circuit;
                 the trailing label shows `N svcs` when multiple.
- **MEM**    -- green if any live `SecureBytes` buffer is mlocked
                 (or `VirtualLock`d on Windows).
- **CRYPTO** -- green when key material is loaded.
- **SWAP**   -- amber if any service warned about swap+mlock fallback.
- **CLOCK**  -- real UTC, ticking every second.

### Multiplex (slot model)

The chrome hosts up to `BABEL_MAX_SERVICES` (default 4) concurrent
**service**-flavoured tools.  Service-flavour tools (VOID, MIRAGE)
keep running while the user switches to anything else.  **Action**-
flavoured tools (MASK, STRIP, CARRIER) run one operation and return
to the menu.

| Hotkey       | Effect                                         |
|--------------|------------------------------------------------|
| `Alt+1..N`   | jump to service N                              |
| `Alt+0`      | jump to main menu (services keep running)      |
| `Alt+M`      | open menu overlay without leaving current view |
| `Alt+]` / `[`| cycle next / previous active service           |
| `Ctrl+W`     | close current service (calls `purge_local()`)  |
| `Ctrl+C`/`Q` | quit (purge_local on EVERY live service)       |

Each service satisfies the runtime-checkable `Service` Protocol
(`babel/shell.py`):

```python
class Service(Protocol):
    name: str
    def status_line(self) -> str: ...
    def footer_contribution(self) -> dict: ...
    def resource_caps(self) -> dict: ...
    async def purge_local(self) -> None: ...  # <1 s, zeros all secrets
```

A service must (a) be cooperative under `purge_local()` (returns in
< 1 s with all in-RAM secrets zeroed), (b) yield CPU during idle
(asyncio.sleep, no busy loops), (c) never block the render loop
(long work in `asyncio.create_task`), (d) cap its bandwidth and
CPU if it touches the network.

## Per-tool architectures

### VOID -- ephemeral encrypted messenger  (service)

Chat for short private conversations.  Fresh ephemeral identity per
session.  X3DH initial AKE + Double Ratchet per-message keys +
Ed25519 signatures on every outbound message.  Routed over Tor v3
onion addresses.  The server is a blind relay; it never sees
plaintext.

```
Identity      IK Ed25519 seed (mlock'd SecureBytes)
              SPK X25519, signed by IK
              OPKs X25519 x 10, refilled below threshold

X3DH          IK_A * SPK_B || EK_A * IK_B || EK_A * SPK_B
              || (EK_A * OPK_B if available) -> shared secret

Double        per-direction sending+receiving chain keys
Ratchet       skip-out-of-order, DH ratchet on each
              direction change, DuplicateMessageException on replay

Symmetric     AES-256-GCM, HKDF-SHA256 chain advance,
              ISO/IEC 7816-4 padding to 1024-byte chunks

Transport     WebSocket (RFC 6455) framed JSON
              Tor SOCKS5 (RFC 1928) socks5h:// -- DNS in proxy
              Tor v3 ephemeral onion (ADD_ONION NEW:ED25519-V3)

Server        MAX_CONNECTIONS=512, close 1013 on overflow
hardening     _valid_bundle, _valid_dr_envelope, _valid_signature,
              _valid_x3dh_envelope.  Drops malformed frames silently.
```

Wire format and protocol detail: see the protocol section below.
Per-tool doc: [docs/tools/VOID.md](tools/VOID.md).

### MASK -- disposable identity generator  (action)

Generates a coherent disposable identity in one keystroke.

```
Pipeline      locale + profile (en/es/fr/de/neutral x 4 profiles)
              -> alias drawn from public-domain census-frequency catalog
              -> 2-3 line bio from template pool
              -> 5x5 mirrored geometric avatar (deterministic
                 SHA-256-seeded 2-colour grid; NO public-service avatar)
              -> optional temp-mail handle via mail.tm / guerrillamail
                 (Tor by default, refuses to fire without SOCKS5)
              -> wire format: mask://base64url({alias, avatar_sha,
                 mail_handle, bio, ts}), ts rounded to 60 s

Storage       RAM only.  Optional encrypted export:
                 Argon2id(passphrase, salt) -> AES-256-GCM blob
                 written to a user-chosen path.  Passphrase lives in
                 a SecureBytes buffer for the duration of the prompt.
```

Per-tool doc: [docs/tools/MASK.md](tools/MASK.md).

### STRIP -- metadata laundry  (action)

Removes declared metadata from five file families with byte-level
parsers -- no re-encode, no pixel-level changes.

```
JPEG          EXIF, XMP, IPTC, COM marker; APP0/JFIF preserved
PNG           tEXt / iTXt / zTXt / tIME / eXIf chunks;
              iCCP under --aggressive; IHDR/IDAT/IEND survive
PDF           /Info dict cleared, /Metadata XMP stream removed,
              /ID array replaced with fresh random; pypdf 6.x
DOCX          core + app + custom properties via stdlib zipfile +
              xml.etree; rsids and trackChanges under --aggressive
MP3           ID3v2 frames (head), ID3v1 trailer, APEv2 (tail);
              whole-block removal, no frame rewrite (avoids GPL
              dep on mutagen)
```

Modes: single, batch (originals untouched), `--aggressive` toggle,
optional `--hash-rename` (SHA-256-named output).

Per-tool doc: [docs/tools/STRIP.md](tools/STRIP.md).

### CARRIER -- steganography  (action)

Hides an AES-256-GCM-encrypted payload in the LSB plane of a PNG
image or WAV PCM stream.

```
Pipeline      1. passphrase + fresh 16 B salt
                 -> Argon2id (time=3, mem=64 MiB, par=4)
                 -> 32 B AES key
              2. payload -> optional zlib -> AES-256-GCM with fresh
                 12 B nonce -> ciphertext + 16 B GCM tag
              3. capacity check (default safety factor 0.125 of
                 channel-bit budget); refuse if unsafe
              4. embed: LSB write of salt || nonce || length ||
                 ciphertext into the cover (NO magic field by design,
                 MASTER.md 7.4 -- GCM auth IS the validity signal)
              5. chi-square sanity check (Westfeld-Pfitzmann + Wilson-
                 Hilferty normal approximation -- no scipy dep);
                 --strict refuses when p > 0.95

Cover         PNG (RGB or RGBA), WAV (1/2/3-byte sample width).
formats       Lossy formats refused (JPEG, MP3, AAC) -- LSB destroyed
              by quantisation on re-encode.
```

Per-tool doc: [docs/tools/CARRIER.md](tools/CARRIER.md).

### MIRAGE -- cover traffic generator  (service)

Generates plausible background HTTP activity from configurable
profiles.  Real httpx requests, real DNS through `socks5h://`, real
session dwell times drawn from a Zipf-weighted per-profile site
catalog.

```
Profiles      office_worker, developer, casual_browser, researcher
              (each: rpm_typical, dwell range, UA pool, accept_language)

Hard caps     bandwidth: token bucket, capacity = bw_kbps * 1024 B,
              gated before fetch; force_consume(actual) after fetch
              so the long-run average respects the cap.
              rate: token bucket, capacity = rate_rpm, refill /60 per s.
              cpu: 60 s sliding window over time.process_time deltas;
              cooldown sleep inserted when windowed avg exceeds cap.

Routing       Tor SOCKS5h by default (DNS in proxy).  Clearnet
              requires `--clearnet --i-know-what-im-doing` AND prints
              a red banner first.  Refuse to start if use_tor=True
              and the SOCKS5 probe fails.

Honest mode   `--honest` emits one stderr line per fired request
              (timestamp / host / bytes / latency).  The TUI also
              shows a deque-bounded ring buffer of recent events.
```

Per-tool doc: [docs/tools/MIRAGE.md](tools/MIRAGE.md).

## Shared modules (`shared/`)

Cross-tool primitives.  Tools may NOT import from each other; they
may import from here and from `babel/`.

| Module                              | Used by                                 |
|-------------------------------------|-----------------------------------------|
| `shared/crypto/secure_mem.py`       | every tool (mlock'd buffer, zero-on-free) |
| `shared/crypto/aead.py`             | CARRIER, MASK (AES-256-GCM wrapper)    |
| `shared/crypto/kdf.py`              | CARRIER, MASK (Argon2id + HKDF)        |
| `shared/tor/control.py`             | VOID (ADD_ONION), MIRAGE (NEWNYM)      |
| `shared/tor/socks_detect.py`        | VOID, MASK, MIRAGE (9050/9150/9151 probe) |
| `shared/ui/progress.py`             | (available, integration WIP)            |
| `shared/ui/step_indicator.py`       | MASK, future tools                      |
| `shared/ui/hex_view.py`             | CARRIER (preview pane)                 |
| `shared/ui/diff_view.py`            | STRIP (before/after report)            |
| `shared/ui/compact.py`              | chrome (<80-col layout decisions)      |
| `shared/link/invite.py`             | VOID (void://), MASK (mask://), CARRIER (carrier://) |

## Cryptographic stack

```
AEAD          AES-256-GCM via pyca/cryptography.hazmat
              (used by VOID's Double Ratchet, CARRIER, MASK export)
KDF           Argon2id via argon2-cffi (CARRIER, MASK export)
              HKDF-SHA256 via pyca/cryptography (VOID chain + IV)
Signatures    Ed25519 via xeddsa (VOID identity)
Key agreement X25519 via xeddsa + doubleratchet + x3dh (VOID)
Padding       ISO/IEC 7816-4 to 1024 B chunks (VOID)
Randomness    secrets.token_bytes (CARRIER nonce/salt, MASK seed)
Memory        SecureBytes -- mmap+mlock (Unix) / VirtualAlloc+
              VirtualLock (Windows), zero-on-free
```

No rolled-your-own crypto anywhere in the suite.  All AEAD goes
through `cryptography.hazmat.primitives.ciphers.aead.AESGCM`; all
Argon2id derivations through `argon2-cffi`; all HKDF through
`cryptography.hazmat.primitives.kdf.hkdf`.

## VOID protocol detail

(Carried over from the v0.5.0 architecture doc.  Unchanged in v1.0.0
-- VOID's wire format, ratchet, and server hardening are wire-
compatible with v0.5.0 clients and servers.)

### Identity model

Every session generates a fresh ephemeral identity. There is no
long-term key material. SAS is the only way to bind "the person I
verified" to "the person I am talking to" -- and only for this session.

- **IK** (Ed25519 seed, 32 B) -- signs every outbound message. Stored
  in a `SecureBytes` buffer. Derived to Curve25519 for X3DH's DH steps.
- **SPK** (X25519) -- signed by IK at generation time.
- **OPKs** (X25519 x 10) -- one-time prekeys, consumed during X3DH,
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

### X3DH (initial key agreement)

`SK = IK_A*SPK_B || EK_A*IK_B || EK_A*SPK_B || (EK_A*OPK_B)`
fed into HKDF; output seeds the Double Ratchet root key.

### Double Ratchet

Per-direction sending + receiving chain keys.  Each new message
advances the chain; each direction change rotates a DH ratchet.
Out-of-order tolerance, replay rejection (`DuplicateMessageException`).

### Wire protocol

```
Client -> Server:
  publish_bundle, fetch_bundle, presence, ratchet_init, msg,
  join, leave

Server -> Client:
  bundle, presence, ratchet_init, msg, error

Server-side enforcement:
  MAX_CONNECTIONS=512 (close 1013 on overflow)
  _valid_bundle: ik/spk 32B, spk_sig 32-128B, opks list of 32B (<=200)
  _valid_dr_envelope: rpub 32B, n/pn >= 0, ct = 1024*n + 16, <= 8208
  _valid_signature: Ed25519 32-128B
  _valid_x3dh_envelope: ik/ek/spk 32B each, opk optional 32B
```

### Memory hygiene

`SecureBytes` (in `shared/crypto/secure_mem.py`) wraps a fixed-size
buffer with:

- mmap + mlock on POSIX (Linux/macOS/Termux)
- `VirtualAlloc(MEM_RESERVE|MEM_COMMIT) + VirtualLock` on Windows
- explicit `zero()` writes `0x00` over the buffer before `free()`

Footer reports `MEM*` green when any live SecureBytes is mlocked;
amber if mlock fails (e.g. ulimit too low) and the suite falls back
to plain heap with a warning.

### Tor -- ephemeral v3 onions

VOID's host opens the onion via Tor's control port using
`ADD_ONION NEW:ED25519-V3 Flags=DiscardPK` (in
`shared/tor/control.py`).  The address is ephemeral: Tor forgets it
the moment the control connection closes.  No on-disk onion
hostname file.

## Build pipeline

```
Reproducibility   SOURCE_DATE_EPOCH pinned (packaging/SOURCE_DATE_EPOCH)
                  PYTHONHASHSEED=0
                  PYTHONDONTWRITEBYTECODE=1
                  TZ=UTC, LC_ALL=C.UTF-8
                  sorted PyInstaller Analysis inputs
                  pinned Docker base: python:3.11.10-slim-bookworm
                  hash-locked requirements.lock (pip-compile output)

Per-platform      babel.spec        full-suite binary (all 5 tools)
specs             void-server.spec  narrow server-only binary for
                                    hardened deployments

CI matrix         ubuntu-latest x86_64
                  macos-latest arm64 (Apple Silicon)
                  windows-latest x86_64
                  .github/workflows/release.yml fires on tag push
                  Two-build same-host determinism verified locally;
                  CI publishes binaries + SHA256SUMS to the Release.
```

## Decision log

Per MASTER.md Section 11.3, architectural sub-decisions surfaced
through the Forge framework are logged here as one-line entries:
date, question, framework, outcome.

| Date | Question | Framework | Outcome |
|------|----------|-----------|---------|
| 2026-05-17 | What threats does STRIP actually address vs leave open? | LINDDUN | Six axes enumerated for STRIP (Linkability through Non-compliance); absorbed into docs/tools/STRIP.md Sections 2-3. Drove (a) byte-level parsers (no Pillow/python-docx/mutagen re-encode), (b) refuse encrypted PDFs rather than guess, (c) opt-in hash-rename for filename leak. |
| 2026-05-17 | What threats does MASK actually address vs leave open? | LINDDUN | Seven categories enumerated; absorbed into docs/tools/MASK.md Sections 2-3.  Drove the three sub-decisions below. |
| 2026-05-17 | Should MASK poll the temp-mail inbox? | DECISION / inversion | No: polling is detectable and adds nothing the user cannot do themselves. MASK returns `inbox_url` and stops. (LINDDUN Detectability.) |
| 2026-05-17 | Should mail.tm domain selection be first-in-list or random? | DECISION / premortem | Uniform-random across the returned list.  First-in-list is a per-install fingerprint if mail.tm ever reorders. (LINDDUN Linkability.) |
| 2026-05-17 | Should the `ts` field in `mask://` carry second precision? | DECISION / inversion | Round to nearest 60 s before encoding.  Second precision leaks sub-minute clock accuracy. (LINDDUN Disclosure.) |
| 2026-05-17 | Build `httpx[socks]` or stick to stdlib + PySocks? | DECISION / decision matrix | `httpx[socks]`.  stdlib + global socket monkeypatch would route every accidental DNS/HTTP call out the Tor port -- masking rather than fixing a leak. `httpx`'s proxy is per-client. |
| 2026-05-17 | `shared/link/invite.py` and `shared/ui/step_indicator.py` were missing -- patch shared/ in Phase 4 or stop? | DECISION (escalated) | Build as net-new modules.  Specified in MASTER.md 5.5 / 5.6; "no refactor of pentest-covered shared/" was the rule, and net-new shared modules are not refactors. |
| 2026-05-18 | `data/` in `.gitignore` silently excluded `tools/mask/data/*.json` from the repo, breaking CI PyInstaller builds. | DEBUG / root-cause | Removed the blanket ignore; pinned the lesson in `.gitignore` so nobody reintroduces it.  Forces the suite's pyfiglet-generated catalogs to ship with the source. |
| 2026-05-19 | Should each tool's home view BE the Service instance, or should the Service be a separate object owned by the home view? | DECISION / inversion | Separate object. Inversion test: if View IS Service, the registry holds a Textual Widget, so the Service Protocol cannot be exercised without importing `textual` -- the spec's pentest contract explicitly bans Textual imports from `pentest/babel/test_*.py`. Also: a Service must survive its View being unmounted (e.g. on chrome rebuild); coupling them to one object destroys that. MIRAGE already split this way (`MirageService` + `MirageView`); Phase 7 extends the pattern to VOID. ACTION-flavour views (MASK / STRIP / CARRIER) get no Service at all. Registry holds `Service` objects with a back-reference `.view` for `chrome.show_existing(svc.view)` jumps. |

---

[<- Usage](USAGE.md) - [Security ->](SECURITY.md)
