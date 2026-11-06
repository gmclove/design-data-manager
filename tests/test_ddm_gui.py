import json
import pickle
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pandas as pd
import pytest

import config.app_paths as app_paths
import ddm_gui as gui_module
from revit_parameter_scheduler_export import generate_rfps_content
from config.app_paths import (
    DATA_DIR,
    DEMO_DATA_PATH,
    TEST_CHECKPOINT_PATH,
    TEST_DATABASE_CSV_PATH,
    get_database_output_paths,
)
from ddm_gui import DDMGUI, OverrideTable
from ddm_tables import catalog_from_tables
from revit_parameter_manager import Catalog
import revit_parameter_manager as model
from revit_shared_parameter_export import parameter_guid


class DummyText:
    def delete(self, *args, **kwargs):
        pass

    def insert(self, *args, **kwargs):
        pass

    def see(self, *args, **kwargs):
        pass


def make_test_tables():
    """The GUI test database as tables: params, families, links and schedule entries."""
    database_df = pd.read_csv(TEST_DATABASE_CSV_PATH, dtype=str, keep_default_na=False)
    params_df = database_df.loc[database_df["record_type"] == "parameter"].drop(
        columns="record_type"
    )
    params_df = params_df.reindex(columns=DDMGUI._table_columns["params"])
    params_df["instance_param"] = params_df["instance_param"].astype(str).str.upper().eq("TRUE")
    params_df["validation_message"] = params_df["validation_message"].fillna("").astype(str)

    extra_rows = [
        {
            "name": "HeadHeight",
            "dtype": "Length",
            "group_under": "Openings",
            "formula": "",
            "instance_param": True,
            "status": "Ready",
            "validation_message": "",
        },
        {
            "name": "GlassArea",
            "dtype": "Area",
            "group_under": "Envelope",
            "formula": "Width * Height",
            "instance_param": False,
            "status": "Ready",
            "validation_message": "",
        },
        {
            "name": "FacadeRatio",
            "dtype": "Number",
            "group_under": "Envelope",
            "formula": "GlassArea / GrossArea",
            "instance_param": False,
            "status": "Ready",
            "validation_message": "",
        },
        {
            "name": "FinishCode",
            "dtype": "Text",
            "group_under": "Finishes",
            "formula": "",
            "instance_param": True,
            "status": "Ready",
            "validation_message": "",
        },
        {
            "name": "PanelCount",
            "dtype": "Number",
            "group_under": "Quantities",
            "formula": "",
            "instance_param": False,
            "status": "Ready",
            "validation_message": "",
        },
        {
            "name": "PowerLoad",
            "dtype": "Number",
            "group_under": "Electrical",
            "formula": "",
            "instance_param": False,
            "status": "Ready",
            "validation_message": "",
        },
    ]
    existing_names = set(params_df["name"].astype(str))
    extra_rows = [row for row in extra_rows if row["name"] not in existing_names]
    params_df = pd.concat([params_df, pd.DataFrame(extra_rows)], ignore_index=True)

    families_df = pd.DataFrame(
        [
            {
                "name": "Family_A",
                "client": "Client A",
                "country": "USA",
                "category": "Doors",
                "description": "Main family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_B",
                "client": "Client B",
                "country": "Canada",
                "category": "Windows",
                "description": "Secondary family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_C",
                "client": "Client C",
                "country": "United Kingdom",
                "category": "Curtain Wall",
                "description": "Glazed facade family",
                "status": "Ready",
                "validation_message": "",
            },
            {
                "name": "Family_D",
                "client": "Client D",
                "country": "Germany",
                "category": "Casework",
                "description": "Custom cabinet family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_E",
                "client": "Client E",
                "country": "France",
                "category": "Railings",
                "description": "Stair guard family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_F",
                "client": "Client F",
                "country": "Spain",
                "category": "Structural Framing",
                "description": "Steel beam family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_G",
                "client": "Client G",
                "country": "Japan",
                "category": "Furniture",
                "description": "Modular joinery family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_H",
                "client": "Client H",
                "country": "Australia",
                "category": "Mechanical Equipment",
                "description": "Air handling unit family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_I",
                "client": "Client I",
                "country": "Sweden",
                "category": "Generic Models",
                "description": "Envelope panel family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_J",
                "client": "Client J",
                "country": "Norway",
                "category": "Openings",
                "description": "Vertical daylight opening family",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_K",
                "client": "Client K",
                "country": "Ireland",
                "category": "Doors",
                "description": "Rated service door",
                "status": "Draft",
                "validation_message": "",
            },
            {
                "name": "Family_L",
                "client": "Client L",
                "country": "Netherlands",
                "category": "Mechanical Equipment",
                "description": "Plant room equipment",
                "status": "Draft",
                "validation_message": "",
            },
        ]
    )
    family_param_links_df = pd.DataFrame(
        [
            {"family_name": "Family_A", "parameter_name": "Length"},
            {"family_name": "Family_A", "parameter_name": "Width"},
            {"family_name": "Family_A", "parameter_name": "Height"},
            {"family_name": "Family_A", "parameter_name": "Area"},
            {"family_name": "Family_A", "parameter_name": "Volume"},
            {"family_name": "Family_B", "parameter_name": "Length"},
            {"family_name": "Family_B", "parameter_name": "Width"},
            {"family_name": "Family_B", "parameter_name": "Height"},
            {"family_name": "Family_C", "parameter_name": "Length"},
            {"family_name": "Family_C", "parameter_name": "Width"},
            {"family_name": "Family_C", "parameter_name": "UValue"},
            {"family_name": "Family_C", "parameter_name": "ScreenRatio"},
            {"family_name": "Family_C", "parameter_name": "GlassArea"},
            {"family_name": "Family_D", "parameter_name": "Depth"},
            {"family_name": "Family_D", "parameter_name": "Width"},
            {"family_name": "Family_D", "parameter_name": "Quantity"},
            {"family_name": "Family_E", "parameter_name": "Height"},
            {"family_name": "Family_E", "parameter_name": "RValue"},
            {"family_name": "Family_E", "parameter_name": "FinishType"},
            {"family_name": "Family_F", "parameter_name": "Length"},
            {"family_name": "Family_F", "parameter_name": "Width"},
            {"family_name": "Family_F", "parameter_name": "GrossArea"},
            {"family_name": "Family_G", "parameter_name": "Depth"},
            {"family_name": "Family_G", "parameter_name": "FinishCode"},
            {"family_name": "Family_G", "parameter_name": "PanelCount"},
            {"family_name": "Family_H", "parameter_name": "Length"},
            {"family_name": "Family_H", "parameter_name": "Width"},
            {"family_name": "Family_H", "parameter_name": "PowerLoad"},
            {"family_name": "Family_I", "parameter_name": "GlassArea"},
            {"family_name": "Family_I", "parameter_name": "FacadeRatio"},
            {"family_name": "Family_I", "parameter_name": "FinishCode"},
            {"family_name": "Family_J", "parameter_name": "HeadHeight"},
            {"family_name": "Family_J", "parameter_name": "Width"},
            {"family_name": "Family_J", "parameter_name": "Openings"},
            {"family_name": "Family_K", "parameter_name": "ClearanceHeight"},
            {"family_name": "Family_K", "parameter_name": "FireRating"},
            {"family_name": "Family_L", "parameter_name": "ServiceClearance"},
            {"family_name": "Family_L", "parameter_name": "FireRating"},
        ]
    )

    entries_df = pd.DataFrame(
        [
            {
                "family_name": "Family_A",
                "group_name": "Schedule A",
                "parameter_name": "Length",
                "override_entry": "",
                "status": "Ready",
                "validation_message": "",
            },
            {
                "family_name": "Family_A",
                "group_name": "Schedule A",
                "parameter_name": "Width",
                "override_entry": "Override Width",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_B",
                "group_name": "Schedule B",
                "parameter_name": "Height",
                "override_entry": "",
                "status": "Ready",
                "validation_message": "",
            },
            {
                "family_name": "Family_C",
                "group_name": "Envelope Schedule",
                "parameter_name": "UValue",
                "override_entry": "0.21",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_C",
                "group_name": "Envelope Schedule",
                "parameter_name": "GlassArea",
                "override_entry": "14.8",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_D",
                "group_name": "Casework Schedule",
                "parameter_name": "Depth",
                "override_entry": "",
                "status": "Ready",
                "validation_message": "",
            },
            {
                "family_name": "Family_E",
                "group_name": "Guardrail Schedule",
                "parameter_name": "RValue",
                "override_entry": "",
                "status": "Ready",
                "validation_message": "",
            },
            {
                "family_name": "Family_F",
                "group_name": "Structural Schedule",
                "parameter_name": "GrossArea",
                "override_entry": "35.5",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_G",
                "group_name": "Joinery Schedule",
                "parameter_name": "FinishCode",
                "override_entry": "J-04",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_H",
                "group_name": "Mechanical Schedule",
                "parameter_name": "PowerLoad",
                "override_entry": "12.4",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_I",
                "group_name": "Facade Review",
                "parameter_name": "FacadeRatio",
                "override_entry": "0.62",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_J",
                "group_name": "Opening Schedule",
                "parameter_name": "HeadHeight",
                "override_entry": "2.4",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_K",
                "group_name": "Safety and Clearance",
                "parameter_name": "ClearanceHeight",
                "override_entry": "2.1 m",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_K",
                "group_name": "Safety and Clearance",
                "parameter_name": "FireRating",
                "override_entry": "90 min",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_L",
                "group_name": "Safety and Clearance",
                "parameter_name": "ServiceClearance",
                "override_entry": "600 mm",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
            {
                "family_name": "Family_L",
                "group_name": "Safety and Clearance",
                "parameter_name": "FireRating",
                "override_entry": "120 min",
                "status": "Ready",
                "validation_message": "Override entry recorded",
            },
        ]
    )
    return {
        "params": params_df,
        "families": families_df,
        "links": family_param_links_df,
        "entries": entries_df,
    }


def gui_from_tables(header_groups=None, **tables):
    """A GUI without a window, holding a catalog built from ``tables``."""
    gui = DDMGUI.__new__(DDMGUI)
    gui.warning_text = DummyText()
    gui.checkpoint_path = gui_module.DEFAULT_CHECKPOINT_PATH
    gui.param_tree = None
    gui.family_tree = None
    gui.group_tree = None
    gui.catalog, gui.load_issues = catalog_from_tables(header_groups=header_groups, **tables)
    gui.catalog.validate()
    return gui


def make_test_gui(header_groups=None, **changes):
    tables = make_test_tables()
    tables.update(changes)
    return gui_from_tables(header_groups=header_groups, **tables)


def row_index(frame, **match):
    mask = pd.Series(True, index=frame.index)
    for column, value in match.items():
        mask &= frame[column] == value
    return int(mask[mask].index[0])


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def find_window(root, title):
    return next(
        widget for widget in descendants(root)
        if isinstance(widget, tk.Toplevel) and widget.title() == title
    )


def find_button(window, text):
    return next(
        widget for widget in descendants(window)
        if isinstance(widget, ttk.Button) and widget.cget("text") == text
    )


# --- model ------------------------------------------------------------------

def test_schedule_name_is_required_and_unique():
    catalog = Catalog()

    first = catalog.add_schedule("Mechanical Schedule")
    assert first.name == "Mechanical Schedule"

    with pytest.raises(ValueError):
        catalog.add_schedule("Mechanical Schedule")
    with pytest.raises(ValueError):
        model.Schedule(name="   ")


def test_schedule_header_text_override_uses_parameter_default_and_round_trips():
    default_param = model.Param("Width", "Length")
    custom_param = model.Param("Height", "Length", header_text="Overall Height")
    family = model.Fam(name="Header Family", category="Doors", params=[default_param, custom_param])
    schedule = model.Schedule(name="Header Schedule", fams=[family])

    assert next(param.header_text for param in schedule.params if param.name == "Width") == "Width"
    assert next(param.header_text for param in schedule.params if param.name == "Height") == "Overall Height"
    assert schedule.override_param("Height", header_text="")
    assert next(param.header_text for param in schedule.params if param.name == "Height") == "Overall Height"
    assert schedule.override_param("Height", header_text="Schedule Height")
    assert next(param.header_text for param in schedule.params if param.name == "Height") == "Schedule Height"

    restored = model.Schedule.from_dict(schedule.to_dict())
    assert next(param.header_text for param in restored.params if param.name == "Height") == "Schedule Height"


def test_parameter_grid_column_width_can_be_overridden_per_schedule():
    width_param = model.Param("Width", "Length", grid_column_width=1.25)
    family = model.Fam(name="Width Family", category="Doors", params=[width_param])
    schedule = model.Schedule(name="Width Schedule", fams=[family])

    assert next(param.grid_column_width for param in schedule.params if param.name == "Width") == 1.25
    schedule.override_param("Width", grid_column_width=2.5)
    assert next(param.grid_column_width for param in schedule.params if param.name == "Width") == 2.5

    restored = model.Schedule.from_dict(schedule.to_dict())
    assert restored.grid_column_width_overrides == {"Width": 2.5}
    restored.override_param("Width", grid_column_width=None)
    assert next(param.grid_column_width for param in restored.params if param.name == "Width") == 1.25


def test_parameter_name_is_required_and_supplied_guid_is_preserved():
    parameter = model.Param("Width", "Length", guid="existing-guid")
    assert parameter.guid == "existing-guid"

    for name in (None, "", "   "):
        with pytest.raises(ValueError, match="(?i)name is required"):
            model.Param(name, "Text")

    with pytest.raises(ValueError, match="(?i)name is required"):
        parameter.name = "   "
    assert parameter.name == "Width"

    family = model.Fam(name="   ", params=[model.Param("Custom", "Text")])
    assert family.status == "Error"
    assert "name is required" in family.validation_message


def test_family_validation_rejects_duplicate_parameters():
    family = model.Fam(
        name="Duplicate Parameter Family",
        category="Doors",
        params=[model.Param("Width", "Length"), model.Param("Width", "Length")],
    )

    assert family.status == "Error"
    assert "Duplicate parameter(s)" in family.validation_message
    assert "Width" in family.validation_message


def test_schedule_contains_a_shared_parameter_only_once():
    family_a = model.Fam(name="Schedule Family A", category="Doors", params=[model.Param("Width", "Length")])
    family_b = model.Fam(
        name="Schedule Family B",
        category="Windows",
        params=[model.Param("Width", "Length"), model.Param("Height", "Length")],
    )

    schedule = model.Schedule(name="Unique Schedule Parameters", fams=[family_a, family_b])

    parameter_names = [param.name for param in schedule.params]
    assert parameter_names.count("Width") == 1
    assert parameter_names.count("Height") == 1


def test_schedule_header_groups_round_trip_with_parameter_references():
    family = model.Fam(
        name="Grouped Header Family",
        category="Doors",
        params=[model.Param("Width", "Length"), model.Param("Height", "Length"), model.Param("Depth", "Length")],
    )
    schedule = model.Schedule(name="Grouped Header Schedule", fams=[family])

    schedule.add_header_group("Size", ["Width", "Height"], top_row=0, bottom_row=0)
    restored = model.Schedule.from_dict(schedule.to_dict())

    assert restored.header_groups == [
        {"caption": "Size", "parameter_names": ["Width", "Height"], "top_row": 0, "bottom_row": 0}
    ]


def test_schedule_header_groups_reject_noncontiguous_parameters():
    family = model.Fam(
        name="Noncontiguous Header Family",
        category="Doors",
        params=[model.Param("Width", "Length"), model.Param("Height", "Length"), model.Param("Depth", "Length")],
    )
    schedule = model.Schedule(name="Noncontiguous Header Schedule", fams=[family])

    with pytest.raises(ValueError, match="(?i)contiguous"):
        schedule.add_header_group("Outer", ["Width", "Depth"])


# --- loading tables into the catalog ------------------------------------------

def test_loading_fixes_and_reports_invalid_records():
    tables = make_test_tables()
    params = tables["params"].copy()
    params["instance_param"] = params["instance_param"].astype(object)
    params["grid_column_width"] = params["grid_column_width"].astype(object)
    first, second, third = params["name"].iloc[:3]
    params.at[0, "instance_param"] = "sometimes"
    params.at[1, "grid_column_width"] = "wide"
    params.at[2, "name"] = ""
    families = tables["families"].copy()
    first_family, second_family = families["name"].iloc[:2]
    families.at[0, "category"] = "Not a Revit category"
    families.at[1, "name"] = ""

    gui = make_test_gui(params=params, families=families)

    issues = "\n".join(gui.load_issues)
    assert f"Parameter '{first}': Instance or Type must be Instance or Type" in issues
    assert gui.catalog.get_param(first).instance_param is True
    assert f"Parameter '{second}': Grid column width must be a number in inches." in issues
    assert gui.catalog.get_param(second).grid_column_width == 1.0
    assert "Parameter row 3 has no name; skipped." in issues
    assert gui.catalog.get_param(third) is None
    assert f"Family '{first_family}' has unknown category 'Not a Revit category'" in issues
    assert gui.catalog.get_family(first_family).category is None
    assert "Family row 2 has no name; skipped." in issues
    assert gui.catalog.get_family(second_family) is None


def test_loading_reports_links_to_unknown_parameters_and_duplicates():
    tables = make_test_tables()
    links = pd.concat(
        [tables["links"], pd.DataFrame([
            {"family_name": "Family_A", "parameter_name": "Length"},
            {"family_name": "Family_A", "parameter_name": "Ghost"},
        ])],
        ignore_index=True,
    )

    gui = make_test_gui(links=links)

    assert "Duplicate link 'Family_A' -> 'Length'; kept one." in gui.load_issues
    assert "Family 'Family_A' links unknown parameter 'Ghost'; skipped." in gui.load_issues
    family_a_links = gui.family_param_links_df.query("family_name == 'Family_A'")["parameter_name"].tolist()
    assert family_a_links.count("Length") == 1


def test_loaded_guid_defaults_to_name_based_export_guid():
    gui = make_test_gui()

    for _, row in gui.params_df.iterrows():
        assert row["guid"] == parameter_guid(row["name"])


# --- validation -------------------------------------------------------------

def test_validation_flags_missing_references():
    gui = make_test_gui()
    gui.validate_all()

    missing_ref_row = gui.params_df[gui.params_df["name"] == "MissingRef"].iloc[0]
    assert str(missing_ref_row["status"]).lower() == "error"
    assert "GhostParam" in str(missing_ref_row["validation_message"])


def test_family_validation_accepts_associated_params():
    gui = make_test_gui()
    gui.validate_all()

    family_a = gui.families_df[gui.families_df["name"] == "Family_A"].iloc[0]
    assert str(family_a["status"]).lower() == "ready"
    assert str(family_a["validation_message"]).strip() == ""


def test_family_validation_detects_missing_link():
    tables = make_test_tables()
    gui = make_test_gui(links=tables["links"][tables["links"]["family_name"] != "Family_A"])
    gui.validate_all()

    family_a = gui.families_df[gui.families_df["name"] == "Family_A"].iloc[0]
    assert str(family_a["status"]).lower() == "warning"  # flagged, but not an error: imported families start unlinked


def test_sync_is_blocked_when_validation_errors_exist(monkeypatch):
    gui = make_test_gui()
    warning_calls = []

    def fail_if_sync_starts(*args, **kwargs):
        raise AssertionError("Quickbase client should not be created for invalid data")

    monkeypatch.setattr(gui_module.os, "getenv", lambda key, default=None: {
        "QB_APP_ID": "test-app",
        "QB_USER_TOKEN": "test-token",
    }.get(key, default))
    monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda *args, **kwargs: warning_calls.append(args))
    monkeypatch.setattr(gui_module, "QuickbaseClient", fail_if_sync_starts)
    monkeypatch.setattr(gui_module, "QuickbaseSyncService", fail_if_sync_starts)

    gui.sync_to_quickbase()

    assert warning_calls
    assert warning_calls[0][0] == "Validation failed"


