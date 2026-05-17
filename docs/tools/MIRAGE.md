*confusion of tongues, by design*

```
███╗   ███╗██╗██████╗  █████╗  ██████╗ ███████╗
████╗ ████║██║██╔══██╗██╔══██╗██╔════╝ ██╔════╝
██╔████╔██║██║██████╔╝███████║██║  ███╗█████╗
██║╚██╔╝██║██║██╔══██╗██╔══██║██║   ██║██╔══╝
██║ ╚═╝ ██║██║██║  ██║██║  ██║╚██████╔╝███████╗
╚═╝     ╚═╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

# MIRAGE - cover traffic generator

## 1 - What this is

MIRAGE generates plausible background network activity from a small
set of behavioural profiles ("office worker", "developer", "casual
browser", "researcher"). It makes real HTTP requests, performs real
DNS lookups through the SOCKS5 proxy, and dwells for realistic
amounts of time between fetches. The point is **decoy**: when an
observer can see your network, your real traffic is buried inside a
larger background stream that looks ordinary.

MIRAGE is a *service* tool (MASTER.md Section 4.4): it occupies a
slot in the babel shell and keeps running while you use VOID, STRIP,
CARRIER, or MASK in the foreground. It is the only tool in the
tower that does work *while you are not looking at it*. That is the
whole point and also the whole risk -- see Section 3.

It does not buy you anonymity on its own. Tor does that. MIRAGE
makes the *shape* of your traffic less informative once Tor has
already broken the link to your identity. Run them together; do not
treat MIRAGE as a substitute.

## 2 - What it protects

| Surface | Protection |
|---|---|
| Idle-vs-active link timing | A constant trickle of profile-shaped requests (default: 6-30 req/min, profile-dependent) means an observer cannot tell from raw byte counts whether you are typing in VOID, embedding a payload in CARRIER, or away from the keyboard. |
| Per-host correlation at the Tor entry guard | Each request flows through Tor SOCKS5 by default. The site mix is drawn from a public Zipf-weighted catalog; no single host dominates unless the profile specifies one. |
| Per-request DNS leakage | The SOCKS5 proxy URL uses `socks5h://` (the `h` variant), so the DNS query travels inside Tor. The local resolver never sees the target hostname. |
| New-circuit rotation | Optional: every `--rotate-min` minutes (default 10), MIRAGE asks Tor's control port for a `NEWNYM` signal, forcing a fresh circuit. Real foreground tools (VOID's chat session, an in-flight CARRIER capacity probe) keep their existing circuits; only MIRAGE's next request lands on the new one. |
| Bandwidth ceiling | Token-bucket cap on outgoing+incoming bytes/second. Default 100 KB/s (~800 kbps), configurable via `--bw-kbps`. The bucket is checked before each request; if a fetch would exceed the budget, MIRAGE sleeps until the budget refills. The cap is enforced even when the profile prefers a higher rate. |
| Request-rate ceiling | A second token bucket on `requests / 60s`. Default 30, configurable via `--rate-rpm`. Together with the bandwidth cap this gives a hard two-axis envelope; a buggy or hostile site list cannot drive MIRAGE past either ceiling. |
| CPU ceiling (advisory) | The engine measures its own CPU consumption every second; if a one-minute moving average exceeds `--cpu-pct` (default 2.0%), MIRAGE inserts cooldown sleeps until the average drops. This is best-effort -- the OS scheduler still owns final say. |
| Profile-bounded request shapes | Profiles are static, public, and version-pinned. They define which sites are reachable, what Accept-Language to send, and what dwell-time distribution to draw from. No profile field is read from the user's environment beyond the locale string they pass on the CLI. |
| Honest mode | `--honest` (CLI) or `[o]` (TUI) shows each request as it fires: timestamp, host, bytes, ms. The user can see in real time what MIRAGE is doing and decide to stop it. Honest mode never writes to disk -- output is stderr (CLI) or a ring-buffer Static (TUI). |
| Clearnet requires explicit opt-in | `--clearnet` bypasses Tor and requires `--i-know` on the CLI; the TUI pops a red confirmation panel. Without it, MIRAGE refuses to start with exit code 5. |
| Tor reachability gate on start | If Tor SOCKS5 is unreachable and `--clearnet` was not passed, MIRAGE exits before issuing any request. The user cannot accidentally leak through their OS resolver. |
| Service slot purge | When the chrome calls `purge_local()` (Ctrl+W on the slot, or Ctrl+C / Ctrl+Q on the suite), the engine cancels its in-flight task within 1 second, closes the `httpx.AsyncClient`, drops the token-bucket state, and clears the per-session counters. No buffers persist beyond the slot's lifetime. |
| No on-disk state | MIRAGE writes nothing to `~/.config/babel/mirage/` and creates no temp files. The ring-buffer event log is in RAM and is bounded (default 256 entries). |
| Profile is a public lookup, not a fingerprint | Two users running the same profile produce statistically similar traffic, by design. The profile string itself (`office_worker`) is not transmitted; it only governs the local request selection. |

