# Install

[← back](../README.md) · **Install** · [Usage](USAGE.md) · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [FAQ](FAQ.md)

---

VOID's installer is a single command per platform. It detects your
package manager, installs Python and Tor (if missing), writes a
per-user `torrc` with `ControlPort 9051` + cookie auth, starts tor in
the background, and `pip install --user`s VOID. It never edits
`/etc/tor/torrc`.

## Linux

```bash
curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh | bash
```

Supports apt / dnf / pacman. The torrc is written to
`~/.config/void/torrc` and tor runs as your user (`tor -f ... --runasdaemon 1`).
If sudo + a system tor service are present, the installer restarts that
instead. PATH gets `~/.local/bin` appended to your shell rc files.

After install, **open a new terminal** so `void` is on PATH.

## macOS

Requires [Homebrew](https://brew.sh):

```bash
curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh | bash
```

Same flow as Linux with `brew install python tor git`. The torrc goes
under `/opt/homebrew/etc/tor/torrc` (Apple Silicon) or
`/usr/local/etc/tor/torrc` (Intel).

## Windows

In PowerShell:

```powershell
iwr -useb https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.ps1 | iex
```

Installs Python 3.11 and Tor Browser via `winget` if missing. The
installer searches for `tor.exe` in PATH, `%LOCALAPPDATA%`, Program
Files, Desktop, Downloads, and recursively in
`%LOCALAPPDATA%\Microsoft\WinGet\Packages\`. The torrc is written to
`%APPDATA%\void\torrc`. PATH updates only reach **new** PowerShell
windows; close and reopen.

## Android — Termux

Install [Termux from F-Droid](https://f-droid.org/packages/com.termux/)
(**not** the Play Store version — it's unmaintained and breaks `pkg`),
then:

```bash
curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh | bash
```

Termux extras:

- First run installs `rust binutils` (~150 MB) so `pydantic-core` can
  build (no aarch64-android wheels on PyPI).
- First run also clones `github.com/Syndace/libxeddsa` and builds it
  via cmake (the Python `xeddsa` wrapper links against `-lxeddsa`).
- Total first-time install: 5–10 minutes.

To keep VOID alive when the screen turns off:

```bash
termux-wake-lock
```

## Verify the install

```bash
void --setup
```

Expected:

```
VOID setup check
================
  Tor SOCKS5: OK on 127.0.0.1:9050
  mlock available: OK
  swap active:     yes/no
  terminal:        OK
```

## Reproducible install (Docker)

If you don't trust the installer or any prebuilt binary, build VOID
from source inside a pinned container:

```bash
git clone https://github.com/deox420/tower_of_babel.git
cd tower_of_babel
docker build -f packaging/Dockerfile.build -t void-build .
docker run --rm -v "$PWD/dist:/src/dist" void-build
cat dist/SHA256SUMS
```

Two consecutive runs produce byte-identical binaries. Details in
[`packaging/Dockerfile.build`](../packaging/Dockerfile.build).

---

## Troubleshooting

### `void: command not found`

PATH wasn't refreshed for the current shell.

```bash
export PATH="$HOME/.local/bin:$PATH"      # Linux / macOS / Termux
$env:PATH += ";$env:APPDATA\Python\Python311\Scripts"   # Windows
```

Open a new terminal to get the change permanently. If the binary
isn't there at all, run as a module:

```bash
cd ~/.local/share/void          # or %LOCALAPPDATA%\void on Windows
python -m client --setup
```

### `Tor SOCKS5: not detected`

Start tor with the per-user torrc the installer wrote:

```bash
tor -f ~/.config/void/torrc &              # Linux / Termux
brew services start tor                    # macOS
```

Windows: open Tor Browser once (runs tor on `:9150`), or:

```powershell
Start-Process "$env:LOCALAPPDATA\Tor Browser\Browser\TorBrowser\Tor\tor.exe" `
    -ArgumentList @('-f',"$env:APPDATA\void\torrc") -WindowStyle Hidden
```

### `mlock unavailable, keys may touch swap`

The OS denied `mlock` (common on Termux without root, some hardened
kernels). VOID continues without it; a one-time stderr warning is
shown. If swap is also enabled, the IK seed may end up on disk —
disable swap if that matters for your threat model.

### Termux: `pydantic-core` or `xeddsa` build fails

The installer should handle both, but if it didn't:

```bash
# pydantic-core needs Rust
pkg install -y rust binutils
# xeddsa needs libsodium + libxeddsa
pkg install -y cmake libsodium
git clone --depth 1 https://github.com/Syndace/libxeddsa.git ~/.cache/libxeddsa
cd ~/.cache/libxeddsa && mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$PREFIX
make -j$(nproc) && make install
pip install --user --no-cache-dir -e ~/.local/share/void
```

### Windows: TUI looks broken

The default Windows conhost has limited ANSI support. Use
[Windows Terminal](https://aka.ms/terminal):

```powershell
winget install -e --id Microsoft.WindowsTerminal
```

### `void --make-invite` says "Could not reach Tor's control port"

The torrc the installer wrote includes `ControlPort 9051`; check it:

```bash
grep -E 'ControlPort|CookieAuth' ~/.config/void/torrc       # Linux
cat "$env:APPDATA\void\torrc"                                # Windows
```

If the lines are missing, the install didn't reach that step. Add
them manually and restart tor.

---

[← back](../README.md) · [Usage →](USAGE.md)
