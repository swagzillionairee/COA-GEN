# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPEC).resolve().parents[1]
streamlit_datas, streamlit_binaries, streamlit_hidden = collect_all("streamlit")

datas = streamlit_datas + [
    (str(root / "app.py"), "."),
    (str(root / "templates"), "templates"),
    (str(root / "assets"), "assets"),
    (str(root / ".streamlit"), ".streamlit"),
    (str(root / "THIRD_PARTY_LICENSES.md"), "."),
    (str(root / "LICENSE"), "."),
    (str(root / "VERSION"), "."),
]

hiddenimports = sorted(
    set(
        streamlit_hidden
        + collect_submodules("coa")
        + [
            "matplotlib.backends.backend_agg",
            "pikepdf",
            "pypdf",
            "fitz",
            "PIL._tkinter_finder",
        ]
    )
)

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root)],
    binaries=streamlit_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "notebook"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="COAGenerator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(root / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="COAGenerator",
)
