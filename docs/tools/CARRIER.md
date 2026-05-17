*confusion of tongues, by design*

```
 ██████╗ █████╗ ██████╗ ██████╗ ██╗███████╗██████╗
██╔════╝██╔══██╗██╔══██╗██╔══██╗██║██╔════╝██╔══██╗
██║     ███████║██████╔╝██████╔╝██║█████╗  ██████╔╝
██║     ██╔══██║██╔══██╗██╔══██╗██║██╔══╝  ██╔══██╗
╚██████╗██║  ██║██║  ██║██║  ██║██║███████╗██║  ██║
 ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝╚═╝  ╚═╝
```

# CARRIER - steganography

## 1 - What this is

CARRIER hides an AES-256-GCM-encrypted payload inside an innocuous
cover file (PNG image, WAV audio). The cover stays visually /
aurally identical to the eye and to the ear; the bytes change in
the lowest bit of each channel sample. Extraction needs the same
passphrase the embedder used. No header magic in the cover means
the file looks like a normal PNG or WAV to a casual inspector --
without the passphrase, there is no way to tell whether anything
is hidden inside.

The pipeline is deliberately simple: passphrase -> Argon2id ->
AES key. Payload -> optional compress -> AES-256-GCM with a
random nonce. The ciphertext (plus a tiny self-framing) is
spread one bit per channel sample across the cover. Extraction
reverses the process.

CARRIER is an action tool. It takes inputs, writes one output,
returns to the menu. No session, no lingering keys, no logs.

## 2 - What it protects

| Surface | Protection |
|---|---|
| Payload contents | AES-256-GCM with key derived from a passphrase via Argon2id (interactive params by default). |
| Payload integrity | GCM authentication tag. Tampered payloads fail to decrypt. |
| Brute-force resistance on weak passphrases | Argon2id with `time_cost=3`, `memory_cost=64 MiB` by default; tunable on the CLI. |
| Plausible deniability of the cover | No magic header inside the cover. The file *is* a normal PNG / WAV; the LSB modifications are visually / aurally imperceptible. |
| Honest capacity | Embedding refuses when the payload would exceed the safe-capacity threshold of the cover (default: 12.5% of channel-bit capacity, leaving the rest as noise margin). |
| Cover-already-tampered detection | Chi-square sanity check on the cover *before* embedding. If the cover already shows LSB-tampering signature, CARRIER warns and (in strict mode) refuses to add more. |
| Key material in RAM | Argon2id output and AES key live in `shared.crypto.secure_mem.SecureBytes`. Wiped when the operation ends. |
| Nonce reuse | Each embed generates a fresh random 12-byte nonce; the nonce ships inside the payload framing, not as a separate piece of metadata. |

## 3 - What this does NOT protect

| Risk | Why it survives |
|---|---|
| Lossy re-encoding (JPEG, MP3, AAC) | LSBs are destroyed by quantisation. CARRIER refuses lossy cover formats entirely; do not re-encode a CARRIER output through a lossy codec, the payload will be lost. |
| Resampling, image resize, cropping | Same. The pixel grid changes; the bit positions change with it. |
| Forensic comparison against the original cover | Anyone who has the *original* unmodified cover file can subtract it from the CARRIER output and read the LSB plane. Use a fresh cover, not one you have publicly shared before. |
| Statistical attacks with a known cover distribution | If an analyst knows the cover came from a specific camera or generator and has a model of that source's LSB distribution, the chi-square skew can betray the presence of *something*. CARRIER will not embed into a cover that already looks tampered, but cannot promise an analyst-blind embedding. |
| Existence-of-tool detection | The presence of `babel` on disk plus a recently-modified PNG is itself a signal. CARRIER cannot launder its own footprint. |
| Endpoint compromise | If something on your machine reads the plaintext payload before it reaches CARRIER, or the passphrase as you type it, CARRIER cannot help. |
| Weak passphrases under high-budget attackers | Argon2id raises the cost per guess; it does not make a four-digit PIN safe. Pick a real passphrase. |
| Coercion ("decrypt this or else") | CARRIER has no duress key. There is no second passphrase that yields a plausible decoy. Plausible deniability is at the cover level (the file looks like an ordinary PNG/WAV), not at the ciphertext level. |
| Side channels (timing, branch prediction) | The chi-square pass and the LSB scatter are constant-pattern but not constant-time. Out of scope for a local file-processing tool. |
| Quantum HNDL | AES-256 has a comfortable margin under Grover; the Argon2id passphrase derivation does not. A future post-quantum migration would replace the KDF, not the cipher. |
| Cover that was already noisy | The chi-square check is a heuristic. A naturally noisy cover (high-ISO photo, dithered audio) will pass the check even if it already contains stego from another tool. |

