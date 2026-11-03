"""Build the standalone DesignDataManager.exe with PyInstaller.

    <build python> build_exe.py [master database] [--console]

The master database (default ``data/database.ddm.json``) is bundled into the .exe and
opened on first launch; saves then go to a ``data`` folder next to the .exe. The .exe is
written to ``dist/``; ``--console`` builds one that shows errors in a console window.

Build with a pip environment, not the project's ``.conda`` one: conda's numpy uses Intel
MKL, which makes a 230 MB .exe that takes ~25 s to start. A venv made from the conda
Python with pip's numpy/pandas gives ~35 MB:

    .\\.conda\\python.exe -m venv %LOCALAPPDATA%\\ddm-build\\venv
    %LOCALAPPDATA%\\ddm-build\\venv\\Scripts\\pip install pandas numpy openpyxl requests pyinstaller

PyInstaller works in a temporary folder outside OneDrive, whose syncing otherwise
interferes with the build.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "DesignDataManager"


def build(master_database, console=False):
    import PyInstaller.__main__

    master_database = Path(master_database).resolve()
    if not master_database.exists():
        raise SystemExit(f"No master database at {master_database}; import or save one first.")
    # A venv made from a conda Python still loads Tcl/Tk, libffi and friends from the conda
    # environment's Library\bin; put it on PATH so PyInstaller finds and bundles them.
    conda_bin = Path(sys.base_prefix) / "Library" / "bin"
    if conda_bin.is_dir():
        os.environ["PATH"] = f"{conda_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    with tempfile.TemporaryDirectory(prefix="ddm-build-") as work:
        work = Path(work)
        staged = work / "master.ddm.json"
        shutil.copy2(master_database, staged)
        PyInstaller.__main__.run([
            str(PROJECT_ROOT / "ddm_gui.py"),
            "--name", APP_NAME,
            "--onefile",
            "--console" if console else "--windowed",
            "--noconfirm",
            "--clean",
            "--add-data", f"{staged};.",
            "--hidden-import", "openpyxl",
            "--exclude-module", "pytest",
            "--workpath", str(work / "build"),
            "--specpath", str(work),
            "--distpath", str(PROJECT_ROOT / "dist"),
        ])
    exe = PROJECT_ROOT / "dist" / f"{APP_NAME}.exe"
    print(f"\nBuilt {exe} ({exe.stat().st_size / 1e6:.0f} MB) with {master_database.name} as its master database.")
    return exe


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if arg != "--console"]
    build(args[0] if args else PROJECT_ROOT / "data" / "database.ddm.json", console="--console" in sys.argv)