# --- editing ----------------------------------------------------------------

def test_gui_cell_edit_updates_the_model():
    gui = make_test_gui()
    name = gui.catalog.params[0].name
    gui._apply_cell_value("params", 0, "formula", "Width + Height")

    assert gui.catalog.get_param(name).formula == "Width + Height"
    assert gui.params_df.at[0, "formula"] == "Width + Height"


def test_gui_rejects_invalid_width_and_defaults_blank_width():
    gui = make_test_gui()
    original_width = gui.params_df.at[0, "grid_column_width"]

    for invalid_width in ("wide", "-1", "0", "inf"):
        with pytest.raises(ValueError):
            gui._apply_cell_value("params", 0, "grid_column_width", invalid_width)
        assert gui.params_df.at[0, "grid_column_width"] == original_width

    gui._apply_cell_value("params", 0, "grid_column_width", "2.5")
    assert gui.params_df.at[0, "grid_column_width"] == 2.5
    gui._apply_cell_value("params", 0, "grid_column_width", "")
    assert gui.params_df.at[0, "grid_column_width"] == gui._default_grid_column_width_in == 1.0
    assert DDMGUI._display_labels["grid_column_width"] == "Default Column Width (in)"


def test_gui_rejects_invalid_boolean_and_validation_owned_fields():
    gui = make_test_gui()

    with pytest.raises(ValueError, match="Instance or Type must be Instance or Type"):
        gui._apply_cell_value("params", 0, "instance_param", "sometimes")

    for column_name in ("status", "validation_message"):
        with pytest.raises(ValueError, match="(?i)generated by validation"):
            gui._apply_cell_value("params", 0, column_name, "Ready")


def test_gui_rejects_unknown_data_type_category_and_blank_family_name():
    gui = make_test_gui()

    with pytest.raises(ValueError, match="Unknown dtype"):
        gui._apply_cell_value("params", 0, "dtype", "Not a type")
    with pytest.raises(ValueError, match="Unknown family category"):
        gui._apply_cell_value("families", 0, "category", "Not a category")
    with pytest.raises(ValueError, match="Family name is required"):
        gui._apply_cell_value("families", 0, "name", "  ")


def test_gui_rename_prompts_and_assigns_new_guid_or_keeps_current(monkeypatch):
    gui = make_test_gui()
    original_name = gui.params_df.at[0, "name"]
    original_guid = gui.params_df.at[0, "guid"]
    prompts = []
    answers = iter([None, False, True])

    def answer(title, message, **kwargs):
        prompts.append(message)
        return next(answers)

    monkeypatch.setattr(gui_module.messagebox, "askyesnocancel", answer)

    gui._apply_cell_value("params", 0, "name", "Cancelled")
    assert gui.params_df.at[0, "name"] == original_name
    assert gui.params_df.at[0, "guid"] == original_guid
    assert f"'{original_name}' to 'Cancelled'" in prompts[0]

    gui._apply_cell_value("params", 0, "name", "KeptGuid")
    assert gui.params_df.at[0, "name"] == "KeptGuid"
    assert gui.params_df.at[0, "guid"] == original_guid

    gui._apply_cell_value("params", 0, "name", "NewGuid")
    assert gui.params_df.at[0, "name"] == "NewGuid"
    assert gui.params_df.at[0, "guid"] not in {original_guid, parameter_guid("NewGuid")}

    with pytest.raises(ValueError, match="assigned automatically"):
        gui._apply_cell_value("params", 0, "guid", "hand-typed")


def test_gui_rename_updates_every_reference_to_the_parameter(monkeypatch):
    gui = gui_from_tables(
        params=pd.DataFrame([
            {"name": "Width", "header_text": "Width", "dtype": "Length", "formula": "", "instance_param": True},
            {"name": "Height", "header_text": "Clear Height", "dtype": "Length", "formula": "", "instance_param": True},
            {"name": "GlassWidth", "header_text": "GlassWidth", "dtype": "Length", "formula": "", "instance_param": True},
            {"name": "Area", "header_text": "Area", "dtype": "Area", "formula": "Width * Height + GlassWidth", "instance_param": True},
        ]),
        families=pd.DataFrame([{"name": "Family_A", "category": "Doors"}]),
        links=pd.DataFrame([
            {"family_name": "Family_A", "parameter_name": name}
            for name in ("Width", "Height", "GlassWidth", "Area")
        ]),
        entries=pd.DataFrame([
            {"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Width",
             "header_text_override": "W", "override_entry": "3"},
            {"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Height"},
        ]),
        header_groups={
            "Schedule A": [{"caption": "Size", "parameter_names": ["Height", "Width"], "top_row": 0, "bottom_row": 0}]
        },
    )
    monkeypatch.setattr(gui_module.messagebox, "askyesnocancel", lambda *args, **kwargs: False)

    gui._apply_cell_value("params", 0, "name", "Rough Width")

    params = gui.params_df.set_index("name")
    assert params.at["Rough Width", "header_text"] == "Rough Width"
    assert params.at["Area", "formula"] == "Rough Width * Height + GlassWidth"
    assert "Rough Width" in gui.family_param_links_df["parameter_name"].tolist()
    entry = gui.family_groups_df.set_index("parameter_name").loc["Rough Width"]
    assert entry["header_text_override"] == "W"
    assert entry["override_entry"] == "3"
    assert gui.schedule_header_groups["Schedule A"][0]["parameter_names"] == ["Rough Width", "Height"]  # schedule column order

    gui._apply_cell_value("params", 1, "name", "Tall")
    assert gui.params_df.set_index("name").at["Tall", "header_text"] == "Clear Height"

    with pytest.raises(ValueError, match="already in use"):
        gui._apply_cell_value("params", 1, "name", "GlassWidth")
    with pytest.raises(ValueError, match="already in use"):
        gui._apply_cell_value("params", 1, "name", "IPS_GROUP_Schedule_Name")
    assert gui.params_df.at[1, "name"] == "Tall"


# --- value overrides ----------------------------------------------------------

def answering(answer, asked=None):
    """A stand-in for the override prompt: picks the connected labels in ``answer["pick"]``."""
    def ask(param_name, value, location, connected, ask_parameter, attribute="value"):
        if asked is not None:
            asked.append((param_name, value, location, [label for _location, label in connected], ask_parameter))
        if answer is None:
            return None
        return {
            "locations": [where for where, label in connected if label in answer.get("pick", ())],
            "parameter": answer.get("parameter", False),
        }
    return ask


def three_family_gui():
    """F1 and F2 in S1 and S2; F3 only in S1; all three have Width."""
    return gui_from_tables(
        params=pd.DataFrame([{"name": "Width", "dtype": "Length", "instance_param": True, "default_value": "1"}]),
        families=pd.DataFrame([{"name": name, "category": "Doors"} for name in ("F1", "F2", "F3")]),
        links=pd.DataFrame([{"family_name": name, "parameter_name": "Width"} for name in ("F1", "F2", "F3")]),
        entries=pd.DataFrame([
            {"family_name": family, "group_name": schedule, "parameter_name": "Width"}
            for family, schedule in (("F1", "S1"), ("F2", "S1"), ("F3", "S1"), ("F1", "S2"), ("F2", "S2"))
        ]),
    )


def test_schedule_override_offers_the_other_families_in_the_schedule(monkeypatch):
    gui = three_family_gui()
    asked = []
    monkeypatch.setattr(gui, "_ask_override_scope", answering({"pick": ["F3"]}, asked))

    assert gui._override_value(("F1", "S1"), "Width", "7") is True

    assert asked == [("Width", "7", ("F1", "S1"), ["F2", "F3"], True)]
    catalog = gui.catalog
    assert catalog.resolved_value(("F1", "S1"), "Width") == "7"
    assert catalog.resolved_value(("F3", "S1"), "Width") == "7"
    assert catalog.resolved_value(("F2", "S1"), "Width") == "1"
    assert catalog.resolved_value(("F1", "S2"), "Width") == "1"
    assert catalog.get_param("Width").value == "1"
    entries = gui.family_groups_df.set_index(["group_name", "family_name"])
    assert entries.at[("S1", "F3"), "override_entry"] == "7"
    assert entries.at[("S1", "F2"), "override_entry"] == ""


def test_family_override_offers_the_familys_schedules(monkeypatch):
    gui = three_family_gui()
    asked = []
    monkeypatch.setattr(gui, "_ask_override_scope", answering({}, asked))
    gui._override_value(("F1", "S2"), "Width", "9")

    monkeypatch.setattr(gui, "_ask_override_scope", answering({"pick": ["S2"]}, asked))
    gui._override_value(("F1", None), "Width", "5")

    assert asked[1] == ("Width", "5", ("F1", None), ["S1", "S2"], True)
    assert gui.catalog.get_family("F1").overrides == {"Width": {"value": "5"}}
    assert gui.catalog.resolved_value(("F1", "S1"), "Width") == "5"
    # S2 had its own override; picking it replaces that with the new value.
    assert gui.catalog.resolved_value(("F1", "S2"), "Width") == "5"


