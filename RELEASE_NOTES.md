# Tower of Babel v1.0.0 -- first suite release

*confusion of tongues, by design*

VOID v0.5.0 was a single tool: an ephemeral encrypted messenger
over Tor.  Tower of Babel v1.0.0 is what VOID grew into: a
federation of five single-purpose terminal tools under a shared
chrome, build system, and moral posture.

```
                ██████╗   █████╗  ██████╗  ███████╗ ██╗
                ██╔══██╗ ██╔══██╗ ██╔══██╗ ██╔════╝ ██║
                ██████╔╝ ███████║ ██████╔╝ █████╗   ██║
                ██╔══██╗ ██╔══██║ ██╔══██╗ ██╔══╝   ██║
                ██████╔╝ ██║  ██║ ██████╔╝ ███████╗ ███████╗
                ╚═════╝  ╚═╝  ╚═╝ ╚═════╝  ╚══════╝ ╚══════╝
```

## What's in the tower

| Tool      | Flavour | Role                                                                                |
|-----------|---------|-------------------------------------------------------------------------------------|
| `VOID`    | service | ephemeral encrypted messenger over Tor (X3DH + Double Ratchet)                      |
| `MASK`    | action  | disposable identity generator (alias + geometric avatar + bio + temp mail)          |
| `STRIP`   | action  | metadata laundry (EXIF, XMP, IPTC, PDF, Office, MP3 tags, MP4 atoms)                |
| `CARRIER` | action  | steganography -- AES-256-GCM payload hidden in PNG / WAV via LSB                    |
| `MIRAGE`  | service | cover traffic generator (real httpx requests over Tor SOCKS5, with hard caps)       |

Service-flavoured tools (VOID, MIRAGE) stay alive in slots while
the user switches to anything else.  Action tools (MASK, STRIP,
CARRIER) run one operation and return to the menu.  Up to four
services concurrent by default, switchable via `Alt+1..N`.

## Moral posture

```
"I hand you the hammer.  How you use it is your business."
```

The tools have specific functions.  They ship with honest threat
models that say what they protect and what they don't.  They do
not moralize, do not gate features behind "intended use"
disclaimers, and do not log who used them for what.  0BSD licence
throughout.

## Honest threat boundaries

Every tool's `docs/tools/<NAME>.md` carries two equal-weight
tables: **What it protects** and **What it does NOT protect**.  A
non-exhaustive sample of the things this release does **not** try
to address:

- Endpoint compromise (every tool).
- Reverse image search defeating publicly-sourced avatars (MASK does
  not use them; LINDDUN Identifiability row).
- Lossy re-encoding destroying LSB payloads (CARRIER).
- Bot-like traffic patterns under sophisticated analysis (MIRAGE).
- Office "track changes" residue in obscure XML (STRIP normalises
  but does not guarantee 100%).
- Quantum HNDL on anything captured today.
- Single-hop Tor's de-anonymisation under a Global Passive
  Adversary (suite-wide).

If you need protection against any of those, this is the wrong
tool for that job; read the per-tool docs before relying on
anything for what it was not built to do.

## Build artefacts

The release workflow builds one unified binary per platform.  Each
artefact carries its own SHA-256 in `SHA256SUMS`.

```
babel-1.0.0-linux-x86_64
babel-1.0.0-linux-arm64
babel-1.0.0-macos-x86_64
babel-1.0.0-macos-arm64
babel-1.0.0-windows-x86_64.exe
```

Plus a server-only deployment for hardened hosts:

```
void-server-1.0.0-linux-x86_64
void-server-1.0.0-linux-arm64
void-server-1.0.0-macos-x86_64
void-server-1.0.0-macos-arm64
void-server-1.0.0-windows-x86_64.exe
```

The `babel` binary contains every tool; `void-server` is the
narrow-attack-surface server alone.

## Verification

```
sha256sum -c SHA256SUMS
```

To reproduce the build from source:

```
git clone --depth 1 --branch v1.0.0 https://github.com/deox420/tower_of_babel.git
cd tower_of_babel
docker build -f packaging/Dockerfile.build -t babel-build:1.0.0 .
docker run --rm -v "$PWD/dist:/src/dist" babel-build:1.0.0
diff <(sort SHA256SUMS) <(sort dist/SHA256SUMS)
```

The output must be empty.

## Install

**Linux / macOS:**

```bash
curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/v1.0.0/install.sh | sh
```

**Termux (Android, F-Droid only):**

```bash
curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/v1.0.0/install.sh | sh
```

**Windows (PowerShell):**

```powershell
iwr -useb https://raw.githubusercontent.com/deox420/tower_of_babel/v1.0.0/install.ps1 | iex
```

Post-install:

```bash
babel                   # menu
babel void              # straight into VOID
babel strip ./img.png   # strip a file from the CLI
babel --setup           # full diagnostic
```

## Upgrading from v0.5.0

VOID's wire format, ratchet, and server hardening are unchanged.
A v0.5.0 client talking to a v1.0.0 server (or vice versa) is
fully compatible.  The only change visible to an existing user is
the entry-point binary: `void` and `void-server` are still
recognised but now forward to `babel`.

## Known deviations from MASTER.md

See the `v1.0.0` stanza in `CHANGELOG.md` for the structural items
that do not yet match MASTER.md's prescribed layout (four missing
`babel/*.py` files, four deferred `shared/*` modules, several
not-yet-imported shared/ui modules, two TUI keybindings that point
at the CLI rather than at unbuilt features).  None of these affect
correctness or security; they shape the post-1.0 cleanup backlog.

## Licence

0BSD.  Verbatim.  Do whatever.  No warranty.
