# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: single-file, windowed GUI build of the extractor.

Build with `.\build.ps1` (or `python -m PyInstaller --noconfirm WallpaperExtractor.spec`).
"""

# tkinterdnd2 ships its drag-and-drop support as a Tcl package (tkdnd) of
# .dll/.tcl files rather than plain imports. PyInstaller's bundled contrib hook
# already collects them, so no manual datas entry is needed here -- but if that
# ever regresses, the App base class in wallpaper_engine_extractor/gui.py
# silently falls back to plain tk.Tk and drag-and-drop just stops working in
# the build.

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("wallpaper_engine_extractor/assets/icon.ico", "assets"), ("assets/version_info.txt", "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "scipy", "pandas", "matplotlib", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WallpaperExtractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon="wallpaper_engine_extractor/assets/icon.ico",
    version="assets/version_info.txt",
)
