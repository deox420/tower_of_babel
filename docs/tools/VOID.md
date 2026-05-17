*confusion of tongues, by design*

```
██╗   ██╗ ██████╗ ██╗██████╗
██║   ██║██╔═══██╗██║██╔══██╗
██║   ██║██║   ██║██║██║  ██║
╚██╗ ██╔╝██║   ██║██║██║  ██║
 ╚████╔╝ ╚██████╔╝██║██████╔╝
  ╚═══╝   ╚═════╝ ╚═╝╚═════╝
```

# VOID - ephemeral encrypted messenger

## 1 - What this is

VOID is a terminal chat for short private conversations. Every
session generates a fresh ephemeral identity; when you close the
program, the conversation is gone. End-to-end encryption between
every pair of peers (X3DH initial key agreement + Double Ratchet
per-message keys + Ed25519 signatures), routed over Tor v3 onion
addresses. The server is a blind relay: it sees who connects to
the room but never sees plaintext.

VOID is a *service* tool (MASTER.md 4.4): once you join a room it
keeps running in a slot while you switch between other rooms or
other tools. The chrome's slot bar shows `[1:VOID 2 peers]` while
it is active.

The deep design lives in [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
(crypto stack, X3DH, Double Ratchet, wire format) and
[docs/SECURITY.md](../SECURITY.md) (full threat model). This file
is the short per-tool summary in the suite's standard layout.

## 2 - What this protects

| Surface | Protection |
|---|---|
| Message contents | AES-256-GCM with per-message keys (Double Ratchet). |
| Forward secrecy | Each new message advances the ratchet; past keys cannot be recovered from current state. |
| Future secrecy | A compromised single key does not let the attacker read future messages once both peers send again. |
| Identity authentication | X3DH initial AKE + Ed25519 signatures on every outbound message. Forged bundles are rejected by `KeyAgreementException`; forged `from` fields by the server's `CONNS[ws]` map. |
| Server-side plaintext exposure | None. The relay never sees the message body or the per-message keys. |
| Replay | Double Ratchet's `DuplicateMessageException`; the receiver drops re-injected frames. |
| Wire-tap of loopback / Tor | Verified by `pentest/void/wire_tap_test.py`: a 54 KB capture of a full session contains zero plaintext. |
| Key material in RAM | `shared.crypto.secure_mem.SecureBytes` (mlock or VirtualLock + zero-on-free). |
| Burn on exit | `/burn` and Ctrl+C zero every `SecureBytes` buffer before exit. |
| Server hardening | `MAX_CONNECTIONS=512`, `_valid_bundle()`, `_valid_dr_envelope()`, `_valid_signature()`, `_valid_x3dh_envelope()`; full table in `pentest/REPORT.md`. |

## 3 - What this does NOT protect

| Risk | Why it survives |
|---|---|
| Endpoint compromise | If your machine is owned, no protocol helps. |
| Metadata at the relay | The server sees room ID, connect time, byte counts. It does not see who you are talking to in clear text, but it knows you are connected. |
| Wire-rate asymmetry | A passive observer watching both ends can distinguish talker from listener. VOID narrows the gap with cover frames to ~1.3x, not 1.0x. |
| SAS grinding | 40-bit SAS. Grinding cost about 10^12 per session; impractical for opportunistic attackers, possible for high-budget ones. Compare in-band. |
| Global Passive Adversary on Tor | Single-hop Tor; an entity that sees both ends of the circuit can correlate. No mixnet. |
| Quantum HNDL | Today's ciphertexts captured today are at risk under a future cryptographically relevant quantum computer. |
| Coercion | No duress key. No plausible-decoy session. |
| Out-of-band onion pinning | First-connect TOFU. If your invite link was tampered with before it reached you, you connect to an attacker. Verify the SAS in person. |

## 4 - CLI flags

```
babel void                              # join the lobby
babel void --make-invite                # host: print a void:// link, hold the room
babel void --setup                      # diagnostic (Tor / mlock / xeddsa / etc.)
babel void --host                       # run void-server in the same process
babel void --onion <addr.onion>[:port]  # join a known onion directly
babel void --server <ws-url>            # explicit server URL (with --clearnet)
babel void --clearnet                   # bypass Tor (red banner; loopback testing)
babel void --insecure                   # WS without TLS (loopback testing only)
babel void --socks <socks5-url>         # explicit SOCKS5 proxy URL
babel void --no-cover                   # disable cover-traffic dummies
```

Full flag reference in [docs/USAGE.md](../USAGE.md).

## 5 - In-app commands and keys

Plain text typed in the chat input is sent as a message; there is no
`/msg` command.  Slash commands cover everything else:

| Command / key | Effect |
|---|---|
| `<text>` | send `<text>` to the room (plain typed input) |
| `/peers` | list peers with their 5-word SAS and trust status |
| `/verify <fp8>` | print the 5-word SAS for one peer (compare out-of-band) |
| `/trust <fp8>` | mark a peer as TRUSTED after a successful SAS compare |
| `/whoami` | show your own fingerprint |
| `/map` | open the interstellar peer map |
| `/burn` | zero every buffer and exit |
| `/leave` | leave the room (back to the menu) |
| `/quit` | same as `/burn` -- purge + close |
| `Ctrl+C`, `Ctrl+Q` | quit the suite (burns every live service) |

Pasting an invite happens in the **lobby** screen (the input field
labelled "PASTE AN INVITE"), not as a chat command.

Full command reference in [docs/USAGE.md](../USAGE.md).

## 6 - Worked walkthrough

```
$ babel void --make-invite
[+] tor SOCKS5    9050  ok
[+] tor control   9051  ok
[+] ephemeral onion published: 3kx...onion
[+] invite link: void://eyJpayI6Ii4uLi4u...

(host stays open)

----

$ babel void
(lobby screen)
> <paste void://... into the input field, press Enter>
[+] tor SOCKS5    9050  ok
[+] connecting to 3kx...onion
[+] X3DH ok, double ratchet up
(in-room)
> hello                       <- plain text = message
< hi
> /verify a1b2c3d4             <- show SAS to compare out-of-band
  SAS words: orbit-cipher-velvet-shore-quill
> /trust a1b2c3d4              <- after both sides see the same words
```

## 7 - Architecture

```
tools/void/
  client/                  # the TUI + the cryptographic state machine
    app.py                 # Textual App
    secure_mem.py          # shim -> shared/crypto/secure_mem
    ratchet.py             # Double Ratchet + AES-256-GCM glue
    host.py                # host-side ephemeral onion via shared/tor/control
    setup_check.py
    screens/               # lobby / chat / sas / wizard
  server/                  # blind relay (its own narrow binary)
    main.py
    rooms.py
    guards.py              # bundle / DR-envelope / signature / X3DH validators
```

`shared/` modules consumed:

- `shared.crypto.secure_mem.SecureBytes` (mlock'd buffer with zero-on-free).
- `shared.tor.control.TorControl` (host's ADD_ONION flow).
- `shared.tor.socks_detect.detect_socks_port` (9050 / 9150 / 9151 probe).
- `shared.link.invite` (void:// codec; suite-wide).

Crypto primitives go through pyca/cryptography (`AESGCM`, HKDF),
`xeddsa` (Ed25519 <-> X25519 on the IK), and `doubleratchet` /
`x3dh` for the protocol state machine.

## 8 - Reproducible build notes

VOID is the only tool that ships a separate, narrow binary:
`void-server-<version>-<platform>-<arch>` is built by
`packaging/void-server.spec` and contains the server alone (no
Pillow, no argon2-cffi, no httpx). Useful for hardened deployments
where the relay runs on its own host and minimising the attack
surface matters.

The full-suite `babel` binary also contains VOID's client + server,
so most users only need that one. Both are listed in
`SHA256SUMS` at every release.

The reproducible-build contract is suite-wide; see
[docs/ARCHITECTURE.md](../ARCHITECTURE.md). No per-tool overrides.
