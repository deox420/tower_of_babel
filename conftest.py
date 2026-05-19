"""Root conftest -- ensure the repo root precedes any installed copy.

A previously-installed ``tower-of-babel`` wheel under the user's
site-packages will shadow the working-tree ``babel/`` package
during ``pytest`` runs unless we pin sys.path explicitly here.
Pentest must always exercise the *source* tree, never an aging
sibling install.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# Strip an existing editable-install finder for ``tower-of-babel``
# from sys.path -- it intercepts ``import babel`` before our local
# tree can answer.  The finder is registered as a sys.path entry of
# the form ``__editable__.tower_of_babel-*.finder.__path_hook__``.
sys.path[:] = [
    p for p in sys.path
    if not (isinstance(p, str)
            and "__editable__.tower_of_babel" in p)
]

# Editable namespace finders are also wired into ``sys.path_hooks``
# and ``sys.path_importer_cache``.  Yank them so a fresh import
# walks our own working tree first.
def _purge_editable_hooks() -> None:
    bad_names = ("_EditableNamespaceFinder", "tower_of_babel")
    sys.path_hooks[:] = [
        h for h in sys.path_hooks
        if not any(b.lower() in repr(h).lower() for b in bad_names)
    ]
    for key in list(sys.path_importer_cache):
        finder = sys.path_importer_cache.get(key)
        if finder is None:
            continue
        rep = repr(finder).lower()
        if any(b.lower() in rep for b in bad_names):
            sys.path_importer_cache.pop(key, None)
    try:
        def _is_editable_finder(f) -> bool:
            # The editable install adds class objects (not instances)
            # to sys.meta_path -- ``f.__name__`` is the right probe.
            name = getattr(f, "__name__", "") or type(f).__name__
            mod  = getattr(f, "__module__", "") or ""
            tags = (name + " " + mod).lower()
            return (
                "editablefinder" in tags
                or "editablenamespacefinder" in tags
                or "tower_of_babel" in tags
                or "void_chat" in tags
            )
        sys.meta_path[:] = [
            f for f in sys.meta_path if not _is_editable_finder(f)
        ]
    except Exception:
        pass

_purge_editable_hooks()

if _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, _HERE)

# Drop already-imported submodules from any sibling install so the
# next ``from babel.menu import ...`` reaches the working tree.
for _key in list(sys.modules):
    if _key == "babel" or _key.startswith("babel."):
        sys.modules.pop(_key, None)
    elif _key == "shared" or _key.startswith("shared."):
        sys.modules.pop(_key, None)
    elif _key == "tools" or _key.startswith("tools."):
        sys.modules.pop(_key, None)
