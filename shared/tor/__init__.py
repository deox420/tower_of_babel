"""Tor integration primitives shared by every Tower of Babel tool.

Holds the control-port client (``control``), the SOCKS5 detection
helpers (``socks_detect``), and the ephemeral v3-onion wrapper
(``ephemeral_onion``). VOID, MASK, and MIRAGE all import from here
so the Tor surface stays in one place. See MASTER.md Section 5.4.
"""
