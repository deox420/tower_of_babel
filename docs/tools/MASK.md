*confusion of tongues, by design*

```
███╗   ███╗ █████╗ ███████╗██╗  ██╗
████╗ ████║██╔══██╗██╔════╝██║ ██╔╝
██╔████╔██║███████║███████╗█████╔╝
██║╚██╔╝██║██╔══██║╚════██║██╔═██╗
██║ ╚═╝ ██║██║  ██║███████║██║  ██╗
╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
```

# MASK - disposable identity generator

## 1 - What this is

MASK produces a coherent disposable identity in one keystroke: a
locale-coherent alias, a 2-3 line bio drawn from a static template
pool, a locally-rendered geometric avatar, and (optionally) a
temp-mail handle acquired over Tor. The whole bundle lives in RAM
for the duration of the action and is zeroed when you leave. If you
want to keep it, you opt in to a passphrase-encrypted export blob
you save somewhere yourself.

MASK is an *action* tool (MASTER.md Section 4.4): drop into the
screen, generate, copy, leave. There is no service slot. There is
no on-disk identity database. The tool does not poll the temp-mail
inbox for you - it hands you the address and the URL where you
read it, and the inbox is public anyway (see Section 3).

It is the cheapest hammer in the tower: every additional identity
costs you the time it takes to press `n`. That cheapness is the
point. Reusing a disposable identity across services correlates
them; rotating is free.

## 2 - What it protects

| Surface | Protection |
|---|---|
| Alias coherence per locale | Given + family names drawn from a per-locale catalog (en / es / fr / de + a `neutral` ambiguous pool). No cross-locale leakage of name patterns. |
| Bio plausibility | Bios composed from a per-locale template pool with profile-tagged fragments (`default`, `writer`, `trader`, `researcher`). |
| Avatar provenance | Avatar rendered locally as an SVG (5x5 grid mirrored to 10x5, 2-colour palette). Never fetched from a public avatar service. PNG output is Pillow-rendered, deterministic for the same seed. |
| Identity in RAM only | No disk writes for the bundle itself. Export is opt-in (`--export <path>`) and writes only to a path you pass. |
| Tor by default for temp-mail | `mask new` routes the mail.tm POST + GET through the auto-detected Tor SOCKS5 port (9050 / 9150 / 9151). |
| Clearnet requires opt-in | `--clearnet` is required to bypass Tor; the CLI also requires `--i-know` (or interactive `y` at the red warning panel) before any clearnet request fires. |
| Encrypted export | Passphrase -> Argon2id (interactive defaults: t=3, m=64 MiB, p=4) -> AES-256-GCM (`shared.crypto.aead`). Wrong passphrase decrypts to a GCM authentication failure, not silent garbage. |
| Passphrase hygiene | Passphrase held in `shared.crypto.secure_mem.SecureBytes` for the lifetime of the export / import call; zeroed on exit even if the call raises. |
| `mask://` codec | Lossless `base64url(canonical_json({alias, bio, avatar_sha, mail_handle, ts}))`. No telemetry fields, no machine fingerprint. The `ts` is rounded to the nearest 60 seconds before encoding, so a paste at 14:32:47 does not leak that you are using a clock at second precision. |
| Identity zeroing on leave | `Esc`, `Ctrl+W`, `Ctrl+C`, `q` all run the action's purge handler: the `SecureBytes` passphrase wrapper is `free()`d, the in-memory `Identity` dataclass is overwritten, and the temp-mail HTTP client is closed. |
| Mail provider rotation | `mail.tm` first, `guerrillamail` on failure or 429. Provider choice is logged on stderr only if `--json`, so a regular run does not leak which adapter you fell through to. |
| mail.tm domain selection | When mail.tm offers multiple domains, MASK picks one uniformly at random rather than the first in the list, so the choice itself does not fingerprint a particular install's traversal order. |

## 3 - What this does NOT protect

