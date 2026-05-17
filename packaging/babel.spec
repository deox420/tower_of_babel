# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Tower of Babel suite binary.
# Bundles babel/, shared/, and every tool under tools/ behind the
# `babel` entry point. Sorts every Analysis input lexicographically
# so the embedded TOC is byte-identical across machines once
# SOURCE_DATE_EPOCH and PYTHONHASHSEED are pinned.
import os
import sys

block_cipher = None

# SPEC lives in packaging/; project root is one level up.
src_root = os.path.abspath(os.path.join(os.path.dirname(SPEC), '..'))
sys.path.insert(0, src_root)

a = Analysis(
    [os.path.join(src_root, 'babel', '__main__.py')],
    pathex=[src_root],
    binaries=[],
    datas=sorted([
        # VOID's Textual CSS lives next to app.py inside the bundle.
        (os.path.join(src_root, 'tools', 'void', 'client', 'style.tcss'),
         'tools/void/client'),
        # MASK's per-locale alias / bio catalogs (Phase 4).
        (os.path.join(src_root, 'tools', 'mask', 'data', 'en.json'),
         'tools/mask/data'),
        (os.path.join(src_root, 'tools', 'mask', 'data', 'es.json'),
         'tools/mask/data'),
        (os.path.join(src_root, 'tools', 'mask', 'data', 'fr.json'),
         'tools/mask/data'),
        (os.path.join(src_root, 'tools', 'mask', 'data', 'de.json'),
         'tools/mask/data'),
        (os.path.join(src_root, 'tools', 'mask', 'data', 'neutral.json'),
         'tools/mask/data'),
    ], key=lambda x: x[0]),
    hiddenimports=sorted([
        # babel / shared
        'babel',
        'babel.__main__',
        'babel.menu',
        'babel.shell',
        'babel.theme',
        'babel.art',
        'shared',
        'shared.crypto',
        'shared.crypto.secure_mem',
        'shared.tor',
        'shared.tor.control',
        'shared.tor.socks_detect',
        'shared.link',
        'shared.link.invite',
        'shared.ui',
        'shared.ui.step_indicator',
        # tools.void (the only tool wired in Phase 0)
        'tools',
        'tools.void',
        'tools.void.client',
        'tools.void.client.app',
        'tools.void.server',
        'tools.void.server.main',
        # tools.mask (Phase 4)
        'tools.mask',
        'tools.mask.cli',
        'tools.mask.app',
        'tools.mask.alias',
        'tools.mask.avatar',
        'tools.mask.bundle',
        'tools.mask.link',
        'tools.mask.mail',
        'tools.mask.pipeline',
        'tools.mask.setup_check',
        # tools.mirage (Phase 5)
        'tools.mirage',
        'tools.mirage.cli',
        'tools.mirage.app',
        'tools.mirage.caps',
        'tools.mirage.engine',
        'tools.mirage.profile',
        'tools.mirage.schedule',
        'tools.mirage.service',
        'tools.mirage.setup_check',
        'tools.mirage.sites',
        # runtime libs
        'textual',
        'rich',
        'websockets',
        'cryptography',
        'doubleratchet',
        'x3dh',
        'xeddsa',
        'python_socks',
        'python_socks.async_.asyncio',
        # MASK (Phase 4): httpx[socks] uses socksio under the hood.
        'httpx',
        'socksio',
    ]),
    hookspath=[],
    runtime_hooks=[],
    excludes=sorted([
        'tkinter',
    ]),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
a.binaries = sorted(a.binaries, key=lambda x: x[0])
a.datas = sorted(a.datas, key=lambda x: x[0])
a.pure = sorted(a.pure, key=lambda x: x[0])
a.zipfiles = sorted(a.zipfiles, key=lambda x: x[0])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='babel',
    debug=False,
    bootloader_ignore_signals=False,
    # strip=True breaks Windows binaries (PyInstaller's --strip cannot
    # strip MSVC-linked Python DLLs and corrupts them in the bundle).
    # Disabled everywhere so the spec stays cross-platform.
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
