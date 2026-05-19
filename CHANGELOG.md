# Changelog

Versions follow `MAJOR.MINOR.PATCH`.

## Unreleased -- 2026-05-19  (Phase 7: navigation + multi-instance)

The v1.0.0 suite was functionally complete but navigationally
rough -- tool home views were info stubs, only one tool could
run at a time, and pasting an invite link in the menu did
nothing.  This phase makes the suite operable end-to-end from
`babel` alone.

### Navigation

- Tool home views (`babel/views.py`) drop the Phase-1 info stubs
  and now mount the live tool surface directly (`VoidView`,
  `MaskView`, `StripView`, `CarrierView`, `MirageView`).  The
  chrome's `enter_tool` mounts the view inside the content slot
  -- no more `self.exit` and relaunch.  Per-tool surfaces lazily
  import their heavy deps so `babel` boot stays fast.
- `F1` / `Alt+H` opens a help overlay that auto-discovers the
  visible view's `BINDINGS` plus the suite-level keys.
- `Alt+M` opens a slot-switcher overlay listing every live
  service + the foreground action.  `Enter` jumps, `Ctrl+W`
  closes, `Esc` returns.
- The main menu accepts pasted `void://` / `mask://` /
  `carrier://` links and routes them with `prefill` to the right
  tool.  Routing goes through `shared.link.invite.looks_like`
  (no per-tool prefix detection).
- Live slot state shows in the menu: a tool whose SERVICE is
  alive renders with `(live in slot N)` in cyan.
- Boot nudge: the menu's hints line shows
  `<Alt+1..4> jump  <Alt+0> menu  <Ctrl+W> close  <F1> help` for
  the first 5 seconds of a session (suppressed on the Termux
  60-col floor).

### Multi-instance

- Two `VOID`s (or `MIRAGE`s, or a mix) coexist in distinct
  slots.  Default digit re-entry focuses the existing slot;
  `Shift+<digit>` or the symbol-row fallback (`!`, `@`, `#`,
  `$`, `%`) forces a new instance.
- `BABEL_MAX_SERVICES` (default 4) caps the slot count.  Beyond
  the cap, new-instance attempts flash
  `"slots full -- close one with Ctrl+W"` and refuse gracefully.
- `Ctrl+W` purges the current SERVICE (calls `purge_local`
  under the 1-second cooperative budget) and frees its slot;
  other services keep running.  `Ctrl+C` / `Ctrl+Q` quits the
  suite and purges every SERVICE in parallel inside the 4-second
  budget from MASTER.md 4.4.

### Architecture

- Service Protocol is implemented by a *separate* object owned
  by the View (`view.service`), per the 2026-05-19 FORGE
  decision in `docs/ARCHITECTURE.md`.  Pentest tests exercise
  the Protocol without importing Textual.
- New module `shared/ui/overlay.py`: pure-string renderers
  (`render_help`, `render_slot_switcher`, `bindings_from_class`,
  `tagline_from_docstring`) + lazy Textual widget wrappers.
- New doc `docs/NAVIGATION.md`: 11-section navigation spec --
  every view, every binding, every transition, the SERVICE vs
  ACTION flow, the 60x20 Termux downgrades, the ASCII state
  diagram.

### Known deviations from Phase 7 spec

The VOID `*View` is a lobby-only surface.  The chat / connecting /
starmap flows still live in `tools/void/client/app.py` as
Textual `Screen` subclasses.  Submitting the lobby in-chrome
calls `ChromeApp.void_session_bridge`, which exits the chrome
and lets `babel.__main__` relaunch the legacy `VoidApp` with
the populated args (via `BABEL_VOID_*` env handoff).  Rewiring
the full session into a `push_view`-style flow is post-1.0 work
and tracked in `RELEASE_NOTES.md`.

The main menu's `[h]` (3-panel first-time wizard) and `[s]`
(TUI setup aggregator) bindings remain absent -- same status
as v1.0.0.  `babel --help` and `babel --setup` cover both from
the CLI.

### Tests

`pentest/babel/test_*.py` adds 44 tests (no Textual imports)
covering:
- every transition in NAVIGATION.md
- two VOIDs, two MIRAGEs, mixed, slot-full refusal
- paste routing for every scheme + garbage rejection
- help-overlay binding auto-discovery + 60-col render
- slot-switcher render + jump/close callbacks
- every renderable line at the Termux 60-col floor
- 4-second purge budget for parallel-close on quit

`pentest/` itself stays `.gitignore`d per the project convention;
the harness is reproducible from the source tree.

---

## v1.0.0 — 2026-05-17  (Tower of Babel -- first suite release)

VOID stops being a single tool and becomes the first room of the
Tower of Babel: a privacy / anti-surveillance suite of five
single-purpose terminal tools under a shared chrome, build system,
and moral posture.  The suite ships under the same 0BSD licence.

