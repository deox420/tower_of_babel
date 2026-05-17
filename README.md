<div align="center">

# Tower of Babel

*confusion of tongues, by design*

```
████████╗ ██████╗ ██╗    ██╗███████╗██████╗
╚══██╔══╝██╔═══██╗██║    ██║██╔════╝██╔══██╗
   ██║   ██║   ██║██║ █╗ ██║█████╗  ██████╔╝
   ██║   ██║   ██║██║███╗██║██╔══╝  ██╔══██╗
   ██║   ╚██████╔╝╚███╔███╔╝███████╗██║  ██║
   ╚═╝    ╚═════╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═╝

  ██████╗  █████╗ ██████╗ ███████╗██╗
  ██╔══██╗██╔══██╗██╔══██╗██╔════╝██║
  ██████╔╝███████║██████╔╝█████╗  ██║
  ██╔══██╗██╔══██║██╔══██╗██╔══╝  ██║
  ██████╔╝██║  ██║██████╔╝███████╗███████╗
  ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝
```

**A privacy and anti-surveillance suite for the terminal.**
Five single-purpose tools under one shell.
Tor by default. Nothing persistent. No telemetry. 0BSD.

[![license](https://img.shields.io/badge/license-0BSD-2d6a4f?style=flat-square)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11+-2d6a4f?style=flat-square)](https://www.python.org)
[![platforms](https://img.shields.io/badge/platforms-linux%20%7C%20macos%20%7C%20windows%20%7C%20android-2d6a4f?style=flat-square)](docs/INSTALL.md)
[![transport](https://img.shields.io/badge/transport-Tor-6cdcff?style=flat-square)](https://www.torproject.org)
[![crypto](https://img.shields.io/badge/crypto-X3DH%20%2B%20Double%20Ratchet-6cdcff?style=flat-square)](docs/ARCHITECTURE.md)
[![build](https://img.shields.io/badge/build-reproducible-6cdcff?style=flat-square)](packaging/Dockerfile.build)
[![release](https://img.shields.io/github/v/release/deox420/tower_of_babel?style=flat-square&color=ffd166)](https://github.com/deox420/tower_of_babel/releases/latest)

</div>

---

The Tower of Babel is where humanity's languages were confused so no
single power could read everything. That image is the project's
thesis in one picture. The suite is a federation of single-purpose
tools that share a shell, an aesthetic, a build system, and a moral
posture.

> "I hand you the hammer. How you use it is your business."

The tools have specific functions. They ship with honest threat
models that say what they protect and what they don't. They do not
moralize, do not gate features behind "intended use" disclaimers,
and do not log who used them for what. The 0BSD licence makes this
explicit.

## The five rooms

| Tool        | Flavour | Role                                                                                  | Docs |
|-------------|---------|---------------------------------------------------------------------------------------|------|
| **VOID**    | service | ephemeral encrypted messenger over Tor (X3DH + Double Ratchet, blind relay)           | [VOID.md](docs/tools/VOID.md) |
| **MASK**    | action  | disposable identity (alias + locally-generated geometric avatar + bio + temp mail)    | [MASK.md](docs/tools/MASK.md) |
| **STRIP**   | action  | metadata laundry (EXIF / XMP / IPTC / PDF properties / Office authorship / audio tags)| [STRIP.md](docs/tools/STRIP.md) |
| **CARRIER** | action  | steganography (AES-256-GCM payload hidden in PNG / WAV via LSB)                       | [CARRIER.md](docs/tools/CARRIER.md) |
| **MIRAGE**  | service | cover traffic generator (real httpx over Tor SOCKS5h, hard rate + bandwidth caps)     | [MIRAGE.md](docs/tools/MIRAGE.md) |

Service tools (VOID, MIRAGE) live in slots and keep running while
you switch between other tools. Action tools (MASK, STRIP, CARRIER)
run one operation and return to the menu. Up to four services at
once, switchable via `Alt+1..N`.

## Install

One command per platform. The code blocks below have a copy button
in the top-right corner when viewed on GitHub.

**Linux / macOS:**

```bash
curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh | sh
```

**Windows (PowerShell):**

```powershell
iwr -useb https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.ps1 | iex
```

**Android (Termux)** -- install [Termux from F-Droid](https://f-droid.org/packages/com.termux/)
first, then run the same Linux command (the installer auto-detects
Termux and pulls the right packages):

```bash
curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh | sh
```

> **Android:** install Termux **from F-Droid only**. The Play Store
> version is unmaintained and breaks `pkg`.

Prebuilt binaries for Linux + macOS + Windows are attached to the
[latest release](https://github.com/deox420/tower_of_babel/releases/latest)
with `SHA256SUMS`.

## Use

`babel` opens the suite menu. Each tool also has a top-level shortcut
that forwards into the same code path.

```bash
babel                          # main menu
babel --setup                  # aggregated diagnostic for every tool
babel void                     # straight into VOID
babel void --make-invite       # host an ephemeral chat
babel mask new                 # one-keystroke disposable identity
babel strip ~/photo.jpg        # remove metadata, write photo.stripped.jpg
babel carrier embed cover.png secret.txt
babel mirage start --profile office_worker
```

The legacy `void`, `mask`, `strip`, `carrier`, and `mirage` commands
are kept as aliases and dispatch through `babel.__main__`.

## What this does NOT protect

Per [MASTER.md](MASTER.md) section 1, every tool ships a `What this
does NOT protect` table in its `docs/tools/<NAME>.md` alongside the
protections it does provide. A non-exhaustive sample of what the
suite makes no claim about:

- **Endpoint compromise.** If your machine is owned, the tools can
  not help. Use a clean device or an air-gapped one.
- **Reverse image search** defeating publicly-sourced avatars
  (MASK does not use them).
- **Lossy re-encoding** destroying LSB payloads (CARRIER).
- **Bot-like traffic patterns** under sophisticated analysis (MIRAGE).
- **Quantum HNDL** on data captured today.
- **Global Passive Adversary** on single-hop Tor (suite-wide).
- **Coercion.** No duress key. No plausible-decoy passphrase.

Read the per-tool `does NOT protect` table before you rely on any
of this for what it was not built to do.

## Documentation

| | |
|---|---|
| [MASTER.md](MASTER.md)                  | suite design: vision, aesthetics, multiplex architecture, per-tool sketches |
| [RELEASE_NOTES.md](RELEASE_NOTES.md)    | what landed in this release, build artefacts, verification |
| [docs/INSTALL.md](docs/INSTALL.md)      | per-platform setup, Tor configuration, troubleshooting |
| [docs/USAGE.md](docs/USAGE.md)          | every CLI flag, every in-app command, walkthroughs |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | crypto stack, wire protocols, mlock, decision log |
| [docs/SECURITY.md](docs/SECURITY.md)    | suite-level threat model |
| [docs/tools/](docs/tools/)              | per-tool docs (one file each: VOID, MASK, STRIP, CARRIER, MIRAGE) |
| [docs/FAQ.md](docs/FAQ.md)              | common questions |

## Verify a release

```bash
curl -LO https://github.com/deox420/tower_of_babel/releases/download/v1.0.0/SHA256SUMS
curl -LO https://github.com/deox420/tower_of_babel/releases/download/v1.0.0/babel-1.0.0-linux-x86_64
sha256sum -c SHA256SUMS --ignore-missing
```

Anyone can rebuild from source and compare:

```bash
docker build -f packaging/Dockerfile.build -t babel-build:1.0.0 .
docker run --rm -v "$PWD/dist:/src/dist" babel-build:1.0.0
diff <(sort SHA256SUMS) <(sort dist/SHA256SUMS)
```

The diff must be empty. The build uses a pinned
`python:3.11.10-slim-bookworm` base, `SOURCE_DATE_EPOCH`,
`PYTHONHASHSEED=0`, sorted PyInstaller analysis, and a hash-locked
`requirements.lock`; full contract in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Releases ship two binaries: `babel-<version>-<platform>-<arch>`
(the full suite) and `void-server-<version>-<platform>-<arch>` (the
narrow server-only binary for hardened deployments). Both appear in
the same `SHA256SUMS`.

## Licence

[0BSD](LICENSE). Use it however you want. No warranty.
For life-critical communication, use Signal or SimpleX.
