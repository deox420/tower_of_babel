# Usage

[← back](../README.md) · [Install](INSTALL.md) · **Usage** · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [FAQ](FAQ.md)

---

## CLI — `void` (client)

```
void [--onion ADDR:PORT] [--clearnet] [--server URL] [--insecure]
     [--socks URL] [--no-cover] [--setup] [--host] [--make-invite]
```

| Flag | Default | Description |
|---|---|---|
| `--onion ADDR:PORT` | (prompted in lobby) | Hidden-service address to connect to |
| `--clearnet` | off | Bypass Tor; connect directly to a `ws://` server (local testing only) |
| `--server URL` | `wss://localhost:8765` | Explicit `ws(s)://` URL; overrides `--onion` routing |
| `--insecure` | off | Allow plain `ws://` and skip TLS verification |
| `--socks URL` | `socks5://127.0.0.1:9050` | SOCKS5 proxy for `--onion`; auto-detected across 9050/9150/9151 |
| `--no-cover` | off | Disable cover-traffic dummies (debug) |
| `--setup` | — | Health check (Tor, mlock, swap, terminal) and exit |
| `--host` | — | Run `void-server` in this process; remaining args pass through |
| `--make-invite` | — | One-shot host: ephemeral onion + embedded server + `void://` invite |

## CLI — `void-server` (relay)

```
void-server [--host HOST] [--port PORT] [--cert PEM] [--key PEM]
            [--insecure] [--no-jitter]
```

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address; expose via a Tor hidden service |
| `--port` | `8765` | TCP port |
| `--cert` / `--key` | — | TLS cert + key for direct `wss://` access |
| `--insecure` | off | Plain `ws://` (use only behind a hidden service) |
| `--no-jitter` | off | Disable 50–350 ms forwarding jitter (tests) |

## In-app commands

| Command | Effect |
|---|---|
| `/help` | List commands |
| `/peers` | Peers in the room with their fingerprint and SAS words |
| `/verify <fp>` | Print 5-word SAS for one peer — compare out-of-band |
| `/trust <fp>` | Mark peer TRUSTED after SAS match (messages get `✦` prefix) |
| `/whoami` | Show your full 64-hex IK fingerprint |
| `/burn <seconds>` | Local disappearing-message timer (10–86400) |
| `/burn off` | Stop disappearing-message mode |
| `/map` | Open the starmap (active-node count, decorative) |
| `/leave` | Purge this room, return to lobby |
| `/quit` | Purge and close VOID |

Keyboard:

| Keys | Effect |
|---|---|
| `Ctrl+C` / `Ctrl+Q` | Same as `/quit` |
| `Ctrl+J` / `Alt+Enter` | Newline in the input |
| `F1` | Open help wizard (lobby only) |
| `Esc` | Close help / return from starmap |

## Footer

Standard layout:

```
[TOR]  [PAD]  [COVER]  [RATCHET]    [BURN 60s]   ← when /burn is on
```

On narrow terminals (Termux portrait): `T·P·C·R   burn:60s`.

| Indicator | Green | Other |
|---|---|---|
| `TOR` | routed via Tor onion | `CLR` red = clearnet, server sees your IP |
| `PAD` | always green (ciphertext is a 1024-byte multiple) | — |
| `COVER` | cover-traffic dummies active | `no-cover` gray (debug only) |
| `RATCHET` | every peer has a working DR session | yellow = handshake pending; red = failed |

---

## Walkthrough — Alice (Linux host) ↔ Bob (Termux peer)

### 1. Alice hosts

```bash
void --setup        # confirms Tor + mlock OK
void --make-invite
```

Output:

```
═══════════════════════════════════════════════════
  VOID — hosting an ephemeral room
═══════════════════════════════════════════════════

  Share this invite with your peer (one line):

    void://eyJvIjoiM3djdzJ4ZXRqZXVxZGdzNWdma3N6N3lubmNw...

  details inside the invite:
    onion    : abcdef…2345.onion:8765
    room key : KvW7p2qX
    password : C9q4ZbR2vKtU

  The invite stays valid only while this command runs.
  Ctrl+C to stop and delete the onion.
```

Under the hood: Alice's client speaks the Tor control protocol on
`127.0.0.1:9051`, authenticates via SAFECOOKIE, asks Tor for a v3
onion (`ADD_ONION NEW:ED25519-V3 Flags=DiscardPK`), embeds a
`void-server` bound to `127.0.0.1:<random>`, generates a random room
key and password, packs them into a `void://` link, and prints it.

### 2. Alice sends the link to Bob

Through any trusted channel (Signal, in-person, etc.). The link IS
the secret — anyone with it can decrypt everything in this room.

### 3. Bob joins

In Termux:

```bash
void
```

In the lobby, Bob long-presses the `INVITE` field and pastes the
`void://...`. The three fields below autofill. ENTER.

CONNECTING shows five steps as the client routes through Tor, fetches
Alice's prekey bundle, runs the X3DH handshake, and initialises a
Double Ratchet session. Then the chat opens.

### 4. They chat

Each message is wrapped as `{"v":3,"text":"…"}`, padded to a 1024-byte
multiple, encrypted with the ratchet's next message key (AES-256-GCM,
HKDF-derived IV), signed Ed25519 over `ratchet_pub || ciphertext`, and
sent to Alice's embedded server, which adds 50–350 ms jitter and
forwards it to Bob.

### 5. They verify each other (SAS)

Both run `/peers`:

```
peers in this room:
  <abc12345>  UNVERIFIED  SAS: reindeer · enrollment · gazelle · frequency · beehive
```

Alice phones Bob, reads the 5 words. If they match, both run
`/trust abc12345`. From now on each other's messages get a `✦` star.

If a malicious server had inserted itself, the words would differ on
the two ends — that's how SAS catches MITM.

### 6. `/burn` (optional)

`/burn 30` makes Alice's outgoing messages disappear from **her** chat
log after 30 s. Bob's screen and his scrollback are unaffected — burn
is best-effort and local-only.

### 7. End the session

- Either side: `/leave` (purge and return to lobby) or `/quit`.
- Alice's Ctrl+C on the `--make-invite` window deletes the onion.
  Nothing persists on either machine.

## Self-test on one machine

Two terminals on the same host. Terminal 1: `void --make-invite`;
copy the link. Terminal 2: `void`, paste, ENTER. You're now chatting
with yourself through your local Tor and your local onion. Useful as
a smoke test after install.

---

[← Install](INSTALL.md) · [Architecture →](ARCHITECTURE.md)