## 4 - CLI flags

```
babel carrier embed <cover> <payload>            # embed payload, write <cover>.carrier
babel carrier embed -o <out> <cover> <payload>   # explicit output path
babel carrier extract <stego>                    # extract to stdout (or -o file)
babel carrier extract -o <out> <stego>           # explicit output path
babel carrier capacity <cover>                   # report safe-capacity in bytes
babel carrier inspect <cover>                    # run chi-square; report verdict
babel carrier ... --time-cost <int>              # Argon2id time cost (default 3)
babel carrier ... --memory-cost <kib>            # Argon2id memory cost (default 65536 KiB = 64 MiB)
babel carrier ... --strict                       # refuse to embed into a cover that fails chi-square
babel carrier ... --no-compress                  # skip the zlib pre-pass
babel carrier ... --json                         # emit results as JSON
babel carrier --setup                            # diagnostic
```

Passphrase is read from stdin (TTY-masked when possible). The
environment variable `BABEL_CARRIER_PASS` is honoured for scripted
use; do not store secrets in shell history.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | invocation error (bad flags, missing input) |
| 3 | I/O error |
| 4 | cover format unsupported |
| 5 | payload too large for cover's safe capacity |
| 6 | wrong passphrase or tampered payload (extract failed authentication) |
| 7 | cover already shows LSB tampering (in `--strict` mode) |

## 5 - In-app commands and keys

The chrome screen is a four-line form: cover path, payload path,
passphrase (masked), aggressive toggle, then a verdict pane.

| Key | Effect |
|---|---|
| `Tab` | next field |
| `Enter` on the last field | run the operation |
| `e` | switch to embed mode |
| `x` | switch to extract mode |
| `c` | switch to capacity-only mode (no payload needed) |
| `i` | switch to inspect mode |
| `Esc` | back to menu |
| `Ctrl+C`, `Ctrl+Q` | quit suite |

The verdict pane shows: capacity in bytes, chi-square p-value,
the operation's outcome (`written to <path>` or
`payload extracted to <path>`), and a hex preview of the first 64
bytes of the payload (extract mode) or first 64 bytes of the
modified cover (embed mode).

## 6 - Worked walkthrough

```
$ babel carrier embed ~/cover.png ~/notes.txt
passphrase: ********
                          CARRIER / embed
+----------------------------------------------------------+
| cover           cover.png  (1280x720, 3 channels)         |
| safe capacity   345 KiB                                   |
| chi-square      p=0.87  (looks untampered)                |
| payload         notes.txt  (12 KiB compressed -> 8 KiB)   |
| embedded        12,234 bytes into 1,920,000 channel-bits  |
| output          /home/u/cover.carrier.png                 |
+----------------------------------------------------------+
$ babel carrier extract ~/cover.carrier.png -o /tmp/notes.txt
passphrase: ********
extracted 12,231 bytes to /tmp/notes.txt
```

## 7 - Architecture

```
tools/carrier/
  __main__.py
  cli.py                 # argparse front-end
  app.py                 # Textual screens
  setup_check.py
  pipeline.py            # embed / extract orchestration
  header.py              # payload framing
  capacity.py            # per-format capacity calc
  chisquare.py           # LSB-tampering detector
  core/
    png.py               # Pillow-backed LSB on RGB channels
    wav.py               # stdlib wave LSB on PCM samples
```

### Payload framing

Inside the cover, the bit-stream produced by the LSB writer is:

```
+----------------+----------------+------------------+------------------------+
| salt 16 bytes  | nonce 12 bytes | length 4 B (BE)  | ciphertext (incl. tag) |
+----------------+----------------+------------------+------------------------+
```

Total fixed overhead: 32 bytes (salt 16 + nonce 12 + length 4).
The ciphertext carries a 16-byte GCM authentication tag at its
end; the length field counts ciphertext+tag together.

**There is no magic field by design.** A plain (non-CARRIER)
cover reads 32 random bits as salt+nonce+length, runs the (slow,
by design) Argon2id derivation against the false salt, then fails
GCM authentication. The presence of a magic byte would be a
signal to anyone walking the LSB plane that the file is a CARRIER
output; relying on GCM's own authentication for validity is what
gives the cover its plausible deniability.

The length field is bounded by `read_header(max_bytes=...)` to
the cover's safe-capacity in bytes, so a tampered or random cover
cannot drive the extractor to read past the LSB plane. Extraction
outcomes are:

