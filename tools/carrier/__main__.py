"""Entry for ``python -m tools.carrier`` and the ``carrier`` script alias."""
from __future__ import annotations

from tools.carrier.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