## 3 - What this does NOT protect

| Risk | Why it survives |
|---|---|
| The fact that you run MIRAGE | Process listings, `~/.bash_history` containing `babel mirage`, antivirus telemetry, and the binary's presence on disk are all visible. MIRAGE cannot launder its own footprint. |
| Bot-like patterns under sophisticated analysis | A Zipf-weighted draw with profile dwell times is **not** indistinguishable from a real human. Mouse-free, scroll-free, idle-period-free traffic is detectable to a determined analyst with access to per-request HTTP-level telemetry. MIRAGE buries traffic in coarse-grain volume; it does not impersonate a person. |
| Absolute-volume change at the ISP | If your normal baseline is 10 KB/min and MIRAGE drives it to 100 KB/s, the *delta itself* is informative to DPI / NetFlow analysis even though the contents are opaque. Tune `--bw-kbps` to match your normal envelope. |
| Real foreground traffic still happens | MIRAGE adds noise; it does not delete your VOID frames or your CARRIER capacity probe. The cover hides *which* of the bytes are yours, not whether you transmitted them. A correlated-pair attacker watching both ends still sees your real traffic. |
| Site-catalog correlation | The default catalog is a public list of common destinations. If an adversary has the catalog (it ships with the suite, it is not secret), they can match your fetches against the public Zipf weights and exclude requests that look profile-shaped. Profiles are decoy, not steganography. |
| TLS fingerprint / JA3 / HTTP/2 settings | MIRAGE uses `httpx` defaults, which produce a recognisable Python/HTTPX JA3. Sophisticated DPI can flag the requests as coming from an automated Python client rather than from a browser. Wrapping in Tor obscures the *destination* but not the *issuer*. |
| Endpoint compromise | If something on your machine reads the engine's in-RAM state through `/proc/<pid>/mem`, kernel debugging, or a core dump, MIRAGE cannot help. The token-bucket counters and the ring buffer live in plain Python objects. |
| Tor circuit-builder correlations | Asking for `NEWNYM` every 10 minutes is *itself* a pattern. A Tor-aware adversary watching your guard can infer roughly when you rotated. The rotation feature is opt-in (`--rotate-min`); leave it off if your threat model is more concerned about meta-patterns than per-circuit linkage. |
| Hostile sites | MIRAGE fetches what the profile says to fetch. If a site in the catalog has been compromised since the catalog was pinned, MIRAGE will still GET its TLS endpoint. The risk is contained (no JS execution, no redirects auto-followed past depth 1, no cookies stored across requests) but not zero. |
| Battery / data-plan cost on mobile | A laptop on AC power barely notices 100 KB/s. A phone on cellular notices a lot. The Termux variant defaults to a 5x smaller envelope (`--bw-kbps 20 --rate-rpm 6 --cpu-pct 0.5`) but the user owns the final decision. |
| Existence of MIRAGE strings in HTTP requests | None of MIRAGE's outgoing headers say "MIRAGE". User-Agent is borrowed from a profile-bound rotation pool of common browser strings, so MIRAGE itself does not advertise. But anyone with the suite source can look up the pool and detect a perfect match. The catalog is a public tell. |
| Quantum HNDL on Tor | Inherited from Tor's threat model: a future quantum capability that breaks the long-lived guard handshake can retroactively decrypt the recordings. MIRAGE does not add a hybrid KEM. |
| Side-channel timing inside Tor | A global passive adversary that sees both ends of every Tor circuit can correlate inputs and outputs with high confidence regardless of MIRAGE's decoys. Tor is not a mixnet. |
| Profile = locale fingerprint | A user who runs `--profile researcher --locale en` produces english academic patterns. The combination is informative. If you do not match the profile's assumptions (e.g. you run `researcher` in a region where that pattern is rare), you become *more* fingerprintable, not less. |