Phase 0 lifted VOID into the new `babel/` + `shared/` + `tools/`
layout without behavioural change; Phases 1-5 added the multiplex
chrome and the four new rooms (STRIP, CARRIER, MASK, MIRAGE); Phase 6
ran the full pentest pass (259/259 green, see `pentest/REPORT.md`),
honesty-fixed the docs against the audit findings, and locked this
1.0 stanza.

The 1.0 designation reflects the *suite* maturing past its single-
tool predecessor.  VOID's wire format and ratchet are unchanged from
v0.5.0; users upgrading from v0.5.0 see no compatibility break in
the chat protocol.

### Known deviations from MASTER.md Section 4

The architecture lives up to MASTER.md's invariants (continuous
chrome, multiplex slot model, tool isolation, no rolled-your-own
crypto, no banned characters, Tor-by-default networking, no
persistent state).  The following structural items differ from the
prescribed file layout and are tracked for a post-1.0 cleanup pass:

  - `babel/app.py`, `babel/nav.py`, `babel/setup.py`, `babel/style.tcss`
    are not present as separate files; their functionality is folded
    into `babel/shell.py` + `babel/menu.py` + inline `DEFAULT_CSS`.
  - `shared/crypto/padding.py`, `shared/tor/ephemeral_onion.py`,
    `shared/ui/borders.py`, `shared/install/` are deferred or folded
    into adjacent modules (e.g. ephemeral-onion logic is a method on
    `TorControl` rather than its own module).
  - Several tools list `shared/ui/progress.py` and `shared/ui/diff_view.py`
    as "reused" in MASTER.md Section 7 but do not yet import them
    (STRIP, CARRIER, MIRAGE wrt `progress`; MASK wrt `diff_view`).
    They are available; integration was deferred to a follow-up pass
    rather than added late in the release-cut window.
  - The main menu does not bind `[h]` (3-panel first-time wizard,
    MASTER.md Section 6.2) or `[s]` (TUI setup aggregator, 6.3); the
    CLI paths `babel --help` and `babel --setup` cover both today.
  - The MASK TUI's encrypted-export key (`[x]`) is intentionally
    absent pre-1.0; `babel mask new --export PATH` is the supported
    path.

### Known minor issues (non-blocking)

- Pytest emits 8 `DeprecationWarning`s during the suite pass:
  `datetime.utcnow()` in `babel/shell.py:252` (Python 3.12+
  deprecation), and `argon2.__version__` in
  `tools/mask/setup_check.py:32` (argon2-cffi packaging-metadata
  deprecation).  Neither affects behaviour; both are scheduled for
  a 1.0.x cleanup.

### What's new since v0.5.0 (Tower of Babel Phase 0 + 1 + 2 + 3 + 4 + 5)

### Phase 5 — MIRAGE (cover traffic generator)

First *service*-flavoured tool in the Tower (MASTER.md 4.4): the
chrome can slot MIRAGE alongside VOID and the user can flip between
the foreground tools while MIRAGE keeps generating background HTTP
noise. Real httpx requests, real DNS through `socks5h://` so the
local resolver never sees the target hostname, real session dwell
times, hard token-bucket caps on bandwidth + request-rate, advisory
CPU cap. Tor SOCKS5 by default; clearnet requires `--clearnet
--i-know`. No on-disk state; ring-buffer event log is in RAM.

