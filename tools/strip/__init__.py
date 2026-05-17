"""STRIP - metadata laundry.

Action tool (MASTER.md 4.4): one-shot, no slot, no lingering state.
The CLI is the primary surface; the in-chrome screen wraps the same
core pipeline. Per-format strippers live in ``tools.strip.core``
and are pure functions on ``bytes`` so the pentest harness can
exercise them without Textual or the filesystem.
"""