## 4 - CLI flags

```
babel mirage                              # interactive TUI screen
babel mirage start                        # run in the foreground until Ctrl+C
babel mirage start --profile office_worker|developer|casual_browser|researcher
babel mirage start --duration <sec>       # exit cleanly after N seconds
babel mirage start --bw-kbps <int>        # bandwidth ceiling (default 100, max 4096)
babel mirage start --rate-rpm <int>       # request-rate ceiling (default 30, max 240)
babel mirage start --cpu-pct <float>      # CPU ceiling (default 2.0, max 25.0)
babel mirage start --rotate-min <int>     # NEWNYM every N minutes (0=disable, default 0)
babel mirage start --locale en|es|fr|de|neutral
babel mirage start --honest               # print each request as it fires
babel mirage start --json                 # emit one JSON line per request to stderr
babel mirage start --clearnet --i-know    # bypass Tor (red banner + opt-in)
babel mirage start --dry-run              # plan and print N requests; do not send any
babel mirage status                       # show current envelope, counters, last request
babel mirage profiles                     # list profiles and their declared envelopes
babel mirage --setup                      # diagnostic: httpx + Tor + control port
```

The CLI's `start` subcommand runs MIRAGE as a foreground process.
Inside the babel shell, the `[5] MIRAGE` menu entry registers a
`MirageService` in the chrome's service registry instead, so VOID
or MASK can sit in the foreground while MIRAGE runs in slot 2.

Hard caps:

| Cap | Default | Max | Floor |
|---|---|---|---|
| `--bw-kbps` | 100 | 4096 | 1 |
| `--rate-rpm` | 30 | 240 | 1 |
| `--cpu-pct` | 2.0 | 25.0 | 0.1 |
| `--rotate-min` | 0 (off) | 1440 | 1 (when set) |
| `--duration` | infinite | 86400 | 1 |

The maximums are enforced at parse time; `start --bw-kbps 100000`
exits with code 2 and a message naming the ceiling. The floor
exists to make the engine make forward progress; setting
`--rate-rpm 0` would mean "never fetch", which is just "do not run
MIRAGE".

Exit codes:

| Code | Meaning |
|---|---|
| 0 | shutdown clean (Ctrl+C, --duration elapsed, slot closed) |
| 1 | shutdown clean but one or more requests warned (timeouts, 5xx) |
| 2 | invocation error (bad flags, value above the ceiling) |
| 3 | I/O error (control-port unreachable when --rotate-min set) |
| 4 | profile catalog malformed (only reachable if the bundle was tampered with) |
| 5 | Tor required but no SOCKS5 port answered (and --clearnet was not passed) |

## 5 - In-app commands and keys

