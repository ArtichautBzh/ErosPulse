# -*- mode: python ; coding: utf-8 -*-
"""
ErosPulse.spec
===============
PyInstaller build configuration for ErosPulse.

IMPORTANT: PyInstaller does not cross-compile. Running this on Windows
produces ErosPulse.exe; running it on macOS produces an ErosPulse.app
bundle; running it on Linux produces a native ELF binary. You must run
it on the same OS as your target.

Usage (from the project root, in the OS you're targeting):
    pip install pyinstaller
    pyinstaller ErosPulse.spec

Or simply run build_exe.bat (Windows) / build_exe.sh (macOS/Linux),
which do this automatically and also make sure PyInstaller can see the
vendored dependencies in vendor/ (so requests/urllib3/etc. get bundled
into the executable without needing a separate `pip install`).

Produces a single-file, windowed executable (no console window, since
ErosPulse is a Tkinter GUI app) at dist/ErosPulse(.exe).
"""

from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root), str(project_root / "vendor")],
    binaries=[],
    datas=[],
    hiddenimports=[
        "core",
        "core.constants",
        "core.lovense_client",
        "core.vibration_command",
        "core.pattern_generator",
        "core.ai_prompt",
        "core.app_state",
        "core.version",
        "ui",
        "ui.theme",
        "ui.app_window",
        "ui.pages",
        "ui.pages.home_page",
        "ui.pages.connection_page",
        "ui.pages.text_page",
        "ui.widgets",
        "ui.widgets.sequence_chart",
        # requests pulls some of its own dependencies in dynamically;
        # listing them explicitly avoids surprises across PyInstaller
        # versions.
        "charset_normalizer",
        "idna",
        "urllib3",
        "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ErosPulse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed app: no console window behind the GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