- New tool `tools/mirage/`:
    - `tools/mirage/caps.py` -- `TokenBucket` (leaky-bucket
      rate limiter with `try_consume` + `force_consume`; the
      latter allows the bucket to carry a deficit so oversized
      responses pay back across the next gate) and `CpuMeter`
      (one-minute sliding average of fractional CPU). Pure
      logic; tests drive both with synthetic clocks.
    - `tools/mirage/profile.py` -- `ProfileSpec` dataclass and
      the four shipped profiles (`office_worker`, `developer`,
      `casual_browser`, `researcher`) with per-profile `rpm_typical`,
      `dwell_seconds`, `accept_language`, and a small public UA
      rotation pool.
    - `tools/mirage/sites.py` -- static, version-pinned per-profile
      site catalogs (host, path, Zipf rank) of common public
      destinations. Module-level literal so PyInstaller picks it
      up without a `package_data` row.
    - `tools/mirage/schedule.py` -- `zipf_draw` (1/rank weighted
      selection from a catalog) and `dwell_for` (uniform-from-
      profile draw, lower-bounded by `60 / --rate-rpm` so the
      user cap always wins on the upper bound of frequency).
    - `tools/mirage/engine.py` -- the async request loop. Gates
      every fetch through the rate and bandwidth buckets;
      ``_settle_bandwidth`` force-charges the actual response
      size after the fact, so the bandwidth bucket is a leaky
      integrator whose long-run drain equals `--bw-kbps`. Holds
      a bounded `collections.deque` ring buffer (default 256
      events); honours `--duration`, pause/resume, NEWNYM
      rotation, and a 1-second `stop()` budget. The HTTP
      transport is injected (`Transport` Protocol) so pentest
      drives the engine without httpx and the chrome drives it
      with `HttpxTransport` over `socks5h://127.0.0.1:<port>`.
    - `tools/mirage/service.py` -- `MirageService`, the
      ``babel.shell.Service``-Protocol wrapper. Reports rpm +
      KB/min in `status_line`, contributes `TOR=on` to the
      footer only when running under Tor, reports the configured
      caps via `resource_caps`, and routes `purge_local` to the
      engine's `stop()`.
    - `tools/mirage/cli.py` -- argparse front-end with
      `start` / `profiles` / `status` / `--setup`. Ceilings
      validated at parse time (`MAX_BW_KBPS = 4096`,
      `MAX_RATE_RPM = 240`, `MAX_CPU_PCT = 25.0`,
      `MAX_ROTATE_MIN = 1440`, `MAX_DURATION = 86400`); exits 2
      on any violation. `--dry-run N` plans N fetches without
      sending; `--honest` emits one stderr line per fired
      request; `--json` switches that line to canonical JSON.
      Exit codes per MIRAGE.md Section 4.
    - `tools/mirage/app.py` -- Textual screen mounted under the
      babel chrome. Cycle toggles for profile / locale / Tor /
      honest mode, snapshot panel that ticks once per second,
      live ring-buffer view when honest mode is on, `+/-` and
      `[/]` for live envelope nudges, `[n]` for a one-shot
      NEWNYM, `[Esc]` purges and returns to the menu.
    - `tools/mirage/setup_check.py` -- contributes to
      `babel --setup`. Verifies httpx + Tor SOCKS5
      reachability + Tor control port (informational; only
      matters for `--rotate-min`) + profile registry sanity.
- `docs/tools/MIRAGE.md` -- full per-tool spec, populated from a
  STRIDE-style threat-model pass (Forge). "What this protects" and
  "What this does NOT protect" tables both populated with one row
  per concrete claim made in the code; no aspirational protections.
- `pentest/mirage/` -- 13 test modules covering every row in the
  "What this protects" table:
    - `test_token_bucket.py` -- pure-logic regressions for the
      bucket + cpu-meter math, including clock-goes-backwards
      and reset-after-drain.
    - `test_rate_cap.py` -- the engine cannot exceed
      `--rate-rpm` under burst pressure (parametrised over 10,
      30, 60 rpm).
    - `test_bandwidth_cap.py` -- the engine cannot exceed
      `--bw-kbps` (parametrised over 50, 200, 1000 KB/s) plus a
      monotonicity check: a tighter cap yields a lower observed
      rate.
    - `test_tor_required.py` -- `MirageEngine.start()` refuses
      to start when Tor is unreachable and `--clearnet` was not
      passed; clearnet path starts cleanly.
    - `test_clearnet_warning.py` -- the CLI refuses
      `--clearnet` without `--i-know`, prints the red banner,
      and accepts `--clearnet --i-know` end-to-end via
      `--dry-run`.
    - `test_zipf_draw.py` -- rank-1 sites dominate rank-20 by
      the expected ratio; `dwell_for` respects the rate-cap
      floor and stays inside the profile range when not bound.
    - `test_service_contract.py` -- `MirageService` is
      Protocol-compliant; `resource_caps` reports the engine
      config; the footer contribution starts empty, switches to
      `TOR=on` once the engine runs under Tor; the service
      registers cleanly with a real `ServiceRegistry`;
      `purge_local` returns in under 1 second and is idempotent.
    - `test_no_disk_writes.py` -- no engine-related file appears
      under `$TMPDIR`, the cwd, or `~/.config/babel` after a
      live run; the ring buffer is a `collections.deque`, not
      a file.
    - `test_honest_mode.py` -- the per-event emitter produces
      one stderr line per fired request in the documented shape.
    - `test_purge_zeros_buffers.py` -- `stop()` closes the
      transport, resets both buckets to capacity, is idempotent,
      and cancels the in-flight task in under 1 second.
    - `test_profile_registry.py` -- every profile's `sites_key`
      resolves to a non-empty catalog; MIRAGE's locales match
      MASK's; profile order is stable; the `rpm_clamped` helper
      collapses against a tight cap; `accept_language` covers
      every locale; the UA pool is non-empty and Mozilla-shaped.
    - `test_setup_check.py` -- the diagnostic returns
      `(int, list[str])`, names MIRAGE on the first line, exits
      0 or 1, and lists all four profiles.
    - `test_multiplex_with_void.py` -- THE Phase-5 gate:
      `MirageService` and a VOID-shaped mock share slots 1 and
      2 of a real `ServiceRegistry`; the footer aggregates
      `TOR` to "2 svcs"; closing VOID's slot leaves MIRAGE
      running; `close_all` purges both services in well under
      MASTER.md's 4-second budget; a third service lands in
      slot 3 as expected.