* Plain cover, wrong passphrase, right passphrase against a plain
  cover: all three indistinguishable from the outside -- each one
  runs Argon2id then fails GCM tag check.
* Right passphrase against a CARRIER cover: GCM verifies, exit 0.

### KDF parameters

- Argon2id, interactive class. Defaults: `time_cost=3`,
  `memory_cost=65536 KiB (64 MiB)`, `parallelism=4`,
  `hash_length=32 bytes` (AES-256 key).
- `--time-cost` and `--memory-cost` override at the CLI; the
  values used at embed time are not stored in the cover, so the
  same overrides must be passed at extract time. (Storing them
  in the cover would weaken plausible deniability; the user owns
  the burden of remembering.)

### Capacity calculation

- **PNG (RGB or RGBA)**: `width * height * (3 if RGB else 4)` bits
  of channel capacity. Safe-capacity = `total_bits * 0.125`. The
  factor is conservative -- below 1/8 of channels touched, chi-square
  detection becomes statistically unreliable.
- **WAV (PCM)**: `n_samples * n_channels` bits of capacity. Same
  0.125 safety factor.

Capacity refusal (exit code 5) fires when
`framed_length > safe_capacity`. CARRIER does not silently spill
into "unsafe" capacity.

### Chi-square sanity check

For each byte / sample value in the cover, count occurrences of
pairs `(2k, 2k+1)`. In an untampered LSB plane these pairs are
typically unequal (sensor noise, encoder rounding); after LSB
embedding into a meaningful fraction of channels, they tend
toward equality. We compute the chi-square statistic against the
"all pairs equal" null hypothesis (the Westfeld-Pfitzmann chi-square
attack): small chi2 (and **high** p-value) means observed counts are
consistent with the LSB-embedded null, i.e. the cover looks
tampered.

CARRIER reports the p-value and:

- `--strict` mode refuses to embed when `p > 0.95`.
- Default mode warns but proceeds; the user can override per
  cover.

### Dependencies

- `Pillow>=10` (new). PNG LSB requires real pixel access; hand-rolling
  PNG IDAT decode (filter handling per scanline) is hundreds of
  lines for code that Pillow has had under fuzzing for a decade.
  BSD-3, on PyPI, no GPL surprises.
- `argon2-cffi>=23` (new). Argon2id reference implementation. The
  PHC-vetted memory-hard KDF; `cryptography` does not ship Argon2.
  MIT, pure-cffi binding to argon2.
- `cryptography` (already pinned). AES-256-GCM and HKDF.

`shared/` modules consumed:

- `shared.crypto.aead.AESGCM256` — thin AES-256-GCM wrapper.
- `shared.crypto.kdf.argon2id`, `shared.crypto.kdf.hkdf`.
- `shared.crypto.secure_mem.SecureBytes` — mlock'd AES key + KDF intermediates.
- `shared.ui.diff_view.render_diff` — extract-mode field summary.
- `shared.ui.hex_view.render_hex` — payload preview.
- `shared.ui.progress.render_bar` — embed/extract progress for large covers.
- `shared.ui.compact.is_compact`.

## 8 - Reproducible build notes

`Pillow` and `argon2-cffi` both bundle compiled extensions; the
suite's pinned `requirements.lock` (built at release-cut time)
pins exact wheel hashes for the supported `python:3.11.10` base.
The `Dockerfile.build` already constrains the build environment;
no per-tool override needed.

## 9 - Threat-model worksheet (Forge output)

Forge framework: LINDDUN, same as STRIP.

| LINDDUN axis | Concern | CARRIER's answer |
|---|---|---|
| **L**inkability | Two covers with the same passphrase share an extractable identity | Each embed uses a fresh salt and a fresh nonce; the AES key differs per cover even with the same passphrase. |
| **I**dentifiability | The cover itself names its source | Out of scope for CARRIER; STRIP launders metadata. Run STRIP on your cover before CARRIER. |
| **N**on-repudiation | Embed signature ties the payload to a sender | CARRIER does not sign. The output is symmetric; both ends share the passphrase. |
| **D**etectability | An observer can tell something is hidden | The cover passes chi-square in default mode; presence of CARRIER on disk is itself a signal (documented in Section 3). |
| **D**isclosure of information | The payload leaks under attack | GCM authentication and Argon2id together resist tampering and brute-force; weak passphrases break the chain (Section 3). |
| **U**nawareness | User doesn't know capacity or risk | `capacity` and `inspect` subcommands surface both. |
| **N**on-compliance | Hidden information violates a policy | Out of scope; CARRIER does not gate its own use. |
