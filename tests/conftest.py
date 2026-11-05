import time
import tkinter as tk

import pytest

import ddm_gui

_real_tk_init = tk.Tk.__init__


def _tk_init_with_retries(self, *args, **kwargs):
    """Retry Tk's startup: on the second machine it sometimes can't read its own script files.

    See Known issues in chat/plan.md. Only the startup is retried, so tests still fail on anything else.
    """
    for attempt in range(5):
        try:
            return _real_tk_init(self, *args, **kwargs)
        except tk.TclError:
            if attempt == 4:
                raise
            time.sleep(0.2)


tk.Tk.__init__ = _tk_init_with_retries


@pytest.fixture(autouse=True)
def no_real_macro_modules(tmp_path, monkeypatch):
    """Saving installs the schedule macro in the user's Revit macro module; never a real one in tests."""
    monkeypatch.setattr(ddm_gui, "MACROS_ROOT", tmp_path / "no-revit-macros")
    monkeypatch.setattr(ddm_gui, "USER_SETTINGS_PATH", tmp_path / "settings.json")
