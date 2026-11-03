import pytest

import ddm_gui


@pytest.fixture(autouse=True)
def no_real_macro_module(tmp_path, monkeypatch):
    """Saving installs the schedule macro into the Revit macro module; never the real one in tests."""
    monkeypatch.setattr(ddm_gui, "REVIT_MACRO_MODULE_DIR", tmp_path / "no-macro-module")