| Risk | Why it survives |
|---|---|
| Reverse image search of avatars | Geometric avatars are harder to reverse-search than photographs, but a sufficiently motivated adversary can build a generator-pattern classifier from a small corpus of MASK outputs. Treat the avatar as visually distinct, not as a unique identity. |
| Public-SMS readability | MASK does not integrate any SMS service. If you paste a public SMS number into a signup, that inbox is world-readable by anyone with the number. MASK provides no SMS shortcut on purpose. |
| Temp-mail inbox readability | mail.tm and guerrillamail are **publicly readable by anyone with the handle**. Anyone who guesses, scrapes, or eavesdrops on the address can read the inbox. Use temp-mail only for things that are worthless 30 seconds later (one-time codes, account verifications). |
| Behavioural fingerprinting | Typing cadence, mouse movement, browser canvas, font set, TLS JA3, language headers, screen size - MASK ships a text bundle, not a browser hardener. The disposable identity holds for as long as the *behaviour* you put behind it stays disposable. |
| mail.tm correlates receiving IP to inbox | Tor breaks the link between your IP and the inbox creation request. Reading the inbox from a non-Tor client undoes that. The Tor handshake is also a tell to anyone watching your local network. |
| DNS leaks if you pass `--clearnet` | Without Tor, your OS resolver sees `api.mail.tm` and `api.guerrillamail.com` lookups. The `--clearnet` warning panel says this verbatim. |
| Argon2id CPU-time leak on export | The Argon2id derivation takes ~1 second on a default 4-core box. An attacker who controls the export-target storage and can time writes can roughly bound your CPU class. Advisory only - relevant if you export to a network share or a hostile USB stick. |
| Reusing the same disposable identity across services | MASK does not de-duplicate. If you paste the same `mask://` blob into two services, they correlate trivially. Generate a fresh one (`n`) per service. |
| The fact that you ran MASK | Process listings, shell history, antivirus telemetry, Tor circuit setup latency, and the existence of `babel` on disk are all observable. MASK cannot launder its own footprint. |
| `mask://` scheme as a clipboard scraper tell | Clipboard managers, browser autofill, and remote screen software see the literal string `mask://...`. The scheme prefix is a feature for autofill in the babel lobby and a liability everywhere else. Treat it like a password. |
| Endpoint compromise | If something on your machine reads the `Identity` buffer through `/proc/<pid>/mem`, a kernel debugger, or a core dump, MASK cannot help. `SecureBytes` reduces but does not eliminate that surface. |
| Mail provider tampering | mail.tm and guerrillamail are third parties; both have observed the address you generated. A subpoena or breach exposes the link between the address and the IP that created it (Tor mitigates the IP half, not the timing half). |
| Identity bundles you exported and forgot about | The encrypted export blob is as secure as your passphrase. A weak passphrase + an old blob on a backup drive is a recoverable identity. |

## 4 - CLI flags

```
babel mask                              # interactive TUI screen
babel mask new                          # one-shot: print mask:// to stdout
babel mask new --locale en|es|fr|de|neutral
babel mask new --profile default|writer|trader|researcher
babel mask new --json                   # full bundle as JSON
babel mask new --no-mail                # skip temp-mail fetch entirely
babel mask new --no-avatar              # skip avatar generation entirely
babel mask new --clearnet --i-know      # bypass Tor (red warning + opt-in flag)
babel mask new --export <path>          # also: passphrase -> Argon2id -> AES-GCM blob
babel mask new --export-avatar <path>   # also: write the 256x256 avatar PNG
babel mask decode <mask://...>          # parse a mask:// blob, print the bundle
babel mask import <blob-path>           # passphrase -> decrypt -> print bundle
babel mask --setup                      # diagnostic: argon2 + Pillow + httpx + Tor
```

`--export` and `--export-avatar` are independent; you can pass
either, both, or neither. `--clearnet` requires `--i-know` on the
non-interactive path (otherwise exit 2 with the warning); the
interactive screen asks for a `y` confirmation instead.

Passphrase is read from `BABEL_MASK_PASS` if set, otherwise prompted
on stdin with masking when a TTY is attached.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | identity generated cleanly |
| 1 | identity generated but a non-fatal step warned (e.g. mail provider unreachable) |
| 2 | invocation error (bad flags, missing `--i-know`, empty passphrase) |
| 3 | I/O error (export path unwritable, blob unreadable) |
| 4 | mail provider unreachable on both primary and fallback |
| 5 | Tor required but no SOCKS5 port answered |
| 6 | wrong passphrase on `import` (AES-GCM `InvalidTag`) |

## 5 - In-app commands and keys

| Key | Effect |
|---|---|
| `n` | new identity (uses current locale + profile + mail toggle) |
| `l` | cycle locale (`en` -> `es` -> `fr` -> `de` -> `neutral`) |
| `p` | cycle profile (`default` -> `writer` -> `trader` -> `researcher`) |
| `t` | toggle Tor / clearnet (clearnet pops a red confirmation panel) |
| `m` | toggle mail fetch (on / off) |
| `x` | export the current identity (asks for passphrase + path) |
| `v` | view the avatar as a small block preview |
| `c` | copy `mask://...` (uses `pyperclip` if importable, else prints) |
| `Esc` / `q` | leave to menu (zeroes the identity buffer) |
| `Ctrl+C` / `Ctrl+Q` | quit the suite (also zeroes the buffer) |

## 6 - Worked walkthrough

```
$ babel mask new --locale en --profile writer
mask://eyJhbGlhcyI6eyJnaXZlbiI6Ik1pcmlhbSIsImZhbWlseSI6IldoaXRsb2NrIiwi
aGFuZGxlIjoibWlyaWFtX3doaXRsb2NrIiwibG9jYWxlIjoiZW4iLCJwcm9maWxlIjoid3J
pdGVyIn0sImJpbyI6Ikxvbmdmb3JtIGVzc2F5cy4gQ29mZmVlIGZpcnN0LCBzZW50ZW5jZX
Mgc2Vjb25kLiBQcmludCBpcyBub3QgZGVhZC4iLCJhdmF0YXJfc2hhIjoiYzM3MmJlMDc4O
GNlNzQ3MzNkYzkwYjU5NTY1ZTU1MGFjYTlhNzM2YzVhMjFiOWQyYzAxMmI4MTRjMjA0YjUw
ZSIsIm1haWxfaGFuZGxlIjoibWlyaWFtX3doaXRsb2NrQGluZG9tYWlsLmNvbSIsInRzIjo
xNzQ3NDgzNTIwfQ
```