### Suite wiring

- `babel/menu.py` -- entry `[5] MIRAGE` is now live; the `5`
  binding calls `app.enter_tool('mirage')` instead of the noop.
- `babel/__main__.py`:
    - `_run_mirage` dispatch + `head == "mirage"` branch + menu
      return-value `"mirage"` routed to `_run_mirage([])`.
    - `_run_setup` aggregator picks up MIRAGE alongside VOID,
      STRIP, CARRIER, and MASK.
- `packaging/babel.spec` -- ten new `tools.mirage.*` entries in
  `hiddenimports` so PyInstaller does not drop the module set.
  No new `datas`; the profile catalogs are plain Python.

### Dependencies

- No new runtime dependencies. `httpx[socks]>=0.27` already pinned
  for Phase 4 (MASK) -- MIRAGE shares it. `socksio` stays in the
  spec's `hiddenimports`.

### Entry points

- New legacy-style alias `mirage = "babel.__main__:main"` alongside
  `babel`, `void`, `strip`, `carrier`, and `mask`.

### Phase 5 verification

- All `pentest/mirage/*` tests pass.
- All prior-phase pentest suites (`babel`, `strip`, `carrier`,
  `mask`, `void`) still pass.
- Smoke-tested `babel mirage profiles`, `babel mirage start --dry-run`,
  `babel mirage --setup`, and `babel --setup` (MIRAGE appears in
  the aggregator output).

### Phase 4 — MASK (disposable identity generator)

Second action tool of the Tower. Generates a coherent disposable
identity in one keystroke: locale-coherent alias drawn from a
per-locale public-domain catalog (en / es / fr / de + neutral),
profile-tagged 2-3 line bio, locally-rendered geometric avatar
(5x5 grid mirrored to 10x5, seeded by SHA-256 of the alias handle),
and an optional temp-mail handle acquired via mail.tm with a
guerrillamail fallback. Tor SOCKS5 is mandatory by default;
`--clearnet` requires `--i-know` and shows a red warning. Identity
lives in RAM; export is opt-in (passphrase -> Argon2id -> AES-256-GCM).

- New tool `tools/mask/`:
    - `tools/mask/alias.py` -- per-locale catalog loader (via
      `importlib.resources`), `AliasSpec` dataclass, profile-aware
      bio templater. Handles are lowercase ASCII-folded so they
      round-trip through mail.tm without diacritics.
    - `tools/mask/avatar.py` -- 5x5 grid (mirrored to 10x5)
      seeded by `SHA256(handle)`; renders to a canonical SVG
      (whitespace-stable, hash-stable) and to a 256x256 PNG via
      Pillow with deterministic compression settings.
    - `tools/mask/mail.py` -- `MailProvider` Protocol with two
      adapters: `MailTm` (POST `/accounts`, picks domains uniformly
      at random across the returned list to avoid a per-install
      tell) and `GuerrillaMail` (fallback). Both go through Tor
      SOCKS5 by default via a per-call `httpx.AsyncClient`;
      `TorRequired` is raised BEFORE any HTTP request if no
      SOCKS5 port answers. MASK does not poll the inbox -- the
      user opens `inbox_url` themselves.
    - `tools/mask/bundle.py` -- `Identity` dataclass, export blob
      layout (`b"MASK" || salt(16) || nonce(12) || ct||tag`), and
      `passphrase_as_secure()` helper that copies the passphrase
      into a `SecureBytes` for the lifetime of an export / import
      call.
    - `tools/mask/link.py` -- thin `build` / `parse` over
      `shared.link.invite` for the `mask://` scheme.
    - `tools/mask/pipeline.py` -- async orchestrator
      `generate_identity(opts, on_step)` walking the four phases
      (alias -> avatar -> mail -> bundle) and emitting `Step`
      callbacks for the TUI's `StepIndicator`.
- `tools/mask/cli.py` -- argparse front-end with subcommands
  `new` / `decode` / `import`. Passphrase via `BABEL_MASK_PASS` env
  or stdin (masked). Exit codes per MASK.md Section 4.
- `tools/mask/app.py` -- Textual screen with cycle toggles for
  locale / profile / Tor / mail, identity preview, and
  `StepIndicator` block.
- `tools/mask/setup_check.py` -- contributes to `babel --setup`.
  Verifies Pillow + argon2-cffi + httpx + mlock + Tor SOCKS5.