def test_override_can_become_the_parameter_default(monkeypatch):
    gui = three_family_gui()
    monkeypatch.setattr(gui, "_ask_override_scope", answering({"parameter": True}))

    gui._override_value(("F1", "S1"), "Width", "7")

    assert gui.catalog.get_param("Width").value == "7"
    assert gui.catalog.resolved_value(("F2", "S2"), "Width") == "7"
    assert gui.params_df.set_index("name").at["Width", "default_value"] == "7"


def test_clearing_an_override_clears_the_picked_locations(monkeypatch):
    gui = three_family_gui()
    monkeypatch.setattr(gui, "_ask_override_scope", answering({"pick": ["F2"]}))
    gui._override_value(("F1", "S1"), "Width", "7")

    gui._override_value(("F1", "S1"), "Width", "")

    assert gui.catalog.resolved_value(("F1", "S1"), "Width") == "1"
    assert gui.catalog.resolved_value(("F2", "S1"), "Width") == "1"
    assert gui.catalog.get_schedule("S1").family_overrides == {}


def test_cancelling_the_override_prompt_changes_nothing(monkeypatch):
    gui = three_family_gui()
    monkeypatch.setattr(gui, "_ask_override_scope", answering(None))

    assert gui._override_value(("F1", "S1"), "Width", "7") is False
    assert gui.catalog.resolved_value(("F1", "S1"), "Width") == "1"


def test_override_with_nothing_to_ask_does_not_prompt(monkeypatch):
    gui = gui_from_tables(families=pd.DataFrame([{"name": "F1", "category": "Doors"}]))
    monkeypatch.setattr(gui, "_ask_override_scope", lambda *args: pytest.fail("should not prompt"))

    gui._override_value(("F1", None), "IPS_GROUP_Schedule_Name", "Lobby")

    assert gui.catalog.resolved_value(("F1", None), "IPS_GROUP_Schedule_Name") == "Lobby"


def test_override_question_wording():
    gui = three_family_gui()

    heading, list_label, parameter = gui._override_questions("Width", "7", ("F1", "S1"))
    assert heading == "Override Schedule Default Value\nS1: F1\nWidth = 7"
    assert list_label == "Override Schedule Default Value for These Families?"
    assert parameter == "Override Parameter Default Value?\nWidth = 7"

    heading, list_label, parameter = gui._override_questions("Width", None, ("F1", None))
    assert heading == "Clear Family Default Value\nF1\nWidth = (no value)"
    assert list_label == "Clear Schedule Default Value in These Schedules?"
    assert parameter == "Clear Parameter Default Value?\nWidth = (no value)"


def cells(rows, label, section=None):
    """``(text, state, editable)`` for each cell of the row with ``label`` (in ``section``)."""
    current = None
    for row in rows:
        current = row["section"] or current
        if row["label"] == label and (section is None or current == section):
            return [(cell["text"], cell["state"], cell["editable"]) for cell in row["cells"]]
    raise AssertionError(f"No row {label!r} in {section!r}")


def test_schedule_table_shows_each_level_and_where_values_come_from(monkeypatch):
    gui = three_family_gui()
    monkeypatch.setattr(gui, "_ask_override_scope", answering({}))
    gui._override_value(("F1", None), "Width", "5")
    gui._override_value(("F2", "S1"), "Width", "9")
    gui._override_value(("F3", None), "Width", "Height * 2", "formula")

    rows = gui._schedule_table_rows(gui.catalog.get_schedule("S1"))

    assert [row["section"] for row in rows if row["section"]] == ["Parameter", "Apply to All Families", "F1", "F2", "F3"]
    assert cells(rows, "Name", "Parameter") == [("Width", "set", True)]
    # The Default Header is the parameter's own; gray when it's just the name.
    assert cells(rows, "Default Header", "Parameter") == [("Width", "inherited", True)]
    gui.catalog.get_param("Width").header_text = "WIDTH (IN)"
    assert cells(gui._schedule_table_rows(gui.catalog.get_schedule("S1")), "Default Header", "Parameter") == [
        ("WIDTH (IN)", "set", True)]
    assert "Default Header" not in [row["label"] for row in gui._family_window_rows(gui.catalog.get_family("F1"))]
    assert cells(rows, "Default Value", "Parameter") == [("1", "set", True)]
    assert cells(rows, "Default Value", "Apply to All Families") == [("(Varies)", "inherited", True)]
    assert cells(rows, "Default Value", "F1") == [("5", "inherited", True)]
    assert cells(rows, "Default Value", "F2") == [("9", "set", True)]
    assert cells(rows, "Default Value", "F3") == [("1", "inherited", True)]
    # Formula and group under belong to the family; in a schedule they set the family's own.
    assert cells(rows, "Default Formula", "F3") == [("Height * 2", "set", True)]
    assert cells(rows, "Default Group Under", "F3") == [("", "inherited", True)]

    # Bold marks the value the schedule uses: F1's own (family) and F2's schedule value; F3 uses
    # the parameter's, so the Parameter cell is bold too.
    def bold(label, section):
        current = None
        for row in rows:
            current = row["section"] or current
            if row["label"] == label and current == section:
                return [cell.get("bold", False) for cell in row["cells"]]

    assert [bold("Default Value", section) for section in ("F1", "F2", "F3")] == [[True], [True], [False]]
    assert bold("Default Value", "Parameter") == [True]
    assert bold("Default Value", "Apply to All Families") == [False]
    assert bold("Default Formula", "F3") == [True] and bold("Default Formula", "Parameter") == [True]
    assert bold("Default Header", "Parameter") == [True]
    gui._override_value(("F3", "S1"), "Width", "4")
    rows = gui._schedule_table_rows(gui.catalog.get_schedule("S1"))
    assert bold("Default Value", "Parameter") == [False]  # every family now sets its own


def test_all_families_row_sets_every_familys_schedule_value_at_once(monkeypatch):
    gui = three_family_gui()
    asked = []
    monkeypatch.setattr(gui, "_ask_override_scope", answering({}, asked))
    schedule = gui.catalog.get_schedule("S1")

    assert cells(gui._schedule_table_rows(schedule), "Default Value", "Apply to All Families") == [("", "inherited", True)]

    assert gui._override_all_families("S1", "Width", "7") is True

    assert asked == [("Width", "7", ("All Families", "S1"), [], True)]
    for family in ("F1", "F2", "F3"):
        assert gui.catalog.resolved_value((family, "S1"), "Width") == "7"
    assert gui.catalog.resolved_value(("F1", "S2"), "Width") == "1"
    assert cells(gui._schedule_table_rows(schedule), "Default Value", "Apply to All Families") == [("7", "set", True)]

    gui._override_value(("F2", "S1"), "Width", "9")
    assert cells(gui._schedule_table_rows(schedule), "Default Value", "Apply to All Families") == [("(Varies)", "inherited", True)]

    gui._override_all_families("S1", "Width", "")
    assert schedule.family_overrides == {}

    heading, _list_label, _parameter = gui._override_questions("Width", "7", ("All Families", "S1"))
    assert heading == "Override Schedule Default Value\nS1: All Families\nWidth = 7"


def test_all_families_formula_and_group_under_set_each_familys_family_default(monkeypatch):
    gui = three_family_gui()
    asked = []
    monkeypatch.setattr(gui, "_ask_override_scope", answering({}, asked))
    schedule = gui.catalog.get_schedule("S1")
    rows = gui._schedule_table_rows(schedule)
    assert [row["label"] for row in rows if row.get("all_families")] == [
        "Default Value", "Default Formula", "Default Group Under", "Instance or Type",
    ]
    assert cells(rows, "Default Formula", "Apply to All Families") == [("", "inherited", True)]

    assert gui._override_all_families("S1", "Width", "Height * 2", "formula") is True
    assert asked == [("Width", "Height * 2", ("All Families", "S1"), [], True)]
    # It's each family's own formula, so F1 and F2 have it in S2 too; nothing is schedule-level.
    for family in ("F1", "F2", "F3"):
        assert gui.catalog.get_family(family).overrides["Width"]["formula"] == "Height * 2"
    assert schedule.family_overrides == {}
    rows = gui._schedule_table_rows(schedule)
    assert cells(rows, "Default Formula", "Apply to All Families") == [("Height * 2", "set", True)]
    assert cells(rows, "Default Formula", "F1") == [("Height * 2", "set", True)]
    assert cells(gui._schedule_table_rows(gui.catalog.get_schedule("S2")), "Default Formula", "F2") == [
        ("Height * 2", "set", True)]

    gui._override_value(("F2", None), "Width", "Dimensions", "group_under")
    gui._override_all_families("S1", "Width", "Dimensions", "group_under")
    assert cells(gui._schedule_table_rows(schedule), "Default Group Under", "Apply to All Families") == [("Dimensions", "set", True)]
    gui._override_value(("F3", None), "Width", "Data", "group_under")
    assert cells(gui._schedule_table_rows(schedule), "Default Group Under", "Apply to All Families") == [("(Varies)", "inherited", True)]

    gui._override_all_families("S1", "Width", "", "formula")
    assert all("formula" not in gui.catalog.get_family(f).overrides.get("Width", {}) for f in ("F1", "F2", "F3"))

    heading, _list_label, parameter = gui._override_questions("Width", "Height * 2", ("All Families", "S1"), "formula")
    assert heading == (
        "Override Family Default Formula\nEvery Family in S1 (in Every Schedule They're In)\nWidth = Height * 2"
    )
    assert parameter == "Override Parameter Default Formula?\nWidth = Height * 2"


def test_instance_or_type_is_set_per_family_from_the_schedule_and_reaches_the_exports(tmp_path, monkeypatch):
    gui = three_family_gui()
    asked = []
    monkeypatch.setattr(gui, "_ask_override_scope", answering({}, asked))
    schedule = gui.catalog.get_schedule("S1")
    rows = gui._schedule_table_rows(schedule)
    # The parameter is Instance; each family inherits it, and can change it from the schedule.
    assert cells(rows, "Instance or Type", "Parameter") == [("Instance", "set", True)]
    assert cells(rows, "Instance or Type", "F1") == [("Instance", "inherited", True)]

    # F1's row sets F1 itself (every schedule it's in), not just this schedule.
    row = next(i for i, r in enumerate(rows) if r.get("family") == "F1" and r["attribute"] == "instance_param")
    table = SimpleNamespace(rows=rows, parameter_names=["Width"], winfo_toplevel=lambda: None)
    edits = {}

    def start_cell_edit(row_index, column_index, value, on_commit, placeholder="", choices=None, on_tab=None):
        edits.update(value=value, choices=choices, placeholder=placeholder)
        on_commit("Type")

    table.start_cell_edit = start_cell_edit
    table.set_rows = lambda new_rows: None
    gui._edit_table_cell(table, lambda: gui._schedule_table_rows(schedule), "S1", row, 0)
    assert edits == {"value": "", "choices": ["Instance", "Type"], "placeholder": "Blank Uses Parameter Instance or Type"}
    assert gui.catalog.get_family("F1").overrides["Width"] == {"instance_param": False}
    assert schedule.family_overrides == {}
    rows = gui._schedule_table_rows(schedule)
    assert cells(rows, "Instance or Type", "F1") == [("Type", "set", True)]
    assert cells(rows, "Instance or Type", "Apply to All Families") == [("(Varies)", "inherited", True)]
    assert asked[-1] == ("Width", False, ("F1", None), [], True)
    heading, _list, _parameter = gui._override_questions("Width", False, ("F1", None), "instance_param")
    assert heading == "Override Family Instance or Type\nF1\nWidth = Type"

    # Apply to All Families sets every family; clearing doesn't offer to clear the parameter's.
    gui._override_all_families("S1", "Width", "Type", "instance_param")
    assert cells(gui._schedule_table_rows(schedule), "Instance or Type", "Apply to All Families") == [
        ("Type", "set", True)]
    asked.clear()
    gui._override_all_families("S1", "Width", "", "instance_param")
    assert asked == [] and all(not gui.catalog.get_family(f).overrides for f in ("F1", "F2", "F3"))
    with pytest.raises(ValueError, match="Instance or Type must be"):
        gui._override_value(("F1", None), "Width", "Sometimes", "instance_param")

    # A family's own settings survive the CSV and reach the RF Tools export.
    gui._override_value(("F2", None), "Width", "Type", "instance_param")
    gui._override_value(("F2", None), "Width", "Width * 2", "formula")
    rfps = generate_rfps_content(gui.families_df, gui.family_param_links_df, gui.params_df)
    lines = {line.split("\t")[0]: line.split("\t") for line in rfps.splitlines()[1:]}
    header = rfps.splitlines()[0].split("\t")
    f1, f2 = lines["F1"], lines["F2"]
    assert (f1[header.index("InstanceOrType")], f2[header.index("InstanceOrType")]) == ("Instance", "Type")
    assert (f1[header.index("Formula")], f2[header.index("Formula")]) == ("", "Width * 2")
    gui.checkpoint_path = tmp_path / "database.ddm.json"
    gui.save_checkpoint()
    loaded = make_test_gui()
    loaded.load_checkpoint(str(tmp_path / "database.ddm.csv"))
    assert loaded.catalog.get_family("F2").overrides["Width"] == {"instance_param": False, "formula": "Width * 2"}


def fake_table(rows, parameter_names):
    """Stands in for an ``OverrideTable``: committing an edit types ``table.typed``."""
    table = SimpleNamespace(rows=rows, parameter_names=parameter_names, winfo_toplevel=lambda: None, edits=[])

    def start_cell_edit(row_index, column_index, value, on_commit, placeholder="", choices=None, on_tab=None):
        table.edits.append({"value": value, "choices": choices, "placeholder": placeholder})
        on_commit(table.typed)

    table.start_cell_edit = start_cell_edit
    table.set_rows = lambda new_rows: setattr(table, "rows", new_rows)
    return table