Interactive (TUI), with export:

```
                              MASK
  alias       Miriam Whitlock (en, writer)
  handle      miriam_whitlock
  bio         Longform essays. Coffee first, sentences second.
              Print is not dead.
  avatar      [ block preview here ]
  mail        miriam_whitlock@indomail.com  (mail.tm, via Tor)
              inbox: https://mail.tm/...    (open in your browser)
  mask://     [ Ctrl+C copies the URL ]

  [n] new  [l] locale  [p] profile  [t] tor  [m] mail  [x] export
  [v] view avatar  [c] copy  [Esc] back
```

Pressing `x` asks for a passphrase, then a path:

```
  passphrase: ********
  passphrase (confirm): ********
  export to: /home/me/notes/2026-05-17.maskblob
  wrote 248 bytes (Argon2id t=3 m=64MiB p=4 + AES-256-GCM)
```

Re-importing:

```
$ babel mask import /home/me/notes/2026-05-17.maskblob
  passphrase: ********
  alias: Miriam Whitlock  ...
```

## 7 - Architecture

```
tools/mask/
  alias.py             # locale + profile -> AliasSpec; bio templater
  avatar.py            # 8x8 (5x5 mirrored to 10x5) grid -> SVG + PNG
  mail.py              # MailProvider protocol; MailTm + Guerrilla adapters
  bundle.py            # Identity dataclass; Argon2id+AES-GCM export/import
  link.py              # mask:// helpers (thin wrapper over shared.link.invite)
  pipeline.py          # generate_identity(opts, on_step) orchestration
  cli.py               # argparse front-end (Section 4)
  app.py               # Textual screen mounted under babel chrome
  setup_check.py       # contributes to `babel --setup`
  data/                # per-locale JSON catalogs (en/es/fr/de/neutral)
```

**Reused** (per MASTER.md Section 7.2):

- `shared.crypto.aead` - AES-256-GCM encrypt / decrypt
- `shared.crypto.kdf` - Argon2id derivation
- `shared.crypto.secure_mem` - `SecureBytes` passphrase wrapper
- `shared.tor.socks_detect` - port probe for Tor SOCKS5
- `shared.ui.step_indicator` - alias / avatar / mail step progress
- `shared.ui.diff_view` - re-used for the `import`'s diff-against-mask:// view
- `shared.link.invite` - `mask://` codec registered alongside `void://` and `carrier://`

**Wire format** (`mask://`):

```
mask://base64url( canonical_json({
    "alias": {
        "given":   "Miriam",
        "family":  "Whitlock",
        "handle":  "miriam_whitlock",
        "locale":  "en",
        "profile": "writer"
    },
    "bio": "Longform essays. Coffee first, sentences second.",
    "avatar_sha": "<64 hex>",                # sha256 of canonical SVG bytes
    "mail_handle": "miriam_whitlock@indomail.com",   # or null
    "ts": 1747483520                          # unix seconds, rounded to 60s
}) )
```

Canonical JSON: sorted keys, no whitespace. Two encodings of the same
bundle hash to the same base64url string. The avatar PNG bytes are
**not** in the wire format - only the SHA-256 of the SVG round-trips;
the PNG is locally regenerable from a seeded re-render if you keep
the alias.

**Export blob format**:

```
offset  length  field
0       4       magic = b"MASK"
4       16      Argon2id salt
20      12      AES-GCM nonce
32      *       AES-256-GCM(ciphertext || 16B tag)
```

The plaintext inside the AEAD is the canonical-json bundle plus the
avatar PNG bytes (base64url'd inside the JSON under `avatar_png`).
Importing returns the full `Identity`, avatar and all.

**Mail adapter contract**:

```python
class MailProvider(Protocol):
    name: str
    async def acquire(self, alias_handle: str, *, tor: bool) -> MailHandle: ...
```

`acquire()` is responsible for picking a domain, generating or
requesting the address, and returning the `inbox_url` the user opens
in a separate browser. MASK does **not** poll the inbox.

## 8 - Reproducible build notes

- New runtime deps: `httpx[socks]>=0.27`, transitively `socksio`.
  Both BSD-3, on PyPI, hash-locked at release-cut time alongside the
  rest of `requirements.txt`.
- The per-locale JSON catalogs in `tools/mask/data/` are
  `package_data` declared in `pyproject.toml`. `packaging/babel.spec`
  adds them to `datas` so PyInstaller bundles them; the SOURCE_DATE_EPOCH
  pin keeps their on-disk mtime deterministic.
- `socksio` is added to `hiddenimports` in the spec because PyInstaller's
  static analyzer does not always follow the `httpx[socks]` extra.
- No Tor control-port calls from MASK (`shared.tor.control` is unused
  here; MASK only needs the SOCKS5 transport via `socks_detect`).
- Avatar PNG rendering uses Pillow's default zlib settings, which the
  Pillow wheel pins; two consecutive renders of the same seed produce
  byte-identical PNG output.