- `tools/mask/data/{en,es,fr,de,neutral}.json` -- public-domain
  census-frequency name catalogs (~50 given + ~50 family per
  locale) plus profile-tagged bio fragments. Declared as
  `package_data` in `pyproject.toml`; bundled by
  `packaging/babel.spec` as PyInstaller `datas`.
- `docs/tools/MASK.md` -- full per-tool spec, populated from a
  LINDDUN threat-model pass (Forge). "What this protects" and
  "What this does NOT protect" tables both populated.
- `pentest/mask/` -- 11 test modules (54 tests) covering every row
  in the "What this protects" table: alias locale coherence, ASCII
  handle, deterministic avatar bytes, avatar local-only (no
  network), no-disk-during-generate, export round-trip, wrong
  passphrase failure, SecureBytes zeroing, mask:// round-trip,
  Tor-required-for-mail, clearnet-warning-required, setup_check
  contract.

### Shared infrastructure for Phase 4

- `shared/link/invite.py` -- multi-scheme codec promised by
  MASTER.md Section 5.6. Knows `void://`, `carrier://`, and the
  new `mask://`. Canonical-json + base64url, padding stripped on
  encode and re-added on decode; per-scheme schema enforced both
  on `encode()` and `decode()` so a body with smuggled keys is
  rejected at the gateway. `looks_like()` returns the matching
  scheme prefix without parsing the body, for paste-autofill in
  the lobby.
- `shared/ui/step_indicator.py` -- generalised from VOID's
  `ConnectingScreen` step block. Pure `render_steps()` renderer
  (lazy Textual import so headless tests do not require
  `textual`) plus an `advance()` helper that returns a new list
  without mutating input. Used by MASK and any future tool with
  named phases.
- `pentest/babel/test_invite_codec.py` (10 tests) and
  `pentest/babel/test_step_indicator.py` (5 tests) cover the
  shared modules.

### Suite wiring

- `babel/menu.py` -- entry `[2] MASK` is live; the `2` binding now
  calls `app.enter_tool('mask')` instead of the no-op stub.
- `babel/__main__.py`:
    - `_run_mask` dispatch + `head == "mask"` branch + menu
      return-value `"mask"` routed to `_run_mask([])`.
    - `_run_setup` aggregator picks up MASK alongside VOID, STRIP,
      and CARRIER.

### Dependencies

- `httpx[socks]>=0.27` (new). Async HTTP client with built-in
  SOCKS5 transport via `socksio`. BSD-3, ~13K stars, maintained
  by the Encode org. Pinned in `requirements.txt` and
  `pyproject.toml`; `socksio` added to PyInstaller `hiddenimports`.

### Entry points

- New legacy-style alias `mask = "babel.__main__:main"` alongside
  `babel`, `void`, `strip`, and `carrier`.

### Phase 4 verification

- 54 / 54 `pentest/mask/*` tests pass.
- 15 / 15 new `pentest/babel/{test_invite_codec, test_step_indicator}`
  tests pass.
- All prior-phase pentest suites (`babel`, `strip`, `carrier`,
  `void`) still pass; 176 tests green in total against the
  Phase 4 source.
- Smoke-tested `babel mask new --no-mail`, `babel mask --setup`,
  and `babel --setup` (MASK appears in the aggregator output).

### Phase 3 — CARRIER (steganography)

Third room of the Tower. Hides an AES-256-GCM-encrypted payload in
the LSB plane of a PNG or WAV cover. Passphrase -> Argon2id ->
AES key. No magic header in the cover -- the GCM tag is the
validity signal, so a scan-all-files attack has to run Argon2id
on every file (the same per-guess cost as a brute force).

- New tool `tools/carrier/`:
    - `tools/carrier/core/png.py` -- Pillow-backed LSB on RGB / RGBA / L
      channels. Operates on the raw channel-byte buffer so each bit
      lands in exactly one channel byte.
    - `tools/carrier/core/wav.py` -- stdlib `wave`, LSB on the low
      byte of each PCM sample (preserves the high byte that carries
      most of the audio amplitude).
    - `tools/carrier/header.py` -- 32-byte framing: salt (16) + nonce
      (12) + length (4 BE). No magic field; length is clamped to
      the cover's safe-capacity to defang junk inputs.
    - `tools/carrier/capacity.py` -- per-format channel-bit counter
      with a default 0.125 safety factor (below which chi-square
      detection is statistically unreliable).
    - `tools/carrier/chisquare.py` -- Westfeld-Pfitzmann chi-square
      LSB-tampering detector. Stdlib-only (Wilson-Hilferty CDF
      approximation; no scipy).
    - `tools/carrier/pipeline.py` -- end-to-end embed / extract.
      Argon2id intermediate key lives inside a `SecureBytes`
      mlock'd buffer for the duration of the AES call.
- `tools/carrier/cli.py` -- subcommands `embed`, `extract`,
  `capacity`, `inspect`. Passphrase via `BABEL_CARRIER_PASS` env
  or stdin (masked). Exit codes per CARRIER.md Section 4.
