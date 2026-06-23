# PyInstaller spec — builds a single-file Session Hub binary (browser UI).
#
#   pip install -e ".[build]"
#   pyinstaller session-hub.spec
#
# Output: dist/session-hub (or dist/session-hub.exe on Windows). Run it on any
# machine — no Python, pip, or system libraries required. It starts the server
# and opens the dashboard in the default browser.
#
# A spec file (rather than a CLI command) is used so the data-file separator
# and collection logic are identical across Linux / macOS / Windows.
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("sessionhub/static", "sessionhub/static")]
binaries = []
hiddenimports = collect_submodules("uvicorn")

# uvicorn/fastapi load protocol + logging implementations dynamically, so pull
# them in wholesale rather than relying on import-graph discovery. platformdirs
# (+ the jaraco helpers) are required by setuptools' pkg_resources runtime hook.
for pkg in ("uvicorn", "fastapi", "starlette", "anyio", "platformdirs"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += [
    "platformdirs",
    "jaraco.text",
    "jaraco.functools",
    "jaraco.context",
    "more_itertools",
]

# The app package itself: editable installs aren't on a normal import path that
# PyInstaller's graph walker follows, so add the repo root to pathex and collect
# all sessionhub submodules explicitly.
hiddenimports += collect_submodules("sessionhub")

a = Analysis(
    ["scripts/pyinstaller_entry.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # never bundle the native-GUI stack into the browser binary
    excludes=["webview", "gi", "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="session-hub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
