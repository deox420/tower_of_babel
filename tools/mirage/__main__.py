"""``python -m tools.mirage`` -- dispatch to the CLI."""
from __future__ import annotations

from tools.mirage.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
