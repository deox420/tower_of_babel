"""Code shared across Tower of Babel tools.

Subpackages: ``shared.crypto`` (mlock'd buffers, AEAD, KDFs),
``shared.tor`` (control-port client, SOCKS5 detection, ephemeral
onions), ``shared.ui`` (Textual primitives), ``shared.install``
(installer helpers reused by ``babel --setup``), ``shared.link``
(multi-scheme invite codec). See MASTER.md Section 5.
"""