| Key | Effect |
|---|---|
| `s` | start the engine with the current profile / envelope |
| `p` | pause (engine sleeps, slot stays alive) |
| `r` | resume from pause |
| `o` | toggle honest mode (per-request lines appear in the lower panel) |
| `l` | cycle locale (`en` -> `es` -> `fr` -> `de` -> `neutral`) |
| `f` | cycle profile (`office_worker` -> `developer` -> `casual_browser` -> `researcher`) |
| `t` | toggle Tor / clearnet (clearnet pops the red confirmation panel) |
| `+` / `-` | nudge `bw-kbps` up / down by 10 (clamped to the cap range) |
| `]` / `[` | nudge `rate-rpm` up / down by 5 (clamped) |
| `n` | request a `NEWNYM` now (one-shot; does not change `--rotate-min`) |
| `c` | clear the in-RAM event ring buffer |
| `Esc` / `q` | leave the slot (engine purges, returns to menu) |
| `Ctrl+W` | close the MIRAGE slot from anywhere in the suite (calls purge) |
| `Ctrl+C` / `Ctrl+Q` | quit the suite (purges every service) |

## 6 - Worked walkthrough

CLI, honest mode, default profile:

```
$ babel mirage start --honest
mirage: profile=office_worker  bw<=100 KB/s  rate<=30 rpm  cpu<=2.0%  via tor:9050
[14:32:17 UTC] GET https://en.wikipedia.org/wiki/Main_Page    18.4 KB   242 ms
[14:32:51 UTC] GET https://duckduckgo.com/                     4.2 KB    98 ms
[14:33:12 UTC] GET https://news.ycombinator.com/                7.1 KB   181 ms
[14:33:48 UTC] GET https://en.wikipedia.org/wiki/Pelican        9.8 KB   201 ms
...
^C
mirage: shutdown clean  (28 requests, 41 KB/min avg, 0 timeouts)
```

In-chrome, alongside VOID:

```
TOWER OF BABEL  [1:VOID 2 peers]  [2:MIRAGE 18 rpm 41 KB/min]  v1.0.0
+---------------------------------------------------------------+
| MIRAGE -- cover traffic generator                              |
| profile=office_worker  net=tor  bw<=100 KB/s  rate<=30 rpm     |
|                                                                |
|   running   28 requests  41 KB/min avg  cpu 1.4%  uptime 17:42 |
|   last      GET https://en.wikipedia.org/wiki/Pelican  9.8 KB  |
|                                                                |
|   [14:33:48] GET en.wikipedia.org           9.8 KB  201 ms     |
|   [14:33:12] GET news.ycombinator.com       7.1 KB  181 ms     |
|   [14:32:51] GET duckduckgo.com             4.2 KB   98 ms     |
|                                                                |
|   [s] start  [p] pause  [r] resume  [o] honest  [f] profile    |
|   [+/-] bw  [ ] [ rate  [n] new circuit  [c] clear  [Esc] back |
+---------------------------------------------------------------+
| * TOR :9050 -- * MEM mlock -- . CRYPTO idle -- * SWAP off --  14:33:48 UTC |
+---------------------------------------------------------------+
```

Profile listing:

```
$ babel mirage profiles
office_worker     news, search, mail web-UIs, weather, maps   en  6-12 rpm typical
developer         docs, package indexes, repo READMEs         en  8-20 rpm typical
casual_browser    news, video front pages, social public      mix 4-10 rpm typical
researcher        wikipedia, journal abstracts, archives      en  3-8  rpm typical
```

## 7 - Architecture

```
tools/mirage/
  __init__.py
  __main__.py
  cli.py            # argparse front-end: start / status / profiles / --setup
  app.py            # Textual screen + standalone MirageApp
  service.py        # MirageService (implements babel.shell.Service)
  engine.py         # async request loop + token-bucket gate + httpx client
  caps.py           # TokenBucket + CpuMeter (pure logic, no I/O)
  schedule.py       # SessionPlan: dwell distributions, jitter, session windows
  profile.py        # ProfileSpec dataclass; PROFILES registry
  sites.py          # static, version-pinned per-profile catalogs (Zipf weights)
  setup_check.py    # contributes to `babel --setup`
```

