"""Default filesystem paths used by the application."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEST_DATA_DIR = DATA_DIR / "test_data"

DEMO_DATA_PATH = TEST_DATA_DIR / "demo_data.ddm.csv"
TEST_DATABASE_CSV_PATH = TEST_DATA_DIR / "test_data.ddm.csv"
DEFAULT_CHECKPOINT_PATH = TEST_DATA_DIR / "test_data.ddm.pkl"


def get_database_output_paths(database_path):
    """Return sibling output paths sharing a database filename stem."""
    path = Path(database_path)
    for suffix in (".ddm.pkl", ".ddm.csv", ".pkl", ".csv"):
        if path.name.lower().endswith(suffix):
            stem = path.name[: -len(suffix)]
            break
    else:
        stem = path.stem

    base_path = path.with_name(stem)
    return {
        "checkpoint": base_path.with_name(f"{stem}.ddm.pkl"),
        "csv": base_path.with_name(f"{stem}.ddm.csv"),
        "macro": base_path.with_name(f"{stem}.cs"),
        "rfps": base_path.with_name(f"{stem}.rfps"),
        "shared_parameters": base_path.with_name(f"{stem}.txt"),
    }
