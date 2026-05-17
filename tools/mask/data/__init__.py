"""Per-locale catalogs for MASK alias and bio generation.

JSON files in this package are read at runtime by ``tools.mask.alias``
via ``importlib.resources``. They are declared as ``package_data`` in
``pyproject.toml`` so editable installs and PyInstaller bundles both
find them.
"""
from __future__ import annotations
