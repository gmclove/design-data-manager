"""Default filesystem paths used by the application."""

import json
import os
import sys
from pathlib import Path

APP_VERSION = "0.1.0 Beta"
NEW_ISSUE_URL = "https://github.com/gmclove/design-data-manager/issues/new"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Packaged as a standalone .exe (PyInstaller), bundled files unpack to a temporary folder and
# working data lives in a "data" folder next to the .exe.
FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
# Each user's settings: their Revit macro module, and where their working database lives.
USER_SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "DesignDataManager" / "settings.json"


def _database_folder_setting():
    """The ``database_folder`` in the user's settings (e.g. a OneDrive folder), or ``None``."""
    try:
        folder = json.loads(USER_SETTINGS_PATH.read_text(encoding="utf-8")).get("database_folder")
    except (OSError, ValueError, AttributeError):
        return None
    return Path(folder) if folder else None


# Working databases: the database_folder setting if there is one, else a "data" folder in the
# project (next to the .exe when packaged).
DATA_DIR = _database_folder_setting() or (
    Path(sys.executable).resolve().parent / "data" if FROZEN else PROJECT_ROOT / "data"
)
TEST_DATA_DIR = PROJECT_ROOT / "data" / "test_data"

DEMO_DATA_PATH = TEST_DATA_DIR / "demo_data.ddm.csv"
TEST_DATABASE_CSV_PATH = TEST_DATA_DIR / "test_data.ddm.csv"
TEST_CHECKPOINT_PATH = TEST_DATA_DIR / "test_data.ddm.pkl"
# Working saves live outside test_data/ (untracked), so saving never rewrites fixtures.
DEFAULT_CHECKPOINT_PATH = DATA_DIR / "database.ddm.json"
# Opened on first launch, before anything is saved: the demo when run from source, the
# master database bundled into the .exe when packaged.
STARTER_DATABASE_PATH = BUNDLE_DIR / "master.ddm.json" if FROZEN else DEMO_DATA_PATH


def get_database_output_paths(database_path):
    """Return sibling output paths sharing a database filename stem."""
    path = Path(database_path)
    for suffix in (".ddm.json", ".ddm.pkl", ".ddm.csv", ".json", ".pkl", ".csv"):
        if path.name.lower().endswith(suffix):
            stem = path.name[: -len(suffix)]
            break
    else:
        stem = path.stem

    base_path = path.with_name(stem)
    return {
        "checkpoint": base_path.with_name(f"{stem}.ddm.json"),
        "csv": base_path.with_name(f"{stem}.ddm.csv"),
        "macro": base_path.with_name(f"{stem}.cs"),
        "rfps": base_path.with_name(f"{stem}.rfps"),
        "shared_parameters": base_path.with_name(f"{stem}.txt"),
    }
