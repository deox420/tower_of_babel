# VOID v0.5.0 — first public release

Ephemeral terminal messenger. End-to-end encrypted via X3DH + Double
Ratchet over Tor. No accounts, no history, no disk.

## Install

| Platform | Command |
|---|---|
| Linux / macOS / Termux | `curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh \| bash` |
| Windows (PowerShell) | `iwr -useb https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.ps1 \| iex` |
| Android | install [Termux from F-Droid](https://f-droid.org/packages/com.termux/), then run the Linux command |

After install:

```bash
void --make-invite    # to host (prints a void:// link)
void                  # to join (paste the void:// link)
```

## Binaries

Built reproducibly by GitHub Actions:

- `void-0.5.0-linux-x86_64` + `void-server-0.5.0-linux-x86_64`
- `void-0.5.0-macos-arm64` + `void-server-0.5.0-macos-arm64`
- `void-0.5.0-windows-x86_64.exe` + `void-server-0.5.0-windows-x86_64.exe`
- `SHA256SUMS`

Intel Mac users: install via pip from source, or run the macOS arm64
binary under Rosetta 2. Termux (Android) users should install via pip —
PyInstaller binaries don't run on Android.

## Verify

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

Or rebuild and diff:

```bash
git clone --depth 1 --branch v0.5.0 https://github.com/deox420/tower_of_babel.git
cd tower_of_babel
docker build -f packaging/Dockerfile.build -t void-build:0.5.0 .
docker run --rm -v "$PWD/dist:/src/dist" void-build:0.5.0
diff <(sort SHA256SUMS) <(sort dist/SHA256SUMS)
```

Empty diff = the binary came from this source tree.

## Before serious use

Read the [threat model](https://github.com/deox420/tower_of_babel/blob/main/docs/SECURITY.md).
VOID is not a Signal replacement. Endpoint compromise, screenshots,
traffic analysis by a global passive adversary, and quantum
"harvest now, decrypt later" are all out of scope.

Full changes: [CHANGELOG.md](https://github.com/deox420/tower_of_babel/blob/main/CHANGELOG.md). License: [0BSD](https://github.com/deox420/tower_of_babel/blob/main/LICENSE).