**Reused** (per MASTER.md Section 7.5):

- `shared.tor.socks_detect` -- SOCKS5 port probe (`9050 / 9150 / 9151`)
- `shared.tor.control`      -- TorControl (`SIGNAL NEWNYM`) for circuit rotation
- `shared.ui.progress`      -- `RealProgressBar` for the session-duration bar
- `babel.shell.Service`     -- Protocol the chrome's registry queries
- `babel.theme`             -- palette + glyph table for the screen
- `babel.art`               -- BABEL_TAGLINE for the screen header

**No** new shared modules. MIRAGE's machinery (token bucket, Zipf
draw, session scheduler) is profile-specific and would not generalise
without forcing the wrong abstractions on the other tools.

**HTTP transport**: a single `httpx.AsyncClient` per engine, with
`proxy="socks5h://127.0.0.1:<port>"` when Tor mode is on. The `h`
variant resolves DNS through the proxy so the local resolver never
sees the target hostname. The client is recreated on every locale
change and on every `NEWNYM` so per-host TLS sessions do not survive
a circuit rotation.

**Profile DSL**:

```python
@dataclass(frozen=True)
class ProfileSpec:
    name: str
    description: str
    rpm_typical: tuple[int, int]      # (low, high), clamped to --rate-rpm cap
    dwell_seconds: tuple[float, float]   # uniform draw for sleep between fetches
    sites_key: str                    # lookup into sites.PROFILE_SITES
    accept_language: dict[str, str]   # locale -> Accept-Language header value
    user_agents: tuple[str, ...]      # pool rotated per-request
```

**Site catalog** (`tools/mirage/sites.py`): per-profile tuples of
`(host, path_template, zipf_rank)` where `zipf_rank` is the integer
rank used in the draw. The draw is `weight_i = 1 / rank_i`,
normalised. Lower rank = more frequent. Catalogs are intentionally
small (typically 30-60 entries) so they fit in the binary without
inflating it.

**Token bucket** (`tools/mirage/caps.py`):

```python
class TokenBucket:
    """Pure-logic rate limiter; the engine wires it to a real clock."""
    def __init__(self, capacity: float, refill_per_sec: float) -> None: ...
    def try_consume(self, amount: float, now: float) -> bool: ...
    def time_until(self, amount: float, now: float) -> float: ...
```

Two buckets, both refilled by wallclock seconds: one in bytes
(capacity = `bw_kbps * 1024`, refill = same per second), one in
requests (capacity = `rate_rpm`, refill = `rate_rpm / 60`). Before
a request, the engine consults both; the deeper deficit decides the
sleep.

**Honest mode emission**: per-request line is built from the
post-fetch state and pushed onto a bounded `collections.deque`
(`maxlen=256`). The CLI prints each line to stderr immediately; the
TUI calls `Static.update()` on the panel widget.

## 8 - Reproducible build notes

- No new runtime dependencies. `httpx[socks]` is already pinned for
  Phase 4 (MASK); MIRAGE shares the same pin. `socksio` stays in
  `hiddenimports` of `packaging/babel.spec`.
- `tools/mirage/sites.py` is a plain Python module (no `data/`
  directory) so PyInstaller picks it up automatically; no
  `package_data` entry is required.
- The User-Agent pool is a tuple of literal strings in the source;
  it does not get rebuilt at runtime and contributes nothing to the
  output binary that differs across builds.
- MIRAGE does not call `random.seed()` or `time.time()` at module
  import. All non-determinism is engine-scoped, so importing the
  module does not perturb the build environment.
- The Tor control-port path (`SIGNAL NEWNYM`) is reused verbatim
  from `shared.tor.control`; no per-tool override.
