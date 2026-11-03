"""Default filesystem paths used by the application."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEST_DATA_DIR = DATA_DIR / "test_data"

DEMO_DATA_PATH = TEST_DATA_DIR / "demo_data.ddm.csv"
TEST_DATABASE_CSV_PATH = TEST_DATA_DIR / "test_data.ddm.csv"
TEST_CHECKPOINT_PATH = TEST_DATA_DIR / "test_data.ddm.pkl"
# Working saves live outside test_data/ (untracked), so saving never rewrites fixtures.
DEFAULT_CHECKPOINT_PATH = DATA_DIR / "database.ddm.json"

# Saving also writes the schedule macro into this Revit 2025 application macro module, when
# it exists on this machine. Build the module in Revit's Macro Manager to pick it up.
REVIT_MACRO_MODULE_DIR = Path(
    r"C:\ProgramData\Autodesk\Revit\Macros\2025\Revit\AppHookup\GLoveMacros\Source\GLoveMacros"
)


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
