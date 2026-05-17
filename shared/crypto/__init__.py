"""Cross-tool cryptographic primitives.

Holds the implementations of memory-locked buffers, AEAD wrappers,
and KDFs used by more than one tool in the suite. Anything that
should be subject to the suite's "trust the math, not the network"
audit gate lives here, not in any individual tool. See MASTER.md
Section 5.
"""