- `tools/carrier/app.py` -- Textual screen with mode toggles
  (e/x/c/i) + cover/payload/passphrase inputs + hex preview.
- `tools/carrier/setup_check.py` -- contributes to `babel --setup`.
  Verifies Pillow + argon2-cffi + mlock status.
- `docs/tools/CARRIER.md` -- full per-tool spec with LINDDUN threat
  model.
- `pentest/carrier/` -- 58 tests covering AEAD round-trip, Argon2id
  determinism, header pack/unpack with size clamps, capacity math,
  chi-square direction, PNG / WAV LSB exactness, end-to-end
  embed/extract, wrong-passphrase auth failure, oversized-payload
  refusal, and strict-mode chi-square refusal on a tampered
  fixture.

### Shared infrastructure for Phase 3 (and Phase 4+)

- `shared/crypto/aead.py` -- thin AES-256-GCM wrapper. One audit
  point for the cipher; replaces ad-hoc `AESGCM(...)` calls.
- `shared/crypto/kdf.py` -- `argon2id` (CARRIER, future MASK) and
  `hkdf` (VOID ratchet, future tools).
- `shared/ui/hex_view.py` -- `render_hex` pure renderer + `HexView`
  Textual widget. Consumed by CARRIER extract preview; future use
  in VOID `/whoami` extended view.

### Suite wiring

- `babel/menu.py` -- entry `[4] CARRIER` lit up.
- `babel/__main__.py` -- `_run_carrier` dispatch branch; menu
  selection routed to the interactive CLI mode.
- `babel/__main__.py` `_run_setup` aggregator picks up CARRIER's
  diagnostic alongside VOID and STRIP.

### Dependencies

- `Pillow>=10` (new). PNG cover handling. BSD-3, on PyPI.
- `argon2-cffi>=23` (new). Argon2id reference implementation. MIT.
- `cryptography` (already pinned). Now reused via the new
  `shared/crypto/aead.py` and `shared/crypto/kdf.py` shims.

### Entry points

- New legacy-style alias `carrier = "babel.__main__:main"`.



### Phase 2 — STRIP (metadata laundry)

The second room of the Tower opens. STRIP is an *action* tool
(MASTER.md 4.4): drop a file in, see what was inside, write the
laundered copy out. Local-only, no network.

- New tool `tools/strip/` with a focused per-format byte-level
  stripper for each supported container:
    - `tools/strip/core/jpeg.py` — APP-segment walker with a
      built-in TIFF parser. Strips EXIF (Make, Model, GPS, DateTime,
      Software, Artist, serial numbers, lens info), XMP, IPTC,
      COM markers, vendor APP segments. Aggressive mode also drops
      ICC profiles and Adobe APP14 authoring tags.
    - `tools/strip/core/png.py` — chunk-level walker. Strips tEXt,
      iTXt, zTXt, tIME, eXIf. Aggressive mode also drops iCCP and
      sRGB.
    - `tools/strip/core/pdf.py` — pypdf-backed. Strips `/Info` dict,
      `/Metadata` XMP stream, and replaces `/ID` array with a fresh
      random pair. Encrypted PDFs are refused (exit 4) rather than
      silently bypassed.
    - `tools/strip/core/docx.py` — zipfile + ElementTree. Replaces
      `docProps/core.xml` and `docProps/app.xml` with empty stubs;
      drops `docProps/custom.xml` entirely and cleans manifest
      references. Aggressive mode also scrubs `w:rsid*` attributes
      and `<w:ins>`/`<w:del>` track-changes wrappers.
    - `tools/strip/core/mp3.py` — ID3v2 (with per-frame name
      diff), ID3v1, and APEv2 -- whole tag blocks removed.
- `tools/strip/cli.py` — argparse front-end with `--batch`,
  `--aggressive`, `--hash-rename`, `--quiet`, `--json`, `--dry-run`,
  `--setup`, `--in-place`. Exit codes follow STRIP.md Section 4.
- `tools/strip/app.py` — minimal Textual screen for the in-chrome
  flow: path input + aggressive / hash-rename / write toggles +
  the same `render_diff` table the CLI uses.
- `tools/strip/setup_check.py` — contributes to `babel --setup`.
  Reports per-format support and warns when `pypdf` is missing.
- `tools/strip/pipeline.py` — extension dispatch, single-file and
  batch loops, originals-untouched guarantee, hash-rename helper.
- `docs/tools/STRIP.md` — full per-tool spec with explicit "What
  this protects" and "What this does NOT protect" tables built
  from a LINDDUN worksheet (Forge THREAT MODEL pass).
