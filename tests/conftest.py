import pytest

import ddm_gui


@pytest.fixture(autouse=True)
def no_real_macro_modules(tmp_path, monkeypatch):
    """Saving installs the schedule macro in the user's Revit macro module; never a real one in tests."""
    monkeypatch.setattr(ddm_gui, "MACROS_ROOT", tmp_path / "no-revit-macros")
    monkeypatch.setattr(ddm_gui, "USER_SETTINGS_PATH", tmp_path / "settings.json")
