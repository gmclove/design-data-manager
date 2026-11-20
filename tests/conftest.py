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


@pytest.fixture(autouse=True)
def features_on(monkeypatch):
    """Test every feature, whether or not this branch releases it (config.app_paths.FEATURES)."""
    from config.app_paths import FEATURES
    for name in FEATURES:
        monkeypatch.setitem(FEATURES, name, True)


@pytest.fixture
def linker_catalog():
    """An AHU primary (tag values and design data), its tag-only copy, a space and a family without
    the Linker ID, with Equipment Tag marked as a Linker Tag Set."""
    from revit_parameter_manager import LINKER_PARAMETER, Catalog
    catalog = Catalog()
    for name in (LINKER_PARAMETER, 'TAG', 'Seq', 'CFM', 'Space Name'):
        catalog.add_param(name, 'Text')
    catalog.set_code('category_1', 'Equipment', 'EQUIP')
    catalog.set_code('category_1', 'Space', 'SPACE')
    catalog.set_code('category_2', 'Air Handling Unit', 'AHU')
    catalog.add_family('AHU 2D', [LINKER_PARAMETER, 'TAG', 'Seq', 'CFM'], category='Detail Item',
                       category_1='Equipment', category_2='Air Handling Unit')
    # The 3D model element holds design-data parameters too, but only a Detail Item can be a primary.
    catalog.add_family('AHU 3D', [LINKER_PARAMETER, 'TAG', 'Seq', 'CFM'], category='Mechanical Equipment',
                       category_1='Equipment', category_2='Air Handling Unit')
    catalog.add_family('Space 2D', [LINKER_PARAMETER, 'Space Name', 'CFM'], category='Detail Item', category_1='Space')
    catalog.add_family('Odd 2D', [LINKER_PARAMETER, 'CFM'], category='Detail Item')
    # A generic box on a utility distribution diagram: a Detail Item with its own flow data, set to Linked.
    catalog.add_family('PFD Distribution 2D', [LINKER_PARAMETER, 'TAG', 'CFM'], category='Detail Item',
                       category_1='Equipment', linker_role='linked')
    catalog.add_family('Plain', ['TAG', 'CFM'])
    catalog.add_section('Equipment Tag', ['Seq', 'TAG'], linker_tag_set=True)
    catalog.add_section('Space Tag', ['Space Name'], linker_tag_set=True)
    catalog.add_section('Airflow', ['CFM'])
    return catalog