- `pentest/strip/` — 49-test harness covering every row in the
  "What this protects" table for JPG/PNG/PDF/DOCX/MP3, plus
  batch / hash-rename / originals-untouched / dry-run / aggressive
  mode regressions. Fixtures are hand-built byte-level so the tests
  don't depend on Pillow / mutagen / python-docx round-trips.

### Shared infrastructure for Phase 2 (and Phase 3+)

- `shared/ui/` is born. Contains the modules MASTER.md 5.5 promised:
    - `shared/ui/diff_view.py` — `FieldRemoved` dataclass, the
      pure-string `render_diff()` renderer, and the `DiffTable`
      Textual widget that wraps it. Both STRIP and (future) CARRIER
      consume this for before/after tables.
    - `shared/ui/progress.py` — `ProgressState` + `render_bar()`
      pure renderer + `RealProgressBar` widget. Driver-fed only
      (MASTER.md 3.2): no internal timer, the bar advances only on
      real progress callbacks.
    - `shared/ui/compact.py` — width-based label adapters used
      throughout; centralises the compact-mode rule.

### Suite wiring

- `babel/menu.py` — entry `[3] STRIP` is now live (`live=True`).
  Pressing `3` calls `app.enter_tool('strip')`.
- `babel/__main__.py`:
    - `_run_strip` and a `head == "strip"` dispatch branch.
    - The menu's STRIP return-value is routed to `_run_strip([])`
      so `babel` → `[3]` lands in the STRIP CLI's interactive mode.
    - `babel --setup` is now a real aggregator (`_run_setup`) that
      collects each tool's `setup_check.run()` and concatenates;
      VOID + STRIP contribute. The aggregator tolerates both the
      MASTER.md 6.3 contract `(int, list[str])` and VOID's older
      "writes stdout, returns int" shape.
- `babel/theme.py` — `_env_says_ascii()` additionally probes
  `sys.stdout.encoding`. cp1252 / cp850 / ascii consoles auto-fall
  back to Tier-1, so `babel strip --setup` no longer raises
  `UnicodeEncodeError` on a default Windows console.

### Dependencies

- `pypdf>=4.0` added to `requirements.txt` and `pyproject.toml`.
  Pure-Python, MIT, no transitive deps. Powers STRIP's PDF surface.

### Entry points

- New legacy-style alias `strip = "babel.__main__:main"` alongside
  the existing `babel` and `void`. All three dispatch via argv.

## v0.6.0 — internal milestone (Phase 0 refactor, never released)

Internal version tag used between v0.5.0 and v1.0.0 for the
structural refactor that lifted VOID into the suite layout.  No
public artefacts under this tag; the work landed as part of
v1.0.0.  Detail preserved below for bisectability.

Structural refactor: VOID becomes the first room of the **Tower of
Babel** suite. No behavioural changes to VOID itself; the wire
format, the CLI surface, the cryptographic primitives, the server
guards, and the threat model are all unchanged. The full suite
design lives in `MASTER.md` at the repo root.

### New layout

- `tools/void/{client,server}/` — VOID source moved here verbatim;
  every relative import inside VOID still resolves the same way.
- `pentest/void/` — every VOID pentest script moved here; their
  `sys.path` bootstrap and `from client.* import` lines were
  rewritten to match.
- `babel/` — the suite launcher and shell:
    - `babel/__main__.py` is the new entry point (`babel`,
      `babel void <args>`, `babel --make-invite`, `babel --setup`)
    - `babel/menu.py` is the five-row stub menu; only [1] VOID is
      live in this phase, [2]-[5] render as `(not yet built)`
    - `babel/shell.py` is the Phase-0 stub for the multiplex
      chrome described in MASTER.md Sections 4.2 / 4.4; Phase 1
      fleshes it out
    - `babel/theme.py` is the suite palette (GREEN, GREEN_DEEP,
      CYAN, AMBER, RED, MUTE, BG) -- single source of truth for
      the seven master-palette colours
    - `babel/art.py` (moved from `client/art.py`) owns the
      logos and rotating hints suite-wide
- `shared/` — cross-tool reusable code:
    - `shared/crypto/secure_mem.py` — the mlock'd `SecureBytes`
      buffer + swap detection (moved from `client/secure_mem.py`;
      the original is now a 5-line import shim)
    - `shared/tor/control.py` — direct Tor control-port client
      (extracted from `client/host.py`)
    - `shared/tor/socks_detect.py` — Tor SOCKS5 detection
      (extracted from `client/setup_check.py`)

### Entry points and installers

- New top-level command: `babel`. The historical `void` and
  `void-server` commands stay as aliases (defined in
  `pyproject.toml [project.scripts]`).
- `install.sh` and `install.ps1` updated to lead with `babel` in
  the post-install banner; the heavy lifting (Tor config, libxeddsa
  build on Termux, sudo gating, PATH patching) is unchanged.
- `pyproject.toml` renamed to `tower-of-babel`; package discovery
  switched to `["babel*", "shared*", "tools*"]`.

