# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the VOID client.
import os
import sys

block_cipher = None

# SPEC lives in packaging/; project root is one level up.
src_root = os.path.abspath(os.path.join(os.path.dirname(SPEC), '..'))
sys.path.insert(0, src_root)

a = Analysis(
    [os.path.join(src_root, 'client', '__main__.py')],
    pathex=[src_root],
    binaries=[],
    datas=sorted([
        (os.path.join(src_root, 'client', 'style.tcss'), 'client'),
    ], key=lambda x: x[0]),
    hiddenimports=sorted([
        'textual',
        'rich',
        'websockets',
        'cryptography',
        'doubleratchet',
        'x3dh',
        'xeddsa',
        'python_socks',
        'python_socks.async_.asyncio',
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
    name='void',
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
