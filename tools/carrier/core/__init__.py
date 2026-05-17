"""Per-format LSB embedders.

Each module exports ``embed_bytes(cover_bytes, payload_bytes) -> bytes``
and ``extract_bits(cover_bytes, n_bits) -> bytes``, plus a
``cover_info(cover_bytes)`` helper that returns the cover's
geometry + safe capacity. The pipeline composes these with the
header-pack and AEAD layers from ``tools.carrier``.
"""