### Build pipeline

- `packaging/void.spec` renamed to `packaging/babel.spec` with the
  new entry point (`babel/__main__.py`) and explicit hidden-imports
  for the babel/, shared/, and tools/ packages so PyInstaller does
  not drop them. The output binary is `babel-<ver>-<plat>-<arch>`.
- `packaging/void-server.spec` retargeted at
  `tools/void/server/__main__.py`; produces the same `void-server`
  binary as before, byte-for-byte (same hash, see step-14 gate in
  the Phase 0 prompt).
- `.github/workflows/release.yml` updated to build both binaries
  on every `v*` tag and include both in `SHA256SUMS`.
- Pipeline fixes (preflight commits):
    - `packaging/build.sh` now tolerates a Docker bind-mount on
      `/src/dist` (was crashing with `rmdir: EBUSY` on
      Windows/WSL2 checkouts).
    - `packaging/Dockerfile.build` no longer flattens
      `packaging/*.spec` into `/src/`; the spec files'
      `dirname(SPEC)/..` project-root resolution now works in the
      container (this build path had never worked end-to-end).

### Documentation

- `MASTER.md` lands at the repo root as the suite's single source
  of truth.
- `docs/HACKING.md` introduced for contributor notes -- adopted
  skills log per MASTER.md Section 11.2, plus the
  Windows-on-WSL2 build-pipeline gotchas this refactor uncovered.
- `README.md` reframed as "Tower of Babel / VOID" with the
  canonical italic tagline and an introduction to the suite; the
  VOID-specific content below is unchanged.

### Verified

- Two consecutive `make build-docker` runs on the pre-refactor
  source produce byte-identical `SHA256SUMS` (regression gate is
  live in this environment).
- Every step from 1 through 13 of the Phase 0 prompt is a separate
  commit on `main` so the history is bisectable.
- Step 14 (post-refactor build) and step 15 (pentest re-run) are
  the remaining gates before tagging `phase-0-complete`.

## v0.5.0 — 2026-05-15

First public release.

### Cryptography

- End-to-end via X3DH initial AKE + Signal-style Double Ratchet
  (per-message keys, forward secrecy, post-compromise security).
- AES-256-GCM with HKDF-derived IV per message.
- Ed25519 signatures over (ratchet_pub || ciphertext); verified
  against the IK from the X3DH handshake.
- ISO/IEC 7816-4 padding to 1024-byte multiples (max 8 KB plaintext).
- 5-word PGP-list SAS over `SHA-256(min(IK_a, IK_b) || max(IK_a, IK_b))`.

### Transport

- Tor v3 ephemeral onions created on the fly via the Tor control
  protocol (no `torrc` editing for the host).
- WebSocket frames tunnelled through SOCKS5; client auto-detects
  port 9050 / 9150 / 9151.
- Server bound to `127.0.0.1`; reachable only through the onion.

### Anonymity hardening

- 50–350 ms forwarding jitter on the server.
- 15–45 s cover-traffic dummies on each client.
- IK seed stored in `mlock`'d / `VirtualLock`'d memory with zero-on-free.
- `/burn N` disappearing-message mode (10–86400 s).

### Server protocol guards

- 32 KB frame cap, 20 frames/s/conn rate limit.
- 512 global connection cap (close 1013).
- 16-peer room cap (close 1013 on join).
- Strict shape validation on bundles, `dr` envelopes, signatures, x3dh headers.
- Cross-room delivery refused.

### Installers

- `install.sh` for Linux / macOS / Termux (detects apt / dnf / pacman / brew / pkg).
- `install.ps1` for Windows (winget Python + Tor Browser).
- Termux installer auto-installs Rust (for `pydantic-core`) and builds
  `libxeddsa` from source.

### Build pipeline

- Reproducible PyInstaller builds with pinned `SOURCE_DATE_EPOCH`,
  `PYTHONHASHSEED`, sorted analysis inputs.
- `packaging/Dockerfile.build` (python:3.11.10-slim-bookworm) for
  byte-identical cross-host reproduction.
- GitHub Actions release workflow builds Linux x86_64, macOS arm64,
  and Windows x86_64 on every `v*` tag, publishes `SHA256SUMS`.

### Documentation

- README + `docs/{INSTALL,USAGE,ARCHITECTURE,SECURITY,FAQ}.md`.

### Known limitations

Phase 5+ work, not in this release:

- Wire-rate asymmetry between talker and silent peers (~1.3x).
- Padding leaks coarse plaintext size in 1024-byte chunks.
- SAS is 40 bits; grinding cost ~10¹² per session.
- No post-quantum hybrid KEM.
- Single-hop Tor; no mixnet routing.
- Onion address not pinned out-of-band (TOFU on the invite channel).

License: [0BSD](LICENSE).
