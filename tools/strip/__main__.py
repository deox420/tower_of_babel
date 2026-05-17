"""Entry for ``python -m tools.strip`` and the legacy ``strip`` shortcut."""
from __future__ import annotations

from tools.strip.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
