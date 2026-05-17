"""CARRIER -- steganography.

Action tool (MASTER.md 4.4). Embeds an AES-256-GCM-encrypted
payload in the LSB of a PNG or WAV cover. Passphrase is fed to
Argon2id to derive the AES key. No magic header in the cover --
the validity signal is the GCM tag check, so an inspector without
the passphrase cannot distinguish a CARRIER output from a cover
with merely noisy LSBs.

Per-format embedders live in ``tools.carrier.core`` and operate
on bytes objects so the pentest harness can exercise them without
touching the filesystem.
"""
