# Changelog

Versions follow `MAJOR.MINOR.PATCH`.

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