def test_schedule_window_parameter_section_edits_the_parameter_itself(monkeypatch):
    gui = three_family_gui()
    schedule = gui.catalog.get_schedule("S1")
    param = gui.catalog.get_param("Width")
    rows_builder = lambda: gui._schedule_table_rows(schedule)  # noqa: E731
    rows = rows_builder()
    for label in ("Name", "Default Header", "Default Value", "Default Formula", "Default Group Under", "Instance or Type"):
        assert cells(rows, label, "Parameter")[0][2] is True, label
    # The family window's Parameter section stays read-only.
    family_rows = gui._family_window_rows(gui.catalog.get_family("F1"))
    assert not any(cell["editable"] for row in family_rows if row.get("param_field") for cell in row["cells"])

    changed = []

    def edit(label, typed):
        table = fake_table(rows_builder(), ["Width"])
        table.typed = typed
        row = next(i for i, r in enumerate(table.rows) if r["label"] == label and r.get("param_field"))
        gui._edit_table_cell(table, rows_builder, "S1", row, 0, on_columns_changed=lambda: changed.append(label))
        return table.edits[-1]

    assert edit("Default Value", "4")["placeholder"] == "Sets the Parameter for Every Family and Schedule"
    assert param.value == "4"
    assert gui.catalog.resolved_value(("F1", "S2"), "Width") == "4"  # every schedule
    assert edit("Instance or Type", "Type")["choices"] == ["Instance", "Type"]
    assert param.instance_param is False
    edit("Default Group Under", "Dimensions")
    edit("Default Formula", "Height * 2")
    assert (param.group_under, param.formula) == ("Dimensions", "Height * 2")
    assert changed == []  # the table refreshes in place

    # The header and name redraw the column headers, so the window reopens.
    assert edit("Default Header", "WIDTH")["value"] == ""
    assert param.header_text == "WIDTH"
    monkeypatch.setattr(gui, "_confirm_param_rename", lambda old, new: True)
    assert edit("Name", "Breite")["value"] == "Width"
    assert gui.catalog.get_param("Breite") is param
    assert changed == ["Default Header", "Name"]

    errors = []
    monkeypatch.setattr(gui_module.messagebox, "showerror", lambda title, message, **_kw: errors.append(message))
    table = fake_table(rows_builder(), ["Breite"])
    table.typed = ""
    row = next(i for i, r in enumerate(table.rows) if r["label"] == "Instance or Type" and r.get("param_field"))
    gui._edit_table_cell(table, rows_builder, "S1", row, 0)
    assert errors == ["A parameter is always Instance or Type; pick one."] and param.instance_param is False


def test_all_families_row_can_also_set_the_parameter_default_or_cancel(monkeypatch):
    gui = three_family_gui()
    monkeypatch.setattr(gui, "_ask_override_scope", answering(None))
    assert gui._override_all_families("S1", "Width", "7") is False
    assert gui.catalog.get_schedule("S1").family_overrides == {}

    monkeypatch.setattr(gui, "_ask_override_scope", answering({"parameter": True}))
    gui._override_all_families("S1", "Width", "7")
    assert gui.catalog.get_param("Width").value == "7"


def test_family_table_edits_family_level_and_shades_missing_columns(monkeypatch):
    gui = gui_from_tables(
        params=pd.DataFrame([
            {"name": "Width", "dtype": "Length", "instance_param": True, "default_value": "1", "group_under": "Dimensions"},
            {"name": "Height", "dtype": "Length", "instance_param": True},
        ]),
        families=pd.DataFrame([{"name": "F1", "category": "Doors"}]),
        links=pd.DataFrame([
            {"family_name": "F1", "parameter_name": "Width"},
            {"family_name": "F1", "parameter_name": "Height"},
        ]),
    )
    monkeypatch.setattr(gui, "_ask_override_scope", answering({}))
    gui._override_value(("F1", None), "Height", "Construction", "group_under")

    rows = gui._family_window_rows(gui.catalog.get_family("F1"))

    assert cells(rows, "Default Group Under", "Parameter") == [("Dimensions", "set", False), ("", "set", False)]
    assert cells(rows, "Default Group Under", "F1") == [("Dimensions", "inherited", True), ("Construction", "set", True)]
    assert cells(rows, "Default Value", "F1") == [("1", "inherited", True), ("", "inherited", True)]

    schedule_rows = gui._schedule_table_rows(gui.catalog.add_schedule("S", ["F1"], field_names=["Width", "Ghost"]))
    assert cells(schedule_rows, "Default Value", "F1") == [("1", "inherited", True)]


def test_formula_override_offers_only_the_parameter_default(monkeypatch):
    gui = three_family_gui()
    asked = []
    monkeypatch.setattr(gui, "_ask_override_scope", answering({"parameter": True}, asked))

    gui._override_value(("F1", None), "Width", "Height * 2", "formula")

    assert asked == [("Width", "Height * 2", ("F1", None), [], True)]
    assert gui.catalog.get_family("F1").overrides == {"Width": {"formula": "Height * 2"}}
    assert gui.catalog.get_param("Width").formula == "Height * 2"


def test_override_question_wording_for_formula_and_group_under():
    gui = three_family_gui()

    heading, _list_label, parameter = gui._override_questions("Width", "Height * 2", ("F1", None), "formula")
    assert heading == "Override Family Default Formula\nF1\nWidth = Height * 2"
    assert parameter == "Override Parameter Default Formula?\nWidth = Height * 2"

    heading, _list_label, parameter = gui._override_questions("Width", None, ("F1", None), "group_under")
    assert heading == "Clear Family Default Group Under\nF1\nWidth Group Under = (no value)"
    assert parameter == "Clear Parameter Default Group Under?\nWidth Group Under = (no value)"


def run_in_dialog(root, action):
    """Run ``action`` once a modal dialog is open; close every dialog if it fails, so the test can't hang."""
    failures = []

    def run():
        try:
            action()
        except Exception as exc:
            failures.append(exc)
            for widget in descendants(root):
                if isinstance(widget, tk.Toplevel):
                    widget.destroy()

    root.after(50, run)
    return failures


def test_override_dialog_returns_picked_locations_and_parameter_choice():
    root = tk.Tk()
    root.withdraw()
    try:
        gui = three_family_gui()
        gui.root = root
        connected = gui._connected_override_locations(("F1", "S1"), "Width")
        shown = {}

        def pick_second_and_tick_parameter():
            dialog = find_window(root, "Override Default Value")
            listbox = next(widget for widget in descendants(dialog) if isinstance(widget, tk.Listbox))
            shown["listed"] = list(listbox.get(0, tk.END))
            listbox.selection_set(1)
            checkbox = next(widget for widget in descendants(dialog) if isinstance(widget, ttk.Checkbutton))
            shown["checkbox"] = checkbox.cget("text")
            checkbox.invoke()
            find_button(dialog, "Apply").invoke()

        failures = run_in_dialog(root, pick_second_and_tick_parameter)
        answer = gui._ask_override_scope("Width", "7", ("F1", "S1"), connected, True)
        assert not failures
        assert shown == {"listed": ["F2", "F3"], "checkbox": "Override Parameter Default Value?\nWidth = 7"}
        assert answer == {"locations": [("F3", "S1")], "parameter": True}

        failures = run_in_dialog(root, lambda: find_button(find_window(root, "Override Default Value"), "Cancel").invoke())
        assert gui._ask_override_scope("Width", "7", ("F1", "S1"), connected, True) is None
        assert not failures
    finally:
        root.destroy()


# --- schedules ----------------------------------------------------------------

def test_schedule_header_override_applies_to_the_schedule_column():
    gui = make_test_gui()

    gui._set_schedule_column("Safety and Clearance", "FireRating", "Fire Rating (min)", "")

    rows = gui.family_groups_df.query("group_name == 'Safety and Clearance' and parameter_name == 'FireRating'")
    assert rows["header_text_override"].tolist() == ["Fire Rating (min)", "Fire Rating (min)"]


def test_schedule_header_display_prefers_override_to_parameter_default():
    gui = make_test_gui()
    length_index = row_index(gui.params_df, name="Length")
    gui._apply_cell_value("params", length_index, "header_text", "Linear Dimension")
    schedule = gui.catalog.get_schedule("Schedule A")

    assert gui._get_schedule_header_text(schedule, "Length") == "Linear Dimension"
    gui._set_schedule_column("Schedule A", "Length", "Schedule Length", "")
    assert gui._get_schedule_header_text(schedule, "Length") == "Schedule Length"


def test_gui_schedule_width_override_uses_and_resets_to_parameter_default():
    gui = make_test_gui()
    schedule = gui.catalog.get_schedule("Schedule A")

    gui._set_schedule_column("Schedule A", "Width", "", "2.25")
    assert schedule.grid_column_width_overrides == {"Width": 2.25}
    assert gui._get_schedule_grid_column_width(schedule, "Width") == 2.25

    with pytest.raises(ValueError, match="positive number"):
        gui._set_schedule_column("Schedule A", "Width", "", "-3")

    gui._set_schedule_column("Schedule A", "Width", "", "")
    assert gui._get_schedule_grid_column_width(schedule, "Width") == 1.0


def test_gui_registers_header_group_on_schedule():
    gui = make_test_gui()

    group = gui._add_schedule_header_group("Schedule A", ["Length", "Width"], "Dimensions")

    assert group["caption"] == "Dimensions"
    assert group["parameter_names"] == ["Length", "Width"]
    assert gui.schedule_header_groups["Schedule A"] == [group]
    assert gui.catalog.get_schedule("Schedule A").header_groups == [group]


def test_schedule_summary_uses_single_value_columns_only():
    gui = make_test_gui()
    summary = gui._build_schedule_summary_df()

    assert list(summary.columns) == ["name", "family_count", "parameter_count", "status", "validation_message"]
    assert "Schedule A" in summary["name"].tolist()


def test_schedule_columns_are_sorted_when_loaded_from_entries():
    gui = make_test_gui()

    schedule = gui.catalog.get_schedule("Safety and Clearance")

    assert gui._get_schedule_parameter_names(schedule) == ["ClearanceHeight", "FireRating", "ServiceClearance"]


def test_wide_variety_examples_cover_multiple_families_and_schedules():
    gui = make_test_gui()

    assert len(gui.params_df) >= 18
    assert len(gui.families_df) >= 12
    assert len(gui.family_groups_df) >= 10
    assert set(gui.families_df["name"]) >= {f"Family_{letter}" for letter in "ABCDEFGHIJKL"}
    assert set(gui.family_groups_df["group_name"]) >= {
        "Schedule A", "Envelope Schedule", "Mechanical Schedule", "Facade Review", "Opening Schedule", "Safety and Clearance",
    }
    safety_rows = gui.family_groups_df[gui.family_groups_df["group_name"] == "Safety and Clearance"]
    assert set(safety_rows["family_name"]) == {"Family_K", "Family_L"}
    assert set(safety_rows["parameter_name"]) == {"ClearanceHeight", "FireRating", "ServiceClearance"}


# --- header canvas and tables ------------------------------------------------

def test_placeholder_entry_shows_gray_hint_until_typing_and_never_returns_it():
    root = tk.Tk()
    root.withdraw()
    try:
        entry = gui_module.PlaceholderEntry(root, placeholder="Blank Uses Family Default Value")

        assert entry.get() == ""
        assert ttk.Entry.get(entry) == "Blank Uses Family Default Value"
        assert entry.cget("style") == "Placeholder.TEntry"

        # Deleting or moving through the hint is ignored; typing a character clears it first.
        assert entry._on_key(SimpleNamespace(keysym="BackSpace", char="\b")) == "break"
        entry._on_key(SimpleNamespace(keysym="7", char="7"))
        assert ttk.Entry.get(entry) == ""
        assert entry.cget("style") == "TEntry"
        ttk.Entry.insert(entry, 0, "7")
        assert entry.get() == "7"

        entry.delete(0, tk.END)
        entry._show_if_empty()
        assert entry.get() == ""
        assert ttk.Entry.get(entry) == "Blank Uses Family Default Value"

        entry.insert(0, "2.25")
        assert entry.get() == "2.25"
    finally:
        root.destroy()


def test_add_parameter_button_links_a_missing_schedule_column_to_the_family():
    root = tk.Tk()
    root.withdraw()
    try:
        gui = make_test_gui()
        gui.root = root
        schedule = gui.catalog.get_schedule("Safety and Clearance")
        rows_builder = lambda: gui._schedule_table_rows(schedule)  # noqa: E731
        names = gui._get_schedule_parameter_names(schedule)
        table = OverrideTable(
            root, names, rows=rows_builder(),
            on_cell_action=lambda row, column: gui._add_parameter_from_table(table, rows_builder, row, column),
        )
        column = names.index("ServiceClearance")
        family_k_rows = [index for index, row in enumerate(table.rows) if row.get("family") == "Family_K"]
        assert all(table.rows[index]["cells"][column]["action"] == "Add Parameter to Family" for index in family_k_rows)
        # The family's rows in that column merge into one button.
        assert table._action_span(family_k_rows[1], column) == (family_k_rows[0], len(family_k_rows))

        left, top, _width, _height = table.cell_bbox(family_k_rows[1], column)
        table._on_mouse_down(SimpleNamespace(x=left + 10, y=top + 5, state=0))

        assert "ServiceClearance" in [param.name for param in gui.catalog.get_family("Family_K").params]
        assert cells(table.rows, "Default Value", "Family_K")[column] == ("", "inherited", True)
        assert not any(
            cell.get("action") for row in table.rows if row.get("family") == "Family_K" for cell in row["cells"]
        )
        # Family_L still lacks ClearanceHeight, so its button stays.
        family_l_value = next(row for row in table.rows if row.get("family") == "Family_L")
        assert family_l_value["cells"][names.index("ClearanceHeight")]["action"] == "Add Parameter to Family"
    finally:
        root.destroy()


