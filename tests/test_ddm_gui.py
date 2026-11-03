import pickle
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pandas as pd
import pytest

import ddm_gui as gui_module
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
    assert f"Parameter '{first}': Instance Param must be true or false" in issues
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
    assert str(family_a["status"]).lower() == "error"


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
    assert DDMGUI._display_labels["grid_column_width"] == "Grid Column Width (in)"


def test_gui_rejects_invalid_boolean_and_validation_owned_fields():
    gui = make_test_gui()

    with pytest.raises(ValueError, match="(?i)true or false"):
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
    assert gui.schedule_header_groups["Schedule A"][0]["parameter_names"] == ["Height", "Rough Width"]

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

    assert [row["section"] for row in rows if row["section"]] == ["Parameter", "All Families", "F1", "F2", "F3"]
    assert cells(rows, "Name", "Parameter") == [("Width", "set", False)]
    assert cells(rows, "Default Value", "Parameter") == [("1", "set", False)]
    assert cells(rows, "Default Value", "All Families") == [("(Varies)", "inherited", True)]
    assert cells(rows, "Default Value", "F1") == [("5", "inherited", True)]
    assert cells(rows, "Default Value", "F2") == [("9", "set", True)]
    assert cells(rows, "Default Value", "F3") == [("1", "inherited", True)]
    # Formula and group under belong to the family: shown in a schedule, not editable there.
    assert cells(rows, "Formula", "F3") == [("Height * 2", "inherited", False)]
    assert cells(rows, "Group Under", "F3") == [("", "inherited", False)]


def test_all_families_row_sets_every_familys_schedule_value_at_once(monkeypatch):
    gui = three_family_gui()
    asked = []
    monkeypatch.setattr(gui, "_ask_override_scope", answering({}, asked))
    schedule = gui.catalog.get_schedule("S1")

    assert cells(gui._schedule_table_rows(schedule), "Default Value", "All Families") == [("", "inherited", True)]

    assert gui._override_all_families("S1", "Width", "7") is True

    assert asked == [("Width", "7", ("All Families", "S1"), [], True)]
    for family in ("F1", "F2", "F3"):
        assert gui.catalog.resolved_value((family, "S1"), "Width") == "7"
    assert gui.catalog.resolved_value(("F1", "S2"), "Width") == "1"
    assert cells(gui._schedule_table_rows(schedule), "Default Value", "All Families") == [("7", "set", True)]

    gui._override_value(("F2", "S1"), "Width", "9")
    assert cells(gui._schedule_table_rows(schedule), "Default Value", "All Families") == [("(Varies)", "inherited", True)]

    gui._override_all_families("S1", "Width", "")
    assert schedule.family_overrides == {}

    heading, _list_label, _parameter = gui._override_questions("Width", "7", ("All Families", "S1"))
    assert heading == "Override Schedule Default Value\nS1: All Families\nWidth = 7"


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

    assert cells(rows, "Group Under", "Parameter") == [("Dimensions", "set", False), ("", "set", False)]
    assert cells(rows, "Group Under", "F1") == [("Dimensions", "inherited", True), ("Construction", "set", True)]
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
    root.geometry("1200x800")
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
        assert heading_padding[3] == 2
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
        ] == ["Load", "Save", "Save As..."]
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

        # Double-click Family_A's Width value, type a new one and save.
        monkeypatch.setattr(gui, "_ask_override_scope", answering({}))
        row_index = next(
            index for index, row in enumerate(table.rows)
            if row.get("family") == "Family_A" and row.get("attribute") == "value"
        )
        table._on_double_click(SimpleNamespace(
            x=table.column_offsets[1] + 10,
            y=table.body_top + row_index * table.row_height + 5,
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


def test_family_list_edits_in_place_on_one_click_and_opens_window_on_two(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.geometry("1200x800")
    try:
        gui = DDMGUI(root)
        gui.notebook.select(gui.family_tab)
        root.update()
        tree = gui.family_tree
        fam = gui.catalog.families[0]
        column = gui._get_table_columns("families").index("description")
        x, y, width, height = tree.bbox(tree.get_children()[0], f"#{column + 1}")
        click = SimpleNamespace(x=x + width // 2, y=y + height // 2)

        # One click: after the double-click delay, an entry opens over the cell.
        gui._on_tree_click(click, "families")
        assert gui._pending_tree_edit is not None
        root.after(gui._single_click_delay_ms + 50, root.quit)
        root.mainloop()
        editor, finish = gui._tree_cell_editor
        assert editor.get() == (fam.description or "")
        editor.delete(0, tk.END)
        editor.insert(0, "Edited in place")
        finish(True)
        assert fam.description == "Edited in place"
        assert gui._tree_cell_editor is None

        # Escape-style cancel leaves the value alone.
        gui._start_tree_cell_edit(tree, "families", tree.get_children()[0], column)
        editor, finish = gui._tree_cell_editor
        editor.insert(0, "discard ")
        finish(False)
        assert fam.description == "Edited in place"

        # Two clicks: the pending edit is cancelled and the family window opens.
        gui._on_tree_click(click, "families")
        gui._on_family_tree_double_click(click)
        assert gui._pending_tree_edit is None
        root.update()
        find_window(root, "Family Details")
        assert getattr(gui, "_tree_cell_editor", None) is None
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
        find_window(root, "Edit Default Header Text")
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


def test_database_paths_are_configured_under_data_directory():
    assert DEMO_DATA_PATH.name == "demo_data.ddm.csv"
    assert TEST_DATABASE_CSV_PATH.name == "test_data.ddm.csv"
    assert TEST_CHECKPOINT_PATH.parent == DATA_DIR / "test_data"
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


# --- Revit schedule macro -----------------------------------------------------

def test_save_installs_the_schedule_macro_in_the_revit_module(tmp_path, monkeypatch):
    module_dir = tmp_path / "GLoveMacros"
    module_dir.mkdir()
    (module_dir / "test_data.cs").write_text("// Generated by Revit Parameter Manager.\n", encoding="utf-8")
    monkeypatch.setattr(gui_module, "REVIT_MACRO_MODULE_DIR", module_dir)
    messages = []
    gui = make_test_gui()
    monkeypatch.setattr(gui, "_append_message", messages.append)
    gui.checkpoint_path = tmp_path / "database.ddm.json"

    gui.save_checkpoint()

    installed = (module_dir / "CreateSchedulesFromDatabase.cs").read_text(encoding="utf-8")
    assert installed == (tmp_path / "database.cs").read_text(encoding="utf-8")
    assert "from database.ddm.json" in installed.splitlines()[0]
    assert not (module_dir / "test_data.cs").exists()
    assert any("Removed older generated macro" in message for message in messages)
    assert any("Build the GLoveMacros module" in message for message in messages)


def test_save_without_the_revit_module_says_to_copy_the_macro(tmp_path, monkeypatch):
    messages = []
    gui = make_test_gui()
    monkeypatch.setattr(gui, "_append_message", messages.append)
    gui.checkpoint_path = tmp_path / "database.ddm.json"

    gui.save_checkpoint()

    assert (tmp_path / "database.cs").exists()
    assert any("copy the macro into it by hand" in message for message in messages)
