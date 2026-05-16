<div align="center">

```
       ██╗   ██╗  ██████╗  ██╗ ██████╗
       ██║   ██║ ██╔═══██╗ ██║ ██╔══██╗
       ██║   ██║ ██║   ██║ ██║ ██║  ██║
       ╚██╗ ██╔╝ ██║   ██║ ██║ ██║  ██║
        ╚████╔╝  ╚██████╔╝ ██║ ██████╔╝
         ╚═══╝    ╚═════╝  ╚═╝ ╚═════╝
```

**Ephemeral terminal messenger.**
End-to-end encrypted. Tor-only. Nothing touches disk.

[![license](https://img.shields.io/badge/license-0BSD-2d6a4f?style=flat-square)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11+-2d6a4f?style=flat-square)](https://www.python.org)
[![platforms](https://img.shields.io/badge/platforms-linux%20%7C%20macos%20%7C%20windows%20%7C%20android-2d6a4f?style=flat-square)](docs/INSTALL.md)
[![transport](https://img.shields.io/badge/transport-Tor-6cdcff?style=flat-square)](https://www.torproject.org)
[![crypto](https://img.shields.io/badge/crypto-X3DH%20%2B%20Double%20Ratchet-6cdcff?style=flat-square)](docs/ARCHITECTURE.md)
[![build](https://img.shields.io/badge/build-reproducible-6cdcff?style=flat-square)](packaging/Dockerfile.build)
[![release](https://img.shields.io/github/v/release/deox420/tower_of_babel?style=flat-square&color=ffd166)](https://github.com/deox420/tower_of_babel/releases/latest)

</div>

---

VOID is a terminal chat for short private conversations. End-to-end
encryption between every pair of peers (X3DH + Double Ratchet),
routed through Tor. The server is a blind relay: it never sees
plaintext. When you close the program, the conversation is gone.

## Install

One command per platform:

| Platform | Command |
|---|---|
| Linux / macOS / Termux | `curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh \| bash` |
| Windows (PowerShell)  | `iwr -useb https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.ps1 \| iex` |
| Android (Termux)      | install [Termux from F-Droid](https://f-droid.org/packages/com.termux/) first, then the Linux command above |

> Android: install Termux **from F-Droid only**. The Play Store version is unmaintained and breaks `pkg`.

Prebuilt binaries for Linux x86_64, macOS arm64, and Windows x86_64 are also attached to the
[latest release](https://github.com/deox420/tower_of_babel/releases/latest) with `SHA256SUMS`.

## Use

```bash
# host (terminal 1)               peer (terminal 2)
void --make-invite                void
# prints a void:// link            paste it in the lobby, ENTER
```

That's the full flow. The host's terminal stays open during the chat;
Ctrl+C destroys the ephemeral onion and the room ends.

## Documentation

| | |
|---|---|
| [Install](docs/INSTALL.md) | per-platform setup, Tor configuration, troubleshooting |
| [Usage](docs/USAGE.md) | every CLI flag, every in-app command, a walkthrough |
| [Architecture](docs/ARCHITECTURE.md) | crypto stack, wire protocol, mlock, ratchet |
| [Security](docs/SECURITY.md) | threat model — what VOID protects, what it doesn't |
| [FAQ](docs/FAQ.md) | common questions |

## Verify a release

```bash
curl -LO https://github.com/deox420/tower_of_babel/releases/download/v0.5.0/SHA256SUMS
curl -LO https://github.com/deox420/tower_of_babel/releases/download/v0.5.0/void-0.5.0-linux-x86_64
sha256sum -c SHA256SUMS --ignore-missing
```

Anyone can also rebuild from source and compare:

```bash
docker build -f packaging/Dockerfile.build -t void-build .
docker run --rm -v "$PWD/dist:/src/dist" void-build
```

## License

[0BSD](LICENSE). Use it however you want. No warranty.
For life-critical communication, use Signal or SimpleX.