def test_table_cells_edit_in_place_with_cancel_and_tab():
    root = tk.Tk()
    root.withdraw()
    try:
        gui = gui_from_tables(
            params=pd.DataFrame([
                {"name": name, "dtype": "Length", "instance_param": True, "default_value": "1"}
                for name in ("Width", "Height")
            ]),
            families=pd.DataFrame([{"name": "F1", "category": "Doors"}]),
            links=pd.DataFrame([{"family_name": "F1", "parameter_name": name} for name in ("Width", "Height")]),
        )
        gui.root = root
        fam = gui.catalog.get_family("F1")
        gui._ask_override_scope = answering({})
        rows_builder = lambda: gui._family_window_rows(fam)  # noqa: E731
        table = OverrideTable(root, ["Width", "Height"], rows=rows_builder(), show_header=False)
        value_row = next(index for index, row in enumerate(table.rows) if row.get("attribute") == "value")

        # The box sits exactly over the cell and shows the placeholder while empty.
        entry = gui._edit_table_cell(table, rows_builder, None, value_row, 0)
        window = table.find_withtag("all")[-1]
        assert tuple(table.coords(window)) == table.cell_bbox(value_row, 0)[:2]
        assert entry.placeholder == "Blank Uses Parameter Default Value"

        # Escape cancels.
        entry.insert(0, "9")
        table._cell_editor[1](False)
        assert fam.overrides == {}

        # Tab commits and moves to the next editable cell in the row.
        entry = gui._edit_table_cell(table, rows_builder, None, value_row, 0)
        entry.insert(0, "5")
        table._cell_editor[1](True, lambda: gui._edit_table_cell(table, rows_builder, None, value_row, 1))
        assert fam.overrides == {"Width": {"value": "5"}}
        assert table._cell_editor is not None
        table._cell_editor[0].insert(0, "6")
        table.finish_cell_edit()
        assert fam.overrides == {"Width": {"value": "5"}, "Height": {"value": "6"}}

        # Committing an unchanged value doesn't prompt or change anything.
        gui._ask_override_scope = lambda *args: pytest.fail("should not prompt")
        gui._edit_table_cell(table, rows_builder, None, value_row, 0)
        table.finish_cell_edit()

        # Read-only cells (the Parameter block) don't open a box.
        assert gui._edit_table_cell(table, rows_builder, None, 1, 0) is None
    finally:
        root.destroy()


def test_schedule_header_text_wraps_at_underscores_and_camel_case():
    canvas = object.__new__(OverrideTable)
    canvas.header_font = SimpleNamespace(measure=lambda text: len(text) * 6)

    lines = canvas._wrap_header_segment("IPS_EQUIP_AirDesign", 40)

    assert lines == ["IPS_", "EQUIP_", "Air", "Design"]
    assert "".join(lines) == "IPS_EQUIP_AirDesign"
    assert all(canvas.header_font.measure(line) <= 40 for line in lines)


def test_main_tab_table_headings_wrap_after_column_resize():
    root = tk.Tk()
    root.geometry("1200x1200")  # tall enough for all three tables, stacked here, once headings grow
    try:
        gui = DDMGUI.__new__(DDMGUI)
        gui.root = root
        parent = ttk.Frame(root)
        parent.pack()

        tables = {}
        for table_name in ("params", "families", "groups"):
            gui._build_data_table(parent, table_name)
            if table_name == "params":
                tree = gui.param_tree
            elif table_name == "families":
                tree = gui.family_tree
            else:
                tree = gui.group_tree
            tree.insert("", "end", values=[""] * len(tree.cget("columns")))
            tables[table_name] = tree
        for tree in tables.values():
            for column in tree._ddm_heading_columns:
                tree.column(column, width=300)
            gui._update_table_heading_wrap(tree)
        root.update()

        original_row_y = {
            tree: tree.bbox(tree.get_children()[0])[1]
            for tree in tables.values()
        }
        for tree in tables.values():
            first_item = tree.get_children()[0]
            for column in tree._ddm_heading_columns:
                tree.column(column, width=55)
            gui._update_table_heading_wrap(tree)
            root.update()

            assert any(
                "\n" in tree.heading(column, "text")
                for column in tree._ddm_heading_columns
            )
            assert all(
                str(tree.heading(column, "anchor")) == "n"
                for column in tree._ddm_heading_columns
            )
        root.update()
        heading_padding = tuple(
            int(str(value))
            for value in root.tk.splitlist(
                ttk.Style(root).lookup("Treeview.Heading", "padding")
            )
        )
        assert heading_padding[1] == 2
        # The headings share one style, so the bottom padding makes room for the tallest heading's
        # extra lines (ttk sizes a heading from its padding, not from its text).
        tallest = max(tree._ddm_heading_line_count for tree in tables.values())
        line_height = next(iter(tables.values()))._ddm_heading_font.metrics("linespace")
        assert heading_padding[3] == 2 + (tallest - 1) * line_height
        for tree in tables.values():
            first_item = tree.get_children()[0]
            assert tree.bbox(first_item)[1] > original_row_y[tree]
            line_count = max(
                tree.heading(column, "text").count("\n") + 1
                for column in tree._ddm_heading_columns
            )
            line_height = tree._ddm_heading_font.metrics("linespace")
            assert tree.bbox(first_item)[1] >= line_count * line_height + 4
    finally:
        root.destroy()


# --- windows and files ------------------------------------------------------

def test_schedule_popup_edits_columns_groups_headers_and_overrides_values(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        tab_texts = [gui.notebook.tab(tab_id, "text") for tab_id in gui.notebook.tabs()]
        assert tab_texts == ["Parameters", "Families", "Schedules"]
        assert gui.file_actions.grid_info()["row"] == 5
        assert [
            widget.cget("text")
            for widget in sorted(gui.file_actions.winfo_children(), key=lambda item: item.grid_info()["column"])
        ] == ["Load", "Save", "Save As...", "Import Excel..."]
        assert "demo_data.ddm.csv" in gui.warning_text.get("1.0", tk.END)
        assert "Safety and Clearance" in gui._build_schedule_summary_df()["name"].tolist()

        gui._open_detail_window("schedule", "Schedule A")
        root.update()
        schedule_popup = find_window(root, "Schedule Details: Schedule A")
        table = next(widget for widget in descendants(schedule_popup) if isinstance(widget, OverrideTable))
        assert table.parameter_names == ["Length", "Width"]

        header_y = table.header_top + 10
        table._on_double_click(SimpleNamespace(x=table.column_offsets[1] + 10, y=header_y))
        root.update()
        width_dialog = find_window(schedule_popup, "Schedule Column Settings")
        width_entries = [widget for widget in descendants(width_dialog) if isinstance(widget, ttk.Entry)]
        width_entries[1].insert(0, "2.25")
        hidden_box = next(widget for widget in descendants(width_dialog) if isinstance(widget, ttk.Checkbutton))
        assert hidden_box.cget("text") == "Hidden Column (Shown Only in the Working Schedule)"
        hidden_box.invoke()
        find_button(width_dialog, "Save").invoke()

        schedule = gui.catalog.get_schedule("Schedule A")
        assert schedule.grid_column_width_overrides == {"Width": 2.25}
        assert table.column_widths[1] == 2.25 * table.pixels_per_inch
        assert schedule.hidden_field_names == {"Width"}
        assert table.hidden_names == {"Width"}

        # The Hidden Column row under the headers toggles a column with one click.
        hidden_row_y = table.hidden_row_top + table.hidden_row_height // 2
        assert table.body_top == table.hidden_row_top + table.row_height
        table._on_mouse_down(SimpleNamespace(x=table.column_offsets[0] + 10, y=hidden_row_y, state=0))
        assert schedule.hidden_field_names == {"Length", "Width"}
        table._on_mouse_down(SimpleNamespace(x=table.column_offsets[1] + 10, y=hidden_row_y, state=0))
        assert schedule.hidden_field_names == {"Length"}
        assert table.hidden_names == {"Length"}
        assert table.get_selected_parameter_names() == []  # a checkbox click doesn't select the header
        table._on_mouse_down(SimpleNamespace(x=table.column_offsets[0] + 10, y=hidden_row_y, state=0))
        assert schedule.hidden_field_names == set()

        table._on_mouse_down(SimpleNamespace(x=table.column_offsets[0] + 10, y=header_y, state=0))
        table._on_mouse_drag(SimpleNamespace(x=table.column_offsets[1] + 10, y=header_y))
        assert table.get_selected_parameter_names() == ["Length", "Width"]
        find_button(schedule_popup, "Group Selected Headers").invoke()
        root.update()
        dialog = find_window(schedule_popup, "Name Header Group")
        next(widget for widget in descendants(dialog) if isinstance(widget, ttk.Entry)).insert(0, "Dimensions")
        find_button(dialog, "Group").invoke()

        assert schedule.header_groups[0]["caption"] == "Dimensions"
        assert schedule.header_groups[0]["parameter_names"] == ["Length", "Width"]
        assert len(table.group_layout) == 1

        assert cells(table.rows, "Default Value", "Family_A")[1] == ("Override Width", "set", True)

        # One click on Family_A's Width value edits it; type a new one and save.
        monkeypatch.setattr(gui, "_ask_override_scope", answering({}))
        row_index = next(
            index for index, row in enumerate(table.rows)
            if row.get("family") == "Family_A" and row.get("attribute") == "value"
        )
        table._on_mouse_down(SimpleNamespace(
            x=table.column_offsets[1] + 10,
            y=table.body_top + row_index * table.row_height + 5,
            state=0,
        ))
        root.update()
        entry, finish = table._cell_editor
        assert entry.master is table
        assert entry.get() == "Override Width"
        entry.delete(0, tk.END)
        entry.insert(0, "3.5")
        finish(True)

        assert table._cell_editor is None
        assert gui.catalog.resolved_value(("Family_A", "Schedule A"), "Width") == "3.5"
        assert cells(table.rows, "Default Value", "Family_A")[1] == ("3.5", "set", True)
    finally:
        root.destroy()


def test_parameters_tab_labels_defaults_and_shows_instance_or_type(tmp_path, monkeypatch):
    labels = {column: DDMGUI._display_labels[column] for column in ("header_text", "formula", "group_under", "instance_param")}
    assert labels == {
        "header_text": "Default Header", "formula": "Default Formula", "group_under": "Default Group Under",
        "instance_param": "Instance or Type",
    }
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        tree = gui.param_tree
        column = gui._get_table_columns("params").index("instance_param")
        shown = {tree.item(row, "values")[column] for row in tree.get_children()}
        assert shown <= {"Instance", "Type"}
        assert gui._revit_dropdown_values("instance_param") == ["Instance", "Type"]
        gui._apply_cell_value("params", 0, "instance_param", "Type")
        assert gui.catalog.params[0].instance_param is False
        assert tree.item(tree.get_children()[0], "values")[column] == "Type"
        assert gui.params_df["instance_param"].iloc[0] is False or gui.params_df["instance_param"].iloc[0] == False  # noqa: E712 - exports still get true / false
    finally:
        root.destroy()


def test_family_list_edits_in_place_on_one_click_and_names_open_the_name_builder(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.geometry("1400x800")
    try:
        gui = DDMGUI(root)
        gui.notebook.select(gui.family_tab)
        root.update()
        tree = gui.family_tree
        fam = gui.catalog.families[0]
        columns = gui._get_table_columns("families")
        assert columns.index("category_1") < columns.index("description")

        def click(column_name):
            column = columns.index(column_name)
            tree.xview_moveto(0 if column < 6 else 1)  # bring the column into view
            root.update()
            x, y, width, height = tree.bbox(tree.get_children()[0], f"#{column + 1}")
            gui._on_tree_click(SimpleNamespace(x=x + width // 2, y=y + height // 2), "families")

        # One click edits a cell at once (there's no double-click to wait for).
        click("description")
        editor, finish = gui._tree_cell_editor
        editor.delete(0, tk.END)
        editor.insert(0, "Edited in place")
        finish(True)
        assert fam.description == "Edited in place"
        assert "<Double-1>" not in tree.bind()

        # One click on a name opens the Family Name Builder.
        click("name")
        root.update()
        find_window(root, "Family Name Builder")
    finally:
        root.destroy()


def naming_gui():
    """Two Detail Item families with codes for every term."""
    gui = make_test_gui()
    catalog = gui.catalog
    for kind, name, code in (("client", "IPS", "IPS"), ("country", "United States", "US"),
                             ("category_1", "Control", "CTRL"), ("category_2", "Device", "Device"),
                             ("category", "Detail Item", "2D")):
        catalog.set_code(kind, name, code)
    for index, fam in enumerate(catalog.families[:2]):
        fam.client, fam.country, fam.category = "IPS", "United States", "Detail Item"
        fam.category_1, fam.category_2, fam.description = "Control", "Device", f"Light {index}"
    return gui


def test_family_name_builder_builds_renames_and_saves_the_shared_format(monkeypatch):
    gui = naming_gui()
    root = tk.Tk()
    root.withdraw()
    gui.root = root
    try:
        fam = gui.catalog.families[0]
        blank = gui.catalog.families[2]
        blank.description = blank.client = blank.country = blank.category = None
        blank_name = blank.name
        window = gui._open_family_name_builder(0)
        assert window.name_var.get() == "IPS-US_CTRL_Device_Light 0_2D"
        labels = [w.cget("text") for w in descendants(window) if isinstance(w, ttk.Label)]
        assert {"Client Code", "Category Code", "Category 1", "Prefix", "Suffix"} <= set(labels)

        # Moving a term and changing a suffix rebuild the name at once.
        index = next(i for i, part in enumerate(window.parts) if part["term"] == "description")
        window.move(index, -1)
        assert window.name_var.get() == "IPS-US_CTRL_Light 0_Device_2D"
        description_suffix = [w for w in descendants(window) if isinstance(w, ttk.Entry)][2 * index - 1]
        description_suffix.insert(0, "!")
        assert window.name_var.get() == "IPS-US_CTRL_Light 0!_Device_2D"

        window.rename_this()
        assert fam.name == "IPS-US_CTRL_Light 0!_Device_2D"
        assert [part["term"] for part in gui.catalog.family_name_format][3:5] == ["description", "category_2_code"]
        assert gui.families_df.iloc[0]["name"] == fam.name

        # Rename All: the second family follows the format; families whose name would be blank stay.
        window = gui._open_family_name_builder(1)
        asked = []
        monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda title, message, **_kw: asked.append(message) or True)
        window.rename_all()
        assert gui.catalog.families[1].name == "IPS-US_CTRL_Light 1!_Device_2D"
        assert "\nFamily_B \u2192 IPS-US_CTRL_Light 1!_Device_2D" in asked[0]
        assert "left as they are" in asked[0]  # the family with nothing to name it by
        assert gui.catalog.families[2].name == blank_name
        assert "families in Revit aren't renamed" in asked[0]
    finally:
        root.destroy()


def test_family_renames_skip_blank_and_clashing_names():
    gui = naming_gui()
    first, second, blank = gui.catalog.families[:3]
    second.description = first.description  # both would get the same name
    blank.description = blank.client = blank.country = blank.category = None
    renames, skipped = gui._family_renames(gui.catalog.family_name_format)
    assert all(old not in (first.name, second.name) for old, _new in renames)
    assert any("would get 'IPS-US_CTRL_Device_Light 0_2D'" in reason for reason in skipped)
    assert any("would be blank" in reason for reason in skipped)


def test_family_table_shows_category_codes_and_new_categories_need_a_code(monkeypatch):
    gui = naming_gui()
    row = gui.families_df.iloc[0]
    assert (row["category_code"], row["category_1"], row["category_1_code"], row["category_2_code"]) == (
        "2D", "Control", "CTRL", "Device")
    assert gui._dropdown_values("category_1")[-1] == gui_module.ADD_NEW
    gui._apply_cell_value("families", 0, "category_code", "3D")
    assert gui.catalog.code("category", "Detail Item") == "3D"
    assert gui.families_df.iloc[1]["category_code"] == "3D"  # every Detail Item family


def test_search_filters_each_main_tab_and_edits_reach_the_right_item(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.geometry("1200x800")
    try:
        gui = DDMGUI(root)
        root.update()
        assert set(gui._search_vars) == {"params", "families", "groups"}

        # Search for the last family by name: only it shows, and its row edits that family.
        fam = gui.catalog.families[-1]
        gui._search_vars["families"].set(fam.name.upper())
        gui.notebook.select(gui.family_tab)
        root.update()
        tree = gui.family_tree
        assert [tree.item(row, "values")[0] for row in tree.get_children()] == [fam.name]
        assert gui._search_counts["families"].cget("text") == f"Showing 1 of {len(gui.catalog.families)}"
        column = gui._get_table_columns("families").index("description")
        gui._start_tree_cell_edit(tree, "families", tree.get_children()[0], column)
        editor, finish = gui._tree_cell_editor
        editor.delete(0, tk.END)
        editor.insert(0, "Found by search")
        finish(True)
        assert fam.description == "Found by search"
        # The search stays applied after the edit re-renders the table.
        assert len(tree.get_children()) == 1

        # Every word must match, in any column; clearing shows everything again.
        gui._search_vars["families"].set(f"{fam.name} no-such-word")
        assert tree.get_children() == ()
        assert gui._search_counts["families"].cget("text") == f"Showing 0 of {len(gui.catalog.families)}"
        gui._search_vars["families"].set("")
        assert len(tree.get_children()) == len(gui.catalog.families)
        assert gui._search_counts["families"].cget("text") == ""

        param = gui.catalog.params[-1]
        gui._search_vars["params"].set(param.name)
        assert param.name in [gui.param_tree.item(row, "values")[0] for row in gui.param_tree.get_children()]
        assert len(gui.param_tree.get_children()) < len(gui.catalog.params)

        # A filtered schedule row opens that schedule's window.
        schedule = gui.catalog.schedules[-1]
        gui._search_vars["groups"].set(schedule.name)
        gui.notebook.select(gui.schedules_tab)
        root.update()
        row = gui.group_tree.get_children()[0]
        assert int(row) == len(gui.catalog.schedules) - 1
        _x, y, _width, height = gui.group_tree.bbox(row)
        opened = []
        monkeypatch.setattr(gui, "_open_detail_window", lambda kind, name: opened.append((kind, name)))
        gui._open_selected_schedule_window(SimpleNamespace(x=5, y=y + height // 2))
        assert opened == [("schedule", schedule.name)]
    finally:
        root.destroy()


def test_parameter_list_edits_in_place_on_one_click_and_pops_up_on_two(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.geometry("1200x800")
    try:
        gui = DDMGUI(root)
        gui.notebook.select(gui.params_tab)
        root.update()
        tree = gui.param_tree
        param = gui.catalog.params[0]
        column = gui._get_table_columns("params").index("header_text")
        x, y, width, height = tree.bbox(tree.get_children()[0], f"#{column + 1}")
        click = SimpleNamespace(x=x + width // 2, y=y + height // 2)

        gui._on_tree_click(click, "params")
        root.after(gui._single_click_delay_ms + 50, root.quit)
        root.mainloop()
        editor, finish = gui._tree_cell_editor
        editor.delete(0, tk.END)
        editor.insert(0, "Edited Header")
        finish(True)
        assert param.header_text == "Edited Header"

        # Two clicks: no in-place editor, the edit pop-up opens instead.
        gui._on_tree_click(click, "params")
        gui._on_tree_double_click(click, "params")
        assert gui._pending_tree_edit is None
        root.update()
        find_window(root, "Edit Default Header")
        assert getattr(gui, "_tree_cell_editor", None) is None
    finally:
        root.destroy()


def test_override_windows_have_an_override_rules_button(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        windows = [("family", 0, "Family Details"),
                   ("schedule", gui.catalog.schedules[0].name, f"Schedule Details: {gui.catalog.schedules[0].name}")]
        for item_type, key, title in windows:
            gui._open_detail_window(item_type, key)
            root.update()
            form = find_window(root, title)
            find_button(form, "ⓘ Override Rules").invoke()
            root.update()
            info = find_window(root, "Override Rules")
            text = next(widget for widget in descendants(info) if isinstance(widget, tk.Text))
            for heading, _body in gui_module.OVERRIDE_RULES:
                assert heading in text.get("1.0", tk.END)
            find_button(info, "Close").invoke()
            root.update()
            assert form.grab_current() is form  # the modal window gets its grab back
            form.destroy()

        # The where-else prompt has the button too.
        found = []
        failures = run_in_dialog(root, lambda: (
            found.append(find_button(find_window(root, "Override Default Value"), "ⓘ Override Rules")),
            find_button(find_window(root, "Override Default Value"), "Cancel").invoke(),
        ))
        fam = gui.catalog.families[0]
        gui._ask_override_scope(fam.custom_params[0].name, "7", (fam.name, None), [], True)
        assert not failures and found
    finally:
        root.destroy()


def test_family_window_lists_values_and_saves_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        gui._open_detail_window("family", 0)
        root.update()
        form = find_window(root, "Family Details")

        fam = gui.catalog.families[0]
        table = next(widget for widget in descendants(form) if isinstance(widget, OverrideTable))
        assert table.parameter_names == [param.name for param in fam.custom_params]
        assert not table.show_header

        # Double-click Family_A's Length formula and override it.
        monkeypatch.setattr(gui, "_ask_override_scope", answering({}))
        row_index = next(
            index for index, row in enumerate(table.rows)
            if row.get("family") == fam.name and row.get("attribute") == "formula"
        )
        table._on_double_click(SimpleNamespace(
            x=table.column_offsets[0] + 10, y=table.body_top + row_index * table.row_height + 5,
        ))
        root.update()
        entry, finish = table._cell_editor
        entry.insert(0, "Width * 2")
        finish(True)
        assert fam.overrides[table.parameter_names[0]] == {"formula": "Width * 2"}

        description = next(
            widget for widget in descendants(form)
            if isinstance(widget, ttk.Entry) and widget.get() == "Main family"
        )
        description.delete(0, tk.END)
        description.insert(0, "Updated family")
        find_button(form, "Save").invoke()
        assert gui.catalog.families[0].description == "Updated family"
    finally:
        root.destroy()


def test_database_saves_as_json_with_csv_and_exports_and_loads_back(tmp_path):
    gui = make_test_gui()
    gui._add_schedule_header_group("Schedule A", ["Length", "Width"], "Dimensions")
    gui.checkpoint_path = tmp_path / "test_data.ddm.json"
    output_paths = get_database_output_paths(gui.checkpoint_path)

    gui.save_checkpoint()
    loaded = make_test_gui()
    loaded.load_checkpoint(str(output_paths["checkpoint"]))

    assert loaded.schedule_header_groups["Schedule A"][0]["caption"] == "Dimensions"
    assert loaded.catalog.to_dict() == gui.catalog.to_dict()
    assert output_paths["csv"].exists()
    assert "CreateSchedulesFromDatabase" in output_paths["macro"].read_text(encoding="utf-8")
    assert "TemplateName" in output_paths["rfps"].read_text(encoding="utf-8").splitlines()[0]
    assert "*PARAM\tGUID\tNAME\tDATATYPE" in output_paths["shared_parameters"].read_text(encoding="utf-16")


def test_saved_database_loads_on_next_gui_start(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "database.ddm.json"
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", checkpoint_path)
    fixture_gui = make_test_gui()
    fixture_gui._add_schedule_header_group("Schedule A", ["Length", "Width"], "Dimensions")
    fixture_gui._write_checkpoint(checkpoint_path)

    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        assert gui.schedule_header_groups["Schedule A"][0]["caption"] == "Dimensions"
        assert gui.checkpoint_path == checkpoint_path
    finally:
        root.destroy()


def test_checkpoint_file_dialogs_save_as_and_load_selected_file(tmp_path, monkeypatch):
    gui = make_test_gui()
    gui._add_schedule_header_group("Schedule A", ["Length", "Width"], "Dimensions")
    checkpoint_path = tmp_path / "custom_database.ddm.json"
    output_paths = get_database_output_paths(checkpoint_path)
    save_dialog_options = {}
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: save_dialog_options.update(kwargs) or str(checkpoint_path),
    )
    monkeypatch.setattr(gui_module.filedialog, "askopenfilename", lambda **kwargs: str(checkpoint_path))

    gui.save_checkpoint_as()
    assert save_dialog_options["defaultextension"] == ".ddm.json"
    for path in output_paths.values():
        assert path.exists()

    loaded = make_test_gui()
    loaded.load_checkpoint()
    assert loaded.schedule_header_groups["Schedule A"][0]["caption"] == "Dimensions"


def test_csv_database_round_trip_preserves_all_tables_and_header_groups(tmp_path):
    gui = make_test_gui(header_groups={
        "Schedule A": [{"caption": "Dimensions", "parameter_names": ["Length", "Width"], "top_row": 0, "bottom_row": 0}]
    })
    gui.checkpoint_path = tmp_path / "database.ddm.json"
    gui.save_checkpoint()

    loaded = make_test_gui()
    loaded.load_checkpoint(str(tmp_path / "database.ddm.csv"))

    assert loaded.load_issues == []
    for view in ("params_df", "families_df", "family_param_links_df", "family_groups_df"):
        pd.testing.assert_frame_equal(getattr(loaded, view), getattr(gui, view))
    assert loaded.schedule_header_groups == gui.schedule_header_groups


def test_older_pickle_database_still_loads():
    gui = make_test_gui()
    gui.load_checkpoint(str(TEST_CHECKPOINT_PATH))

    with TEST_CHECKPOINT_PATH.open("rb") as checkpoint_file:
        checkpoint = pickle.load(checkpoint_file)
    assert len(gui.catalog.params) == len(checkpoint["params"])
    assert gui.checkpoint_path == TEST_CHECKPOINT_PATH
    assert get_database_output_paths(gui.checkpoint_path)["checkpoint"].suffix == ".json"


def test_demo_database_loads_without_problems():
    gui = make_test_gui()
    gui.load_checkpoint(str(DEMO_DATA_PATH))

    assert gui.load_issues == []
    assert len(gui.params_df) == 16
    assert len(gui.families_df) == 12
    assert len(gui.family_param_links_df) == 17
    assert len(gui.family_groups_df) == 15
    assert "Safety and Clearance" in gui.family_groups_df["group_name"].tolist()


def test_legacy_parameter_csv_loads_as_parameter_only_database(tmp_path):
    gui = make_test_gui()
    legacy_csv_path = tmp_path / "legacy_parameters.csv"
    pd.DataFrame([{"name": "Volume", "dtype": "Volume", "group_under": "Dimensions"}]).to_csv(legacy_csv_path, index=False)

    gui.load_checkpoint(str(legacy_csv_path))

    assert gui.params_df["name"].tolist() == ["Volume"]
    assert gui.families_df.empty
    assert gui.family_param_links_df.empty
    assert gui.family_groups_df.empty


def test_unified_test_database_contains_seed_parameters_and_defaults():
    gui = make_test_gui()
    all_air_parameters = gui.params_df.loc[gui.params_df["name"].str.startswith("DDM_EQUIP_Air_")]

    assert len(all_air_parameters) == 7
    assert set(all_air_parameters["dtype"]) == {"Number"}
    assert set(all_air_parameters["group_under"]) == {"Mechanical Flow"}
    assert all_air_parameters["formula"].eq("").all()
    assert all_air_parameters["instance_param"].all()
    assert set(all_air_parameters["default_value"]) == {"-999"}


def test_the_database_folder_setting_moves_the_working_database(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(app_paths, "USER_SETTINGS_PATH", settings)
    assert app_paths._database_folder_setting() is None  # no settings file
    settings.write_text('{"revit_macro_module": "x"}', encoding="utf-8")
    assert app_paths._database_folder_setting() is None
    settings.write_text(json.dumps({"database_folder": r"D:\Shared\ddm-data"}), encoding="utf-8")
    assert app_paths._database_folder_setting() == Path(r"D:\Shared\ddm-data")
    settings.write_text("not json", encoding="utf-8")
    assert app_paths._database_folder_setting() is None


def test_database_paths_are_configured_under_data_directory():
    assert DEMO_DATA_PATH.name == "demo_data.ddm.csv"
    assert TEST_DATABASE_CSV_PATH.name == "test_data.ddm.csv"
    # Fixtures stay in the repo, wherever the working database lives.
    assert TEST_CHECKPOINT_PATH.parent == DEMO_DATA_PATH.parent == app_paths.PROJECT_ROOT / "data" / "test_data"
    assert gui_module.DEFAULT_CHECKPOINT_PATH == DATA_DIR / "database.ddm.json"
    assert get_database_output_paths(gui_module.DEFAULT_CHECKPOINT_PATH) == {
        "checkpoint": DATA_DIR / "database.ddm.json",
        "csv": DATA_DIR / "database.ddm.csv",
        "macro": DATA_DIR / "database.cs",
        "rfps": DATA_DIR / "database.rfps",
        "shared_parameters": DATA_DIR / "database.txt",
    }


def test_database_output_paths_share_stem_for_json_pickle_and_csv_inputs(tmp_path):
    paths = [
        get_database_output_paths(tmp_path / f"equipment.ddm.{suffix}")
        for suffix in ("json", "pkl", "csv")
    ]

    assert paths[0] == paths[1] == paths[2]
    assert paths[0]["checkpoint"].name == "equipment.ddm.json"
    assert paths[0]["csv"].name == "equipment.ddm.csv"
    assert paths[0]["macro"].name == "equipment.cs"
    assert paths[0]["rfps"].name == "equipment.rfps"
    assert paths[0]["shared_parameters"].name == "equipment.txt"


# --- clients and countries ----------------------------------------------------

def test_family_table_shows_codes_and_editing_a_code_changes_it_for_the_client():
    gui = make_test_gui()
    assert gui._get_table_columns("families")[:5] == ["name", "client", "client_code", "country", "country_code"]
    assert gui._dropdown_values("client")[-1] == gui_module.ADD_NEW
    assert "Client B" in gui._dropdown_values("client")

    gui.catalog.get_family("Family_B").client = "Client A"
    gui._apply_cell_value("families", 0, "client_code", "CLA")
    assert gui.catalog.get_family("Family_B").client_code == "CLA"
    assert list(gui.families_df.loc[gui.families_df["client"] == "Client A", "client_code"]) == ["CLA", "CLA"]

    gui.catalog.get_family("Family_A").country = None
    with pytest.raises(ValueError, match="Choose a country before setting its code"):
        gui._apply_cell_value("families", 0, "country_code", "US")


def test_schedule_settings_box_saves_filter_itemize_and_view_template(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        schedule = gui.catalog.schedules[0]
        gui._open_detail_window("schedule", schedule.name)
        root.update()
        form = find_window(root, f"Schedule Details: {schedule.name}")
        box = next(w for w in descendants(form) if isinstance(w, ttk.LabelFrame) and w.cget("text") == "Schedule Settings")
        labels = [w.cget("text") for w in descendants(box) if isinstance(w, ttk.Label)]
        assert labels == ["Schedule Filter", "IPS_GROUP_Schedule_Name =", "View Template"]
        filter_entry, template_entry = [w for w in descendants(box) if isinstance(w, gui_module.PlaceholderEntry)]
        itemize = next(w for w in descendants(box) if isinstance(w, ttk.Checkbutton))
        assert itemize.cget("text") == "Itemize Every Instance"
        assert filter_entry.get() == "" and filter_entry.placeholder.startswith(schedule.name)

        filter_entry.insert(0, "FILTER A")
        template_entry.insert(0, "IPS Schedules")
        box.save()
        itemize.invoke()  # on by default; one click turns it off and saves
        assert (schedule.filter_value, schedule.itemize, schedule.view_template) == ("FILTER A", False, "IPS Schedules")
        fam = schedule.fams[0]
        assert schedule.resolved_family_param(fam, "IPS_GROUP_Schedule_Name").value == "FILTER A"

        # Typing the schedule's own name is the same as leaving it blank.
        filter_entry.delete(0, tk.END)
        filter_entry.insert(0, schedule.name)
        box.save()
        assert schedule.filter_value is None
    finally:
        root.destroy()


def schedule_window_parts(root, schedule):
    """The open schedule window's table and its Add/Remove buttons bar."""
    form = find_window(root, f"Schedule Details: {schedule.name}")
    table = next(w for w in descendants(form) if isinstance(w, gui_module.OverrideTable))
    bar = next(w for w in descendants(form) if hasattr(w, "remove_families"))
    return table, bar


def click(table, x, y, state=0):
    table._on_mouse_down(SimpleNamespace(x=x, y=y, state=state))


def test_schedule_window_selects_and_removes_families_and_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        schedule = next(
            schedule for schedule in gui.catalog.schedules if len(schedule.fams) >= 2 and len(schedule.params) >= 3
        )
        gui._open_detail_window("schedule", schedule.name)
        root.update()
        table, bar = schedule_window_parts(root, schedule)
        buttons = [w.cget("text") for w in descendants(bar) if isinstance(w, ttk.Button)]
        assert buttons == [
            "Add Parameter...", "Remove Parameter", "◀ Move Left", "Move Right ▶",
            "Add Family...", "Remove Family",
        ]

        # Clicking a family's name on the left selects it; Ctrl-click adds another.
        def family_y(name):
            row = next(i for i, row in enumerate(table.rows) if row.get("family") == name)
            return table.body_top + row * table.row_height + table.row_height // 2

        first, second = schedule.fams[0].name, schedule.fams[1].name
        click(table, 20, family_y(first))
        click(table, 150, family_y(second), state=0x0004)
        assert table.get_selected_family_names() == [first, second]

        # Selecting a column clears the family selection; a Name cell selects its column too.
        name_row = next(i for i, row in enumerate(table.rows) if row.get("selects_column"))
        names = [param.name for param in schedule.params]
        click(table, table.column_offsets[1] + 5, table.body_top + name_row * table.row_height + 5)
        click(table, table.column_offsets[2] + 5, table.header_top + 5, state=0x0004)
        assert table.get_selected_parameter_names() == names[1:3]
        assert table.get_selected_family_names() == []

        # Saying no to the confirmation keeps the columns; yes removes them and reopens the window.
        monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda *_args, **_kwargs: False)
        bar.remove_parameters()
        assert [param.name for param in schedule.params] == names
        monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda *_args, **_kwargs: True)
        bar.remove_parameters()
        root.update()
        assert [param.name for param in schedule.params] == names[:1] + names[3:]

        table, bar = schedule_window_parts(root, schedule)
        fam = schedule.fams[0]
        column = schedule.family_param_names(fam)[0]
        schedule.override_family_param(fam.name, column, value="Gone")
        click(table, 20, family_y(fam.name))
        bar.remove_families()
        root.update()
        assert schedule.get_family(fam.name) is None
        assert fam.name not in schedule.family_overrides

        # Nothing selected: the Remove buttons say what to select instead.
        table, bar = schedule_window_parts(root, schedule)
        shown = []
        monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda title, message, **_kwargs: shown.append(title))
        bar.remove_families()
        bar.remove_parameters()
        assert shown == ["Remove Families", "Remove Parameters"]
    finally:
        root.destroy()


def test_schedule_window_moves_selected_columns_and_keeps_them_selected(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        schedule = next(schedule for schedule in gui.catalog.schedules if len(schedule.params) >= 3)
        names = [param.name for param in schedule.params]
        gui._open_detail_window("schedule", schedule.name)
        root.update()
        table, bar = schedule_window_parts(root, schedule)

        click(table, table.column_offsets[0] + 5, table.header_top + 5)
        bar.move(1)
        root.update()
        assert [param.name for param in schedule.params] == [names[1], names[0]] + names[2:]
        # The window reopens with the moved column still selected, so the arrows can be clicked again.
        table, bar = schedule_window_parts(root, schedule)
        assert table.get_selected_parameter_names() == [names[0]]
        bar.move(1)
        assert [param.name for param in schedule.params][2] == names[0]
        for _ in range(2):
            _table, bar = schedule_window_parts(root, schedule)
            bar.move(-1)
        root.update()
        assert [param.name for param in schedule.params] == names

        # Already at the left end: nothing changes. A move that would split a header group is refused.
        table, bar = schedule_window_parts(root, schedule)
        bar.move(-1)
        assert [param.name for param in schedule.params] == names
        schedule.add_header_group("Pair", names[1:3])
        warnings = []
        monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda title, message, **_kw: warnings.append(message))
        bar.move(1)
        assert [param.name for param in schedule.params] == names
        assert warnings and "split header group 'Pair'" in warnings[0]
    finally:
        root.destroy()


def test_add_all_parameters_button_gives_a_family_every_schedule_column(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        schedule = gui.catalog.schedules[0]
        unlinked = next(fam for fam in gui.catalog.families if fam not in schedule.fams)
        gui._link_schedule_families(schedule.name, [unlinked.name])
        columns = [param.name for param in schedule.params if gui.catalog.get_param(param.name)]
        missing = [name for name in columns if name not in {param.name for param in unlinked.params}]
        assert missing, "the demo family should lack some of the schedule's columns"
        gui._open_detail_window("schedule", schedule.name)
        root.update()
        table, _bar = schedule_window_parts(root, schedule)
        first = next(row for row in table.rows if row.get("family") == unlinked.name)
        assert first["family_action"] == "Add All Parameters"

        left, top, right, bottom = table._family_action_boxes[unlinked.name]
        click(table, (left + right) / 2, (top + bottom) / 2)
        assert {name for name in columns} <= {param.name for param in unlinked.params}
        first = next(row for row in table.rows if row.get("family") == unlinked.name)
        assert "family_action" not in first  # nothing left to add
        assert unlinked.name not in table._family_action_boxes
    finally:
        root.destroy()


def test_schedule_window_adds_parameters_after_the_selected_column_and_adds_families(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        schedule = gui.catalog.schedules[0]
        names = [param.name for param in schedule.params]
        new_param = next(param.name for param in gui.catalog.params if param.name not in names)
        unlinked = [fam for fam in gui.catalog.families if fam not in schedule.fams]
        assert unlinked, "the demo needs a family outside the first schedule"
        before = [fam.name for fam in schedule.fams]
        gui._open_detail_window("schedule", schedule.name)
        root.update()
        table, bar = schedule_window_parts(root, schedule)

        # The parameter picker lists only parameters not yet columns; it adds after the selection.
        click(table, table.column_offsets[0] + 5, table.header_top + 5)
        picker = bar.add_parameters()
        assert picker.title() == f"Add Parameters to {schedule.name}"
        assert new_param in picker.listbox.get(0, "end")
        assert not set(names) & set(picker.listbox.get(0, "end"))
        picker.search_var.set(new_param)
        picker.listbox.selection_set(list(picker.listbox.get(0, "end")).index(new_param))
        picker.add()
        root.update()
        assert [param.name for param in schedule.params] == names[:1] + [new_param] + names[1:]

        # The family picker lists only unlinked families, and searching narrows it.
        table, bar = schedule_window_parts(root, schedule)
        picker = bar.add_families()
        assert list(picker.listbox.get(0, "end")) == [fam.name for fam in unlinked]
        target = unlinked[-1]
        picker.search_var.set(target.name.upper())
        picker.listbox.selection_set(list(picker.listbox.get(0, "end")).index(target.name))
        picker.add()
        root.update()
        assert [fam.name for fam in schedule.fams] == before + [target.name]
        assert gui.group_tree.item(gui.group_tree.get_children()[0], "values")[1] == str(len(before) + 1)
        table, _bar = schedule_window_parts(root, schedule)
        assert target.name in table._family_names()
    finally:
        root.destroy()


def test_schedule_family_links_round_trip_through_csv(tmp_path):
    gui = make_test_gui()
    schedule = gui.catalog.schedules[0]
    extra = next(fam for fam in gui.catalog.families if fam not in schedule.fams)
    gui._link_schedule_families(schedule.name, [extra.name])
    gui.checkpoint_path = tmp_path / "database.ddm.json"
    gui.save_checkpoint()

    loaded = make_test_gui()
    loaded.load_checkpoint(str(tmp_path / "database.ddm.csv"))
    assert extra.name in [fam.name for fam in loaded.catalog.get_schedule(schedule.name).fams]


def test_schedule_window_title_renames_the_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        schedule, other = gui.catalog.schedules[:2]
        old_name = schedule.name
        gui._open_detail_window("schedule", old_name)
        root.update()

        def name_entry(name):
            form = find_window(root, f"Schedule Details: {name}")
            return next(w for w in descendants(form) if hasattr(w, "rename"))

        entry = name_entry(old_name)
        assert entry.get() == old_name

        # A taken or blank name is refused and the title goes back.
        warnings = []
        monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda title, message, **_kw: warnings.append(message))
        for bad in (other.name, "   "):
            entry.delete(0, tk.END)
            entry.insert(0, bad)
            entry.rename()
            assert schedule.name == old_name and entry.get() == old_name
        assert warnings == [f"Schedule name '{other.name}' already exists.", "Schedule name is required."]

        # A new name renames it, updates the Schedules list and reopens the window under it.
        entry.delete(0, tk.END)
        entry.insert(0, "  Renamed Schedule ")
        entry.rename()
        root.update()
        assert schedule.name == "Renamed Schedule"
        assert gui.group_tree.item(gui.group_tree.get_children()[0], "values")[0] == "Renamed Schedule"
        assert name_entry("Renamed Schedule").get() == "Renamed Schedule"
        assert schedule.resolved_filter_value == "Renamed Schedule"  # a blank filter follows the name
    finally:
        root.destroy()


def test_schedule_settings_round_trip_through_csv(tmp_path):
    gui = make_test_gui()
    schedule = gui.catalog.schedules[0]
    gui._set_schedule_settings(schedule.name, "FILTER A", False, "IPS Schedules")
    gui.checkpoint_path = tmp_path / "database.ddm.json"
    gui.save_checkpoint()

    loaded = make_test_gui()
    loaded.load_checkpoint(str(tmp_path / "database.ddm.csv"))
    restored = loaded.catalog.get_schedule(schedule.name)
    assert (restored.filter_value, restored.itemize, restored.view_template) == ("FILTER A", False, "IPS Schedules")
    other = loaded.catalog.schedules[1]
    assert (other.filter_value, other.itemize, other.view_template) == (None, True, None)


def test_codes_round_trip_through_csv_and_conflicts_are_reported(tmp_path):
    gui = make_test_gui()
    gui.catalog.set_code("client", "Client A", "CLA")
    gui.catalog.set_code("country", "USA", "US")
    gui.checkpoint_path = tmp_path / "database.ddm.json"
    gui.save_checkpoint()

    loaded = make_test_gui()
    loaded.load_checkpoint(str(tmp_path / "database.ddm.csv"))
    assert loaded.load_issues == []
    assert loaded.catalog.get_family("Family_A").client_code == "CLA"
    assert loaded.catalog.get_family("Family_A").country_code == "US"

    tables = make_test_tables()
    families = tables["families"].copy()
    families["client"] = "Client A"
    families["client_code"] = ["CLA", "OTHER"] + [""] * (len(families) - 2)
    tables["families"] = families
    catalog, issues = catalog_from_tables(**tables)
    assert catalog.code("client", "Client A") == "CLA"
    assert any("already has 'CLA'" in issue for issue in issues)


def test_choosing_add_new_in_the_family_list_adds_a_client(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.geometry("1200x800")
    try:
        gui = DDMGUI(root)
        gui.notebook.select(gui.family_tab)
        root.update()
        tree = gui.family_tree
        column = gui._get_table_columns("families").index("client")

        def add_new(kind, parent=None):
            gui.catalog.set_code(kind, "New Client", "NEW")
            return "New Client"

        monkeypatch.setattr(gui, "_ask_new_code_entry", add_new)
        gui._start_tree_cell_edit(tree, "families", tree.get_children()[0], column)
        editor, finish = gui._tree_cell_editor
        assert editor.cget("values")[-1] == gui_module.ADD_NEW
        editor.set(gui_module.ADD_NEW)
        finish(True)
        fam = gui.catalog.families[0]
        assert (fam.client, fam.client_code) == ("New Client", "NEW")

        # Cancelling the dialog keeps the old client.
        monkeypatch.setattr(gui, "_ask_new_code_entry", lambda kind, parent=None: None)
        gui._start_tree_cell_edit(tree, "families", tree.get_children()[0], column)
        editor, finish = gui._tree_cell_editor
        editor.set(gui_module.ADD_NEW)
        finish(True)
        assert fam.client == "New Client"
    finally:
        root.destroy()


def test_add_new_dialog_adds_a_country_with_its_code(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)

        def fill():
            dialog = find_window(root, "Add New Country")
            name_entry, code_entry = [w for w in descendants(dialog) if isinstance(w, gui_module.PlaceholderEntry)]
            name_entry.insert(0, "Atlantis")
            code_entry.insert(0, "ATL")
            find_button(dialog, "Add").invoke()

        failures = run_in_dialog(root, fill)
        assert gui._ask_new_code_entry("country") == "Atlantis"
        assert not failures
        assert gui.catalog.code("country", "Atlantis") == "ATL"
        assert "Atlantis" in gui._dropdown_values("country")
    finally:
        root.destroy()


def test_family_window_add_new_client_fills_in_its_code(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        fam = gui.catalog.families[0]
        old_client = fam.client
        gui.catalog.set_code("client", old_client, "OLD")

        def add_new(kind, parent=None):
            gui.catalog.set_code(kind, "New Client", "NEW")
            return "New Client"

        monkeypatch.setattr(gui, "_ask_new_code_entry", add_new)
        gui._open_detail_window("family", 0)
        root.update()
        form = find_window(root, "Family Details")
        combo = next(w for w in descendants(form) if isinstance(w, ttk.Combobox) and w.get() == old_client)
        code_entry = next(w for w in descendants(form) if type(w) is ttk.Entry and w.get() == "OLD")
        combo.set(gui_module.ADD_NEW)
        combo.event_generate("<<ComboboxSelected>>")
        root.update()
        assert combo.get() == "New Client"
        assert code_entry.get() == "NEW"

        find_button(form, "Save").invoke()
        assert (fam.client, fam.client_code) == ("New Client", "NEW")
        assert gui.catalog.code("client", old_client) == "OLD"  # the old client's code is untouched
    finally:
        root.destroy()


# --- unsaved changes ------------------------------------------------------------

def open_saved_gui(tmp_path, monkeypatch):
    """A GUI on a database saved at tmp_path, with no macro module to build."""
    path = tmp_path / "database.ddm.json"
    make_test_gui().catalog.save(str(path))
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", path)
    root = tk.Tk()
    root.withdraw()
    gui = DDMGUI(root)
    return root, gui, path


def test_edits_are_unsaved_until_saved(tmp_path, monkeypatch):
    root, gui, path = open_saved_gui(tmp_path, monkeypatch)
    try:
        assert not gui.has_unsaved_changes()
        gui.validate_all()  # refreshing changes nothing
        assert not gui.has_unsaved_changes()
        gui.catalog.families[0].description = "Edited"
        assert gui.has_unsaved_changes()
        assert gui.save_checkpoint() is True
        assert not gui.has_unsaved_changes()
        gui.catalog.families[0].description = "Edited again"
        gui.load_checkpoint(str(path))  # reloading discards
        assert not gui.has_unsaved_changes()
    finally:
        root.destroy()


def test_closing_with_unsaved_changes_asks_to_save_discard_or_cancel(tmp_path, monkeypatch):
    root, gui, path = open_saved_gui(tmp_path, monkeypatch)
    try:
        closed = []
        monkeypatch.setattr(gui.root, "destroy", lambda: closed.append(True))
        answers = []
        monkeypatch.setattr(gui, "_ask_save_discard_cancel", lambda action: answers.pop(0))

        gui.close()  # nothing to save: closes at once
        assert closed == [True]

        gui.catalog.families[0].description = "Edited"
        answers.append(None)  # Cancel
        gui.close()
        assert closed == [True] and gui.has_unsaved_changes()

        answers.append("save")
        gui.close()
        assert closed == [True, True] and not gui.has_unsaved_changes()
        assert gui_module.Catalog.load(str(path))[0].families[0].description == "Edited"

        gui.catalog.families[0].description = "Thrown away"
        answers.append("discard")
        gui.close()
        assert closed == [True, True, True]
        assert gui_module.Catalog.load(str(path))[0].families[0].description == "Edited"

        # Load asks too, and Cancel keeps the open database.
        answers.append(None)
        monkeypatch.setattr(gui_module.filedialog, "askopenfilename", lambda **_kw: pytest.fail("shouldn't ask"))
        gui.open_database()
        assert gui.catalog.families[0].description == "Thrown away"
    finally:
        monkeypatch.undo()
        root.destroy()


def test_unsaved_changes_window_has_save_discard_and_cancel(tmp_path, monkeypatch):
    root, gui, _path = open_saved_gui(tmp_path, monkeypatch)
    try:
        seen = []

        def press_discard():
            dialog = find_window(root, "Unsaved Changes")
            seen.extend(w.cget("text") for w in descendants(dialog) if isinstance(w, ttk.Button))
            find_button(dialog, "Discard").invoke()

        failures = run_in_dialog(root, press_discard)
        assert gui._ask_save_discard_cancel("closing") == "discard"
        assert not failures
        assert seen == ["Cancel", "Discard", "Save"]
    finally:
        root.destroy()


def test_closing_during_a_macro_build_waits_for_it(tmp_path, monkeypatch):
    root, gui, _path = open_saved_gui(tmp_path, monkeypatch)
    try:
        closed = []
        monkeypatch.setattr(gui.root, "destroy", lambda: closed.append(True))
        gui._macro_build_thread = object()  # a build is running
        gui.close()
        assert closed == []
        gui._macro_build_thread = None
        gui._finish_macro_build(SimpleNamespace(name="TeamMacros"), True, ["Built"])
        assert closed == [True]
    finally:
        monkeypatch.undo()
        root.destroy()


# --- Revit schedule macro -----------------------------------------------------

def test_save_installs_the_macro_in_the_only_module_in_its_namespace_and_builds_it(tmp_path, monkeypatch):
    from tests.test_revit_macro_module import make_module

    macros = tmp_path / "Macros"
    monkeypatch.setattr(gui_module, "MACROS_ROOT", macros)
    module_dir = make_module(macros, 2025, "TeamMacros", namespace="Team.Macros")
    (module_dir / "test_data.cs").write_text("// Generated by Revit Parameter Manager.\n", encoding="utf-8")
    built = []

    def fake_build(module):
        built.append(module)
        return False, ["CreateSchedulesFromDatabase.cs(12,5): error CS1002: ; expected", "The module failed to build"]

    monkeypatch.setattr(gui_module, "build_module", fake_build)
    popups = []
    monkeypatch.setattr(gui_module.messagebox, "showerror", lambda title, message, **_kw: popups.append((title, message)))
    messages = []
    gui = make_test_gui()
    monkeypatch.setattr(gui, "_append_message", messages.append)
    gui.checkpoint_path = tmp_path / "database.ddm.json"

    gui.save_checkpoint()

    installed = (module_dir / "CreateSchedulesFromDatabase.cs").read_text(encoding="utf-8")
    assert installed == (tmp_path / "database.cs").read_text(encoding="utf-8")
    assert "namespace Team.Macros" in installed
    assert "from database.ddm.json" in installed.splitlines()[0]
    assert not (module_dir / "test_data.cs").exists()
    assert "Using Revit 2025: TeamMacros for the schedule macro (the only macro module found)." in messages
    assert any("Removed older generated macro" in message for message in messages)
    # Save builds the module and shows the build's messages; a failure also pops up.
    assert [module.name for module in built] == ["TeamMacros"]
    assert "CreateSchedulesFromDatabase.cs(12,5): error CS1002: ; expected" in messages
    assert [title for title, _message in popups] == ["Macro Build Failed"]
    assert "TeamMacros module didn't build" in popups[0][1]


def test_save_builds_the_macro_in_the_background_and_queues_a_save_made_meanwhile(tmp_path, monkeypatch):
    import threading
    import time
    from tests.test_revit_macro_module import make_module

    macros = tmp_path / "Macros"
    monkeypatch.setattr(gui_module, "MACROS_ROOT", macros)
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    module_dir = make_module(macros, 2025, "TeamMacros")
    release = threading.Event()
    builds = []

    def slow_build(module):
        builds.append((module.name, (module_dir / "CreateSchedulesFromDatabase.cs").read_text(encoding="utf-8")))
        release.wait(10)
        if len(builds) == 1:
            return True, ["build 1 done"]
        return False, ["build 2 done", "The module failed to build"]

    monkeypatch.setattr(gui_module, "build_module", slow_build)
    popups = []
    monkeypatch.setattr(gui_module.messagebox, "showerror", lambda title, message, **_kw: popups.append(title))
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        messages = []
        monkeypatch.setattr(gui, "_append_message", messages.append)
        gui.checkpoint_path = tmp_path / "database.ddm.json"

        def pump_until(condition):
            deadline = time.monotonic() + 10
            while not condition() and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert condition()

        gui.save_checkpoint()
        # Save returns while the build runs; the other files are already written.
        pump_until(lambda: len(builds) == 1)
        assert gui._macro_build_thread is not None
        for name in ("database.ddm.csv", "database.rfps", "database.txt"):
            assert (tmp_path / name).exists(), name
        assert any("Building TeamMacros in the background" in message for message in messages)

        # Saving again mid-build doesn't touch the module until the build finishes.
        gui.catalog.schedules[0].view_template = "Changed Template"  # shows in the macro
        gui.save_checkpoint()
        assert any("still building; this save's macro will be installed" in message for message in messages)
        assert len(builds) == 1

        release.set()
        pump_until(lambda: len(builds) == 2 and gui._macro_build_thread is None)
        assert "build 1 done" in messages and "build 2 done" in messages
        assert builds[0][1] != builds[1][1]  # the queued save's macro was installed before the second build
        assert popups == ["Macro Build Failed"]  # only the second build failed
    finally:
        release.set()
        root.destroy()


def test_save_uses_the_remembered_module_and_says_when_none_is_chosen(tmp_path, monkeypatch):
    from tests.test_revit_macro_module import make_module

    macros = tmp_path / "Macros"
    monkeypatch.setattr(gui_module, "MACROS_ROOT", macros)
    first = make_module(macros, 2025, "AlphaMacros")
    second = make_module(macros, 2026, "BetaMacros")
    monkeypatch.setattr(gui_module, "build_module", lambda module: (True, [f"Built {module.name}"]))
    messages = []
    gui = make_test_gui()
    monkeypatch.setattr(gui, "_append_message", messages.append)
    gui.checkpoint_path = tmp_path / "database.ddm.json"

    # Two modules, none chosen, no window to ask in: nothing is installed.
    gui.save_checkpoint()
    assert any("choose a macro module with Revit Macro Settings" in message for message in messages)
    assert not (first / "CreateSchedulesFromDatabase.cs").exists()

    gui_module.choose_module(
        next(m for m in gui_module.find_macro_modules(macros) if m.name == "AlphaMacros"), gui_module.USER_SETTINGS_PATH
    )
    gui.save_checkpoint()
    assert (first / "CreateSchedulesFromDatabase.cs").exists()
    assert not (second / "CreateSchedulesFromDatabase.cs").exists()
    assert "Built AlphaMacros" in messages


def test_macro_settings_dialog_lists_modules_and_remembers_the_choice(tmp_path, monkeypatch):
    from tests.test_revit_macro_module import make_module

    macros = tmp_path / "Macros"
    monkeypatch.setattr(gui_module, "MACROS_ROOT", macros)
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    make_module(macros, 2025, "AlphaMacros")
    make_module(macros, 2026, "BetaMacros")
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        find_button(root, "Revit Macro Settings")
        seen = []

        def pick():
            dialog = find_window(root, "Revit Macro Settings")
            combo = next(w for w in descendants(dialog) if isinstance(w, ttk.Combobox))
            seen.extend(combo.cget("values"))
            combo.set("Revit 2025: AlphaMacros")
            find_button(dialog, "Use This Module").invoke()

        failures = run_in_dialog(root, pick)
        chosen = gui.open_macro_settings()
        assert not failures
        assert list(seen) == ["Revit 2026: BetaMacros", "Revit 2025: AlphaMacros"]
        assert chosen.name == "AlphaMacros"
        modules = gui_module.find_macro_modules(macros)
        assert gui_module.chosen_module(modules, gui_module.USER_SETTINGS_PATH).name == "AlphaMacros"
    finally:
        root.destroy()


def test_build_failure_popup_lists_at_most_ten_errors(monkeypatch):
    from revit_macro_module import MacroModule

    popups = []
    monkeypatch.setattr(gui_module.messagebox, "showerror", lambda title, message, **_kw: popups.append(message))
    gui = make_test_gui()
    module = MacroModule(2025, "TeamMacros", None, "TeamMacros")
    errors = [f"A.cs({n},1): error CS0001: bad" for n in range(1, 14)]

    gui._show_macro_build_failure(module, errors + ["The module failed to build (see above)."])

    assert "A.cs(10,1)" in popups[0] and "A.cs(11,1)" not in popups[0]
    assert popups[0].endswith("... and 3 more (see Messages).")

    # Nothing to list (dotnet missing): the reason itself is shown.
    gui._show_macro_build_failure(module, ["The .NET SDK isn't installed."])
    assert popups[1].endswith("The .NET SDK isn't installed.")


def test_save_without_any_macro_module_says_how_to_make_one(tmp_path, monkeypatch):
    messages = []
    gui = make_test_gui()
    monkeypatch.setattr(gui, "_append_message", messages.append)
    gui.checkpoint_path = tmp_path / "database.ddm.json"

    gui.save_checkpoint()

    assert "namespace RevitMacros" in (tmp_path / "database.cs").read_text(encoding="utf-8")
    assert any("No Revit 2025 (or later) application macro module was found" in message for message in messages)


def test_create_github_ticket_opens_a_new_issue_with_the_app_version(monkeypatch):
    opened = []
    monkeypatch.setattr(gui_module.webbrowser, "open", lambda url: opened.append(url) or True)
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        gui.open_new_ticket()
    finally:
        root.destroy()
    assert len(opened) == 1
    assert opened[0].startswith("https://github.com/gmclove/design-data-manager/issues/new?body=App+Version")
