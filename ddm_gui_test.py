import importlib.util
import pickle
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pandas as pd

import ddm_gui as gui_module
from config.app_paths import (
    DATA_DIR,
    DEMO_DATA_PATH,
    TEST_DATABASE_CSV_PATH,
    get_database_output_paths,
)
from ddm_gui import DDMGUI, ScheduleHeaderCanvas


def load_model_module():
    module_path = Path(__file__).with_name("revit_parameter_manager.py")
    spec = importlib.util.spec_from_file_location("revit_parameter_manager_model", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyText:
    def delete(self, *args, **kwargs):
        pass

    def insert(self, *args, **kwargs):
        pass


def make_test_gui():
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

    gui = DDMGUI.__new__(DDMGUI)
    gui.params_df = params_df
    gui.families_df = families_df
    gui.family_param_links_df = family_param_links_df
    gui.warning_text = DummyText()
    gui.checkpoint_path = gui_module.DEFAULT_CHECKPOINT_PATH
    gui.param_tree = None
    gui.family_tree = None
    gui.link_tree = None
    gui.group_tree = None
    gui.family_groups_df = pd.DataFrame(
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
    return gui


def test_schedule_name_is_required_and_unique():
    module = load_model_module()
    catalog = module.Catalog()

    first = catalog.add_schedule("Mechanical Schedule")
    assert first.name == "Mechanical Schedule"

    try:
        catalog.add_schedule("Mechanical Schedule")
        raise AssertionError("Duplicate schedule names should fail")
    except ValueError:
        pass

    try:
        module.Schedule(name="   ")
        raise AssertionError("Blank schedule names should fail")
    except ValueError:
        pass


def test_schedule_header_text_override_uses_parameter_default_and_round_trips():
    module = load_model_module()
    default_param = module.Param("Width", "Length")
    custom_param = module.Param("Height", "Length", header_text="Overall Height")
    family = module.Fam(name="Header Family", category="Doors", params=[default_param, custom_param])
    schedule = module.Schedule(name="Header Schedule", fams=[family])

    default_header = next(param.header_text for param in schedule.params if param.name == "Width")
    assert default_header == "Width"
    assert next(param.header_text for param in schedule.params if param.name == "Height") == "Overall Height"
    assert schedule.override_param("Height", header_text="")
    assert next(param.header_text for param in schedule.params if param.name == "Height") == "Overall Height"
    assert schedule.override_param("Height", header_text="Schedule Height")
    assert next(param.header_text for param in schedule.params if param.name == "Height") == "Schedule Height"

    serialized_schedule = schedule.to_dict()
    restored = module.Schedule.from_dict(serialized_schedule)
    assert next(param.header_text for param in restored.params if param.name == "Height") == "Schedule Height"


def test_parameter_grid_column_width_can_be_overridden_per_schedule():
    module = load_model_module()
    width_param = module.Param("Width", "Length", grid_column_width=1.25)
    family = module.Fam(name="Width Family", category="Doors", params=[width_param])
    schedule = module.Schedule(name="Width Schedule", fams=[family])

    assert next(param.grid_column_width for param in schedule.params if param.name == "Width") == 1.25
    schedule.override_param("Width", grid_column_width=2.5)
    assert next(param.grid_column_width for param in schedule.params if param.name == "Width") == 2.5

    serialized_schedule = schedule.to_dict()
    restored = module.Schedule.from_dict(serialized_schedule)
    assert restored.grid_column_width_overrides == {"Width": 2.5}
    restored.override_param("Width", grid_column_width=None)
    assert next(param.grid_column_width for param in restored.params if param.name == "Width") == 1.25


def test_parameter_name_is_required_and_supplied_guid_is_preserved():
    module = load_model_module()
    parameter = module.Param("Width", "Length", guid="existing-guid")
    assert parameter.guid == "existing-guid"

    for name in (None, "", "   "):
        try:
            module.Param(name, "Text")
            raise AssertionError("Blank parameter names should fail")
        except ValueError as exc:
            assert "name is required" in str(exc).lower()

    try:
        parameter.name = "   "
        raise AssertionError("Renaming to a blank name should fail")
    except ValueError as exc:
        assert "name is required" in str(exc).lower()
    assert parameter.name == "Width"

    family = module.Fam(name="   ", params=[module.Param("Custom", "Text")])
    assert family.status == "Error"
    assert "name is required" in family.validation_message


def test_family_validation_rejects_duplicate_parameters():
    module = load_model_module()
    width_a = module.Param("Width", "Length")
    width_b = module.Param("Width", "Length")

    family = module.Fam(
        name="Duplicate Parameter Family",
        category="Doors",
        params=[width_a, width_b],
    )

    assert family.status == "Error"
    assert "Duplicate parameter(s)" in family.validation_message
    assert "Width" in family.validation_message


def test_schedule_contains_a_shared_parameter_only_once():
    module = load_model_module()
    family_a = module.Fam(
        name="Schedule Family A",
        category="Doors",
        params=[module.Param("Width", "Length")],
    )
    family_b = module.Fam(
        name="Schedule Family B",
        category="Windows",
        params=[
            module.Param("Width", "Length"),
            module.Param("Height", "Length"),
        ],
    )

    schedule = module.Schedule(
        name="Unique Schedule Parameters",
        fams=[family_a, family_b],
    )

    parameter_names = [param.name for param in schedule.params]
    assert parameter_names.count("Width") == 1
    assert parameter_names.count("Height") == 1


def test_gui_rejects_invalid_width_and_defaults_blank_width():
    gui = make_test_gui()
    gui.params_df["grid_column_width"] = pd.Series(
        gui._default_grid_column_width_in,
        index=gui.params_df.index,
        dtype=object,
    )
    original_width = gui.params_df.at[0, "grid_column_width"]

    for invalid_width in ("wide", "-1", "0", "inf"):
        try:
            gui._apply_cell_value("params", 0, "grid_column_width", invalid_width)
            raise AssertionError("Invalid widths should fail")
        except ValueError:
            pass
        assert gui.params_df.at[0, "grid_column_width"] == original_width

    gui._apply_cell_value("params", 0, "grid_column_width", "")
    assert gui.params_df.at[0, "grid_column_width"] == 1.0
    assert gui.params_df.at[0, "grid_column_width"] == gui._default_grid_column_width_in
    assert gui._default_grid_column_width_in == 1.0
    assert DDMGUI._display_labels["grid_column_width"] == "Grid Column Width (in)"


def test_validation_reports_invalid_persisted_values_without_crashing():
    gui = make_test_gui()
    gui.params_df["grid_column_width"] = pd.Series(
        gui._default_grid_column_width_in,
        index=gui.params_df.index,
        dtype=object,
    )
    gui.params_df["instance_param"] = gui.params_df["instance_param"].astype(object)
    gui.params_df.at[0, "instance_param"] = "sometimes"
    gui.params_df.at[1, "grid_column_width"] = "wide"
    gui.params_df.at[2, "name"] = ""
    gui.families_df.at[0, "category"] = "Not a Revit category"
    gui.families_df.at[1, "name"] = ""

    gui.validate_all()

    assert gui.params_df.at[0, "status"] == "Error"
    assert "true or false" in gui.params_df.at[0, "validation_message"]
    assert gui.params_df.at[1, "status"] == "Error"
    assert "number in inches" in gui.params_df.at[1, "validation_message"]
    assert gui.params_df.at[2, "status"] == "Error"
    assert gui.families_df.at[0, "status"] == "Error"
    assert gui.families_df.at[1, "status"] == "Error"


def test_gui_rejects_invalid_boolean_and_validation_owned_fields():
    gui = make_test_gui()

    try:
        gui._apply_cell_value("params", 0, "instance_param", "sometimes")
        raise AssertionError("Unrecognized boolean values should fail")
    except ValueError as exc:
        assert "true or false" in str(exc).lower()

    for column_name in ("status", "validation_message"):
        try:
            gui._apply_cell_value("params", 0, column_name, "Ready")
            raise AssertionError("Validation-owned fields should not be editable")
        except ValueError as exc:
            assert "generated by validation" in str(exc).lower()


def test_sync_is_blocked_when_validation_errors_exist(monkeypatch):
    gui = make_test_gui()
    gui.params_df.at[0, "name"] = ""
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


def test_schedule_header_groups_round_trip_with_parameter_references():
    module = load_model_module()
    family = module.Fam(
        name="Grouped Header Family",
        category="Doors",
        params=[
            module.Param("Width", "Length"),
            module.Param("Height", "Length"),
            module.Param("Depth", "Length"),
        ],
    )
    schedule = module.Schedule(name="Grouped Header Schedule", fams=[family])

    schedule.add_header_group("Size", ["Width", "Height"], top_row=0, bottom_row=0)
    serialized_schedule = schedule.to_dict()
    restored = module.Schedule.from_dict(serialized_schedule)

    assert restored.header_groups == [
        {
            "caption": "Size",
            "parameter_names": ["Width", "Height"],
            "top_row": 0,
            "bottom_row": 0,
        }
    ]


def test_schedule_header_groups_reject_noncontiguous_parameters():
    module = load_model_module()
    family = module.Fam(
        name="Noncontiguous Header Family",
        category="Doors",
        params=[
            module.Param("Width", "Length"),
            module.Param("Height", "Length"),
            module.Param("Depth", "Length"),
        ],
    )
    schedule = module.Schedule(name="Noncontiguous Header Schedule", fams=[family])

    try:
        schedule.add_header_group("Outer", ["Width", "Depth"])
        raise AssertionError("Header groups must reference contiguous schedule fields")
    except ValueError as exc:
        assert "contiguous" in str(exc).lower()


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
    gui = make_test_gui()
    gui.family_param_links_df = gui.family_param_links_df[gui.family_param_links_df["family_name"] != "Family_A"]
    gui.validate_all()

    family_a = gui.families_df[gui.families_df["name"] == "Family_A"].iloc[0]
    assert str(family_a["status"]).lower() == "error"


def test_duplicate_family_parameter_link_is_validation_error():
    gui = make_test_gui()
    duplicate_link = gui.family_param_links_df[
        (gui.family_param_links_df["family_name"] == "Family_A")
        & (gui.family_param_links_df["parameter_name"] == "Length")
    ].iloc[0]
    gui.family_param_links_df = pd.concat(
        [gui.family_param_links_df, duplicate_link.to_frame().T],
        ignore_index=True,
    )

    gui.validate_all()

    family_a = gui.families_df[gui.families_df["name"] == "Family_A"].iloc[0]
    assert str(family_a["status"]).lower() == "error"
    assert "Duplicate parameter link(s): Length." in family_a["validation_message"]


def test_duplicate_schedule_entry_is_validation_error():
    gui = make_test_gui()
    duplicate_entry = gui.family_groups_df[
        (gui.family_groups_df["family_name"] == "Family_A")
        & (gui.family_groups_df["group_name"] == "Schedule A")
        & (gui.family_groups_df["parameter_name"] == "Length")
    ].iloc[0]
    gui.family_groups_df = pd.concat(
        [gui.family_groups_df, duplicate_entry.to_frame().T],
        ignore_index=True,
    )

    gui.validate_all()

    duplicate_rows = gui.family_groups_df[
        (gui.family_groups_df["family_name"] == "Family_A")
        & (gui.family_groups_df["group_name"] == "Schedule A")
        & (gui.family_groups_df["parameter_name"] == "Length")
    ]
    assert duplicate_rows["status"].str.lower().eq("error").all()
    schedule = gui._build_schedule_summary_df()
    schedule_a = schedule[schedule["name"] == "Schedule A"].iloc[0]
    assert str(schedule_a["status"]).lower() == "error"


def test_gui_cell_edit_updates_dataframe():
    gui = make_test_gui()
    gui._apply_cell_value("params", 0, "formula", "Width + Height")

    assert gui.params_df.at[0, "formula"] == "Width + Height"
    assert gui.params_df.at[0, "status"] == "Ready"


def test_parameter_guid_defaults_to_name_based_export_guid():
    gui = make_test_gui()
    gui.validate_all()

    for _, row in gui.params_df.iterrows():
        assert row["guid"] == gui_module.parameter_guid(row["name"])


def test_gui_rename_prompts_and_assigns_new_guid_or_keeps_current(monkeypatch):
    gui = make_test_gui()
    gui.validate_all()
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
    assert gui.params_df.at[0, "guid"] not in {original_guid, gui_module.parameter_guid("NewGuid")}

    try:
        gui._apply_cell_value("params", 0, "guid", "hand-typed")
        raise AssertionError("GUID should not be editable")
    except ValueError as exc:
        assert "assigned automatically" in str(exc)


def test_gui_rename_updates_every_reference_to_the_parameter(monkeypatch):
    gui = make_test_gui()
    gui.params_df = pd.DataFrame(
        [
            {"name": "Width", "header_text": "Width", "dtype": "Length", "formula": "", "instance_param": True},
            {"name": "Height", "header_text": "Clear Height", "dtype": "Length", "formula": "", "instance_param": True},
            {"name": "GlassWidth", "header_text": "GlassWidth", "dtype": "Length", "formula": "", "instance_param": True},
            {"name": "Area", "header_text": "Area", "dtype": "Area", "formula": "Width * Height + GlassWidth", "instance_param": True},
        ]
    )
    gui.family_param_links_df = pd.DataFrame(
        [
            {"family_name": "Family_A", "parameter_name": "Width"},
            {"family_name": "Family_A", "parameter_name": "GlassWidth"},
        ]
    )
    gui.family_groups_df = pd.DataFrame(
        [{"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Width", "header_text_override": "W"}]
    )
    gui.schedule_header_groups = {
        "Schedule A": [{"caption": "Size", "parameter_names": ["Width", "Height"], "top_row": 0, "bottom_row": 0}]
    }
    monkeypatch.setattr(gui_module.messagebox, "askyesnocancel", lambda *args, **kwargs: False)

    gui._apply_cell_value("params", 0, "name", "Rough Width")

    assert gui.params_df.at[0, "header_text"] == "Rough Width"
    assert gui.params_df.at[3, "formula"] == "Rough Width * Height + GlassWidth"
    assert gui.family_param_links_df["parameter_name"].tolist() == ["Rough Width", "GlassWidth"]
    assert gui.family_groups_df.at[0, "parameter_name"] == "Rough Width"
    assert gui.family_groups_df.at[0, "header_text_override"] == "W"
    assert gui.schedule_header_groups["Schedule A"][0]["parameter_names"] == ["Rough Width", "Height"]

    gui._apply_cell_value("params", 1, "name", "Tall")
    assert gui.params_df.at[1, "header_text"] == "Clear Height"

    try:
        gui._apply_cell_value("params", 1, "name", "GlassWidth")
        raise AssertionError("Renaming onto another parameter's name should fail")
    except ValueError as exc:
        assert "already in use" in str(exc)
    assert gui.params_df.at[1, "name"] == "Tall"
    assert gui.family_param_links_df["parameter_name"].tolist() == ["Rough Width", "GlassWidth"]


def test_group_override_entry_updates_schedule_table():
    gui = make_test_gui()
    gui.family_groups_df = pd.DataFrame(
        [
            {
                "family_name": "Family_A",
                "group_name": "Schedule A",
                "parameter_name": "Length",
                "override_entry": "",
                "status": "Ready",
                "validation_message": "",
            }
        ]
    )

    gui._apply_cell_value("groups", 0, "override_entry", "Override Length")

    assert gui.family_groups_df.at[0, "override_entry"] == "Override Length"
    assert str(gui.family_groups_df.at[0, "status"]).lower() == "ready"


def test_schedule_header_override_updates_all_family_rows():
    gui = make_test_gui()
    gui.family_groups_df = pd.DataFrame(
        [
            {"family_name": "Family_A", "group_name": "Schedule A", "parameter_name": "Length", "override_entry": ""},
            {"family_name": "Family_C", "group_name": "Schedule A", "parameter_name": "Length", "override_entry": ""},
        ]
    )

    gui._apply_cell_value("groups", 0, "header_text_override", "Linear Dimension")

    assert gui.family_groups_df["header_text_override"].tolist() == ["Linear Dimension", "Linear Dimension"]


def test_parameter_default_header_text_flows_into_model_snapshot():
    gui = make_test_gui()
    gui.params_df["header_text"] = gui.params_df["name"]
    gui.params_df["grid_column_width"] = 1.0
    gui.params_df.loc[gui.params_df["name"] == "Length", "header_text"] = "Linear Dimension"
    gui.params_df.loc[gui.params_df["name"] == "Length", "grid_column_width"] = 2.25

    param_models, _, _, _ = gui._build_model_validation_snapshot()

    assert next(param.header_text for param in param_models if param.name == "Length") == "Linear Dimension"
    assert next(param.grid_column_width for param in param_models if param.name == "Length") == 2.25


def test_wide_variety_examples_cover_multiple_families_and_schedules():
    gui = make_test_gui()
    gui.validate_all()

    assert len(gui.params_df) >= 18
    assert len(gui.families_df) >= 12
    assert len(gui.family_groups_df) >= 10
    assert set(gui.families_df["name"]) >= {"Family_A", "Family_B", "Family_C", "Family_D", "Family_E", "Family_F", "Family_G", "Family_H", "Family_I", "Family_J", "Family_K", "Family_L"}
    assert set(gui.family_groups_df["group_name"]) >= {"Schedule A", "Envelope Schedule", "Mechanical Schedule", "Facade Review", "Opening Schedule", "Safety and Clearance"}
    assert gui.family_groups_df["status"].str.lower().isin(["ready"]).all()


def test_expanded_case_includes_more_family_and_schedule_variants():
    gui = make_test_gui()
    assert "Family_H" in gui.families_df["name"].tolist()
    assert "Family_I" in gui.families_df["name"].tolist()
    assert "Family_J" in gui.families_df["name"].tolist()
    assert "Family_K" in gui.families_df["name"].tolist()
    assert "Family_L" in gui.families_df["name"].tolist()
    assert "Mechanical Schedule" in gui.family_groups_df["group_name"].tolist()
    assert "Facade Review" in gui.family_groups_df["group_name"].tolist()
    assert "Opening Schedule" in gui.family_groups_df["group_name"].tolist()
    safety_rows = gui.family_groups_df[gui.family_groups_df["group_name"] == "Safety and Clearance"]
    assert set(safety_rows["family_name"]) == {"Family_K", "Family_L"}
    assert set(safety_rows["parameter_name"]) == {"ClearanceHeight", "FireRating", "ServiceClearance"}


def test_gui_has_more_interface_playground_examples_for_manual_review():
    gui = make_test_gui()
    assert "HeadHeight" in gui.params_df["name"].tolist()
    assert "FacadeRatio" in gui.params_df["name"].tolist()
    assert "Family_F" in gui.families_df["name"].tolist()
    assert "Family_G" in gui.families_df["name"].tolist()
    assert gui.family_groups_df["family_name"].str.contains("Family_F|Family_G").any()


def test_schedule_summary_uses_single_value_columns_only():
    gui = make_test_gui()
    summary = gui._build_schedule_summary_df()

    assert list(summary.columns) == ["name", "family_count", "parameter_count", "status", "validation_message"]
    assert "family_name" not in summary.columns
    assert "parameter_name" not in summary.columns
    assert "Schedule A" in summary["name"].tolist()


def test_schedule_parameter_names_are_sorted_for_headers():
    schedule_rows = pd.DataFrame(
        [
            {"parameter_name": "Width"},
            {"parameter_name": "Length"},
            {"parameter_name": "Width"},
        ]
    )

    parameter_names = DDMGUI._get_schedule_parameter_names(schedule_rows)

    assert parameter_names == ["Length", "Width"]


def test_schedule_header_text_wraps_at_underscores_and_camel_case():
    canvas = object.__new__(ScheduleHeaderCanvas)
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


def test_gui_registers_header_group_on_schedule_instance():
    gui = make_test_gui()

    group = gui._add_schedule_header_group("Schedule A", ["Length", "Width"], "Dimensions")

    assert group["caption"] == "Dimensions"
    assert group["parameter_names"] == ["Length", "Width"]
    assert gui.schedule_header_groups["Schedule A"] == [group]
    assert gui.schedule_models["Schedule A"].header_groups == [group]


def test_gui_schedule_width_override_uses_and_resets_to_parameter_default():
    gui = make_test_gui()
    gui.params_df["grid_column_width"] = 1.0
    gui.family_groups_df["grid_column_width_override"] = ""
    width_row = gui.family_groups_df[
        (gui.family_groups_df["group_name"] == "Schedule A")
        & (gui.family_groups_df["parameter_name"] == "Width")
    ].index[0]
    gui.family_groups_df.at[width_row, "grid_column_width_override"] = "2.25"

    gui._add_schedule_header_group("Schedule A", ["Length", "Width"], "Dimensions")
    schedule_model = gui.schedule_models["Schedule A"]

    assert schedule_model.grid_column_width_overrides == {"Width": 2.25}
    assert next(param.grid_column_width for param in schedule_model.params if param.name == "Width") == 2.25
    assert gui._get_schedule_grid_column_width(
        gui.family_groups_df[gui.family_groups_df["group_name"] == "Schedule A"],
        "Width",
    ) == 2.25

    gui._apply_cell_value("groups", width_row, "grid_column_width_override", "")
    assert gui._get_schedule_grid_column_width(
        gui.family_groups_df[gui.family_groups_df["group_name"] == "Schedule A"],
        "Width",
    ) == 1.0


def test_schedule_popup_groups_selected_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gui_module,
        "DEFAULT_CHECKPOINT_PATH",
        tmp_path / "missing" / "test_data.ddm.pkl",
    )
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
        assert "Family_K" in gui.families_df["name"].tolist()
        assert "Family_L" in gui.families_df["name"].tolist()
        assert "ClearanceHeight" in gui.params_df["name"].tolist()
        assert "FireRating" in gui.params_df["name"].tolist()
        assert "Safety and Clearance" in gui._build_schedule_summary_df()["name"].tolist()

        gui._open_detail_window("schedule", "Schedule A")
        root.update()

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(root))
        schedule_popup = next(
            widget for widget in widgets
            if isinstance(widget, tk.Toplevel) and widget.title() == "Schedule Details: Schedule A"
        )
        popup_widgets = list(descendants(schedule_popup))
        header_grid = next(
            widget for widget in popup_widgets
            if isinstance(widget, ScheduleHeaderCanvas)
        )
        header_grid._on_double_click(
            SimpleNamespace(x=header_grid.column_widths[0] + 10, y=header_grid.header_top + 10)
        )
        root.update()
        width_dialog = next(
            widget for widget in descendants(schedule_popup)
            if isinstance(widget, tk.Toplevel) and widget.title() == "Schedule Column Settings"
        )
        width_dialog_widgets = list(descendants(width_dialog))
        width_entries = [widget for widget in width_dialog_widgets if isinstance(widget, ttk.Entry)]
        width_entries[1].insert(0, "2.25")
        width_save = next(
            widget for widget in width_dialog_widgets
            if isinstance(widget, ttk.Button) and widget.cget("text") == "Save"
        )
        width_save.invoke()

        assert gui.family_groups_df.loc[
            (gui.family_groups_df["group_name"] == "Schedule A")
            & (gui.family_groups_df["parameter_name"] == "Width"),
            "grid_column_width_override",
        ].tolist() == ["2.25"]
        assert header_grid.column_widths[1] == 108

        header_y = header_grid.header_top + 10
        header_grid._on_mouse_down(SimpleNamespace(x=10, y=header_y, state=0))
        header_grid._on_mouse_drag(
            SimpleNamespace(x=header_grid.column_width + 10, y=header_y)
        )
        assert header_grid.get_selected_parameter_names() == ["Length", "Width"]
        group_button = next(
            widget for widget in popup_widgets
            if isinstance(widget, ttk.Button) and widget.cget("text") == "Group Selected"
        )
        group_button.invoke()
        root.update()

        dialog = next(
            widget for widget in descendants(schedule_popup)
            if isinstance(widget, tk.Toplevel) and widget.title() == "Name Header Group"
        )
        dialog_widgets = list(descendants(dialog))
        entry = next(widget for widget in dialog_widgets if isinstance(widget, ttk.Entry))
        entry.insert(0, "Dimensions")
        save_button = next(
            widget for widget in dialog_widgets
            if isinstance(widget, ttk.Button) and widget.cget("text") == "Group"
        )
        save_button.invoke()

        assert gui.schedule_header_groups["Schedule A"][0]["caption"] == "Dimensions"
        assert gui.schedule_header_groups["Schedule A"][0]["parameter_names"] == ["Length", "Width"]
        assert len(header_grid.group_layout) == 1
        assert gui.schedule_models["Schedule A"].grid_column_width_overrides == {"Width": 2.25}

    finally:
        root.destroy()


def test_schedule_header_groups_persist_in_database_checkpoint(tmp_path, monkeypatch):
    gui = make_test_gui()
    gui._add_schedule_header_group("Schedule A", ["Length", "Width"], "Dimensions")
    monkeypatch.chdir(tmp_path)
    gui.checkpoint_path = tmp_path / "test_data.ddm.pkl"
    output_paths = get_database_output_paths(gui.checkpoint_path)

    gui.save_checkpoint()
    with open("test_data.ddm.pkl", "rb") as checkpoint_file:
        payload = pickle.load(checkpoint_file)
    gui.schedule_header_groups = {}
    gui.schedule_models = {}
    gui.load_checkpoint(str(tmp_path / "test_data.ddm.pkl"))

    assert payload["schedule_header_groups"]["Schedule A"][0]["caption"] == "Dimensions"
    assert gui.schedule_header_groups["Schedule A"][0]["parameter_names"] == ["Length", "Width"]
    assert output_paths["csv"].exists()
    assert output_paths["macro"].exists()
    assert "CreateSchedulesFromDatabase" in output_paths["macro"].read_text(encoding="utf-8")
    assert output_paths["rfps"].exists()
    assert "TemplateName" in output_paths["rfps"].read_text(encoding="utf-8").splitlines()[0]
    assert output_paths["shared_parameters"].exists()
    assert "*PARAM\tGUID\tNAME\tDATATYPE" in output_paths["shared_parameters"].read_text(encoding="utf-16")


def test_saved_schedule_header_groups_load_on_next_gui_start(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "test_data.ddm.pkl"
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", checkpoint_path)
    fixture_gui = make_test_gui()
    fixture_gui.schedule_header_groups = {
        "Schedule A": [{
            "caption": "Dimensions",
            "parameter_names": ["Length", "Width"],
            "top_row": 0,
            "bottom_row": 0,
        }]
    }
    fixture_gui._write_checkpoint(checkpoint_path)

    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        assert gui.schedule_header_groups["Schedule A"][0]["caption"] == "Dimensions"
        assert checkpoint_path.exists()
    finally:
        root.destroy()


def test_checkpoint_file_dialogs_save_as_and_load_selected_file(tmp_path, monkeypatch):
    gui = make_test_gui()
    gui.schedule_header_groups = {
        "Schedule A": [{"caption": "Dimensions", "parameter_names": ["Length", "Width"]}]
    }
    checkpoint_path = tmp_path / "custom_database.ddm.pkl"
    output_paths = get_database_output_paths(checkpoint_path)
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(checkpoint_path),
    )
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilename",
        lambda **kwargs: str(checkpoint_path),
    )

    gui.save_checkpoint_as()
    assert checkpoint_path.exists()
    assert output_paths["csv"].exists()
    assert output_paths["macro"].exists()
    assert output_paths["rfps"].exists()
    assert output_paths["shared_parameters"].exists()
    gui.schedule_header_groups = {}
    gui.load_checkpoint()

    assert gui.schedule_header_groups["Schedule A"][0]["caption"] == "Dimensions"


def test_csv_database_round_trip_preserves_all_tables_and_header_groups(tmp_path, monkeypatch):
    gui = make_test_gui()
    gui.schedule_header_groups = {
        "Schedule A": [{
            "caption": "Dimensions",
            "parameter_names": ["Length", "Width"],
            "top_row": 0,
            "bottom_row": 0,
        }]
    }
    csv_path = tmp_path / "database.ddm.csv"
    save_dialog_options = {}
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: save_dialog_options.update(kwargs) or str(csv_path),
    )
    gui.save_checkpoint_as()

    assert csv_path.exists()
    assert save_dialog_options["defaultextension"] == ".ddm.pkl"
    assert save_dialog_options["filetypes"][0][0] == "Pickle databases"

    loaded_gui = make_test_gui()
    monkeypatch.setattr(gui_module.filedialog, "askopenfilename", lambda **kwargs: str(csv_path))
    loaded_gui.load_checkpoint()

    assert len(loaded_gui.params_df) == len(gui.params_df)
    assert len(loaded_gui.families_df) == len(gui.families_df)
    assert len(loaded_gui.family_param_links_df) == len(gui.family_param_links_df)
    assert len(loaded_gui.family_groups_df) == len(gui.family_groups_df)
    assert bool(loaded_gui.params_df.at[0, "instance_param"])
    assert loaded_gui.schedule_header_groups == gui.schedule_header_groups


def test_demo_database_loads_from_tagged_csv():
    gui = make_test_gui()
    gui._read_database_csv(str(DEMO_DATA_PATH))

    assert len(gui.params_df) == 7
    assert len(gui.families_df) == 12
    assert len(gui.family_param_links_df) == 17
    assert len(gui.family_groups_df) == 15
    assert "Safety and Clearance" in gui.family_groups_df["group_name"].tolist()


def test_database_paths_are_configured_under_data_directory():
    assert DEMO_DATA_PATH.name == "demo_data.ddm.csv"
    assert TEST_DATABASE_CSV_PATH.name == "test_data.ddm.csv"
    assert gui_module.DEFAULT_CHECKPOINT_PATH.parent == DATA_DIR / "test_data"
    assert gui_module.DEFAULT_CHECKPOINT_PATH.name == "test_data.ddm.pkl"
    assert get_database_output_paths(gui_module.DEFAULT_CHECKPOINT_PATH) == {
        "checkpoint": DATA_DIR / "test_data" / "test_data.ddm.pkl",
        "csv": DATA_DIR / "test_data" / "test_data.ddm.csv",
        "macro": DATA_DIR / "test_data" / "test_data.cs",
        "rfps": DATA_DIR / "test_data" / "test_data.rfps",
        "shared_parameters": DATA_DIR / "test_data" / "test_data.txt",
    }


def test_database_output_paths_share_stem_for_pickle_and_csv_inputs(tmp_path):
    pickle_paths = get_database_output_paths(tmp_path / "equipment.ddm.pkl")
    csv_paths = get_database_output_paths(tmp_path / "equipment.ddm.csv")

    assert pickle_paths == csv_paths
    assert pickle_paths["checkpoint"].name == "equipment.ddm.pkl"
    assert pickle_paths["csv"].name == "equipment.ddm.csv"
    assert pickle_paths["macro"].name == "equipment.cs"
    assert pickle_paths["rfps"].name == "equipment.rfps"
    assert pickle_paths["shared_parameters"].name == "equipment.txt"


def test_legacy_parameter_csv_loads_as_parameter_only_database(tmp_path):
    gui = make_test_gui()
    legacy_csv_path = tmp_path / "legacy_parameters.csv"
    pd.DataFrame(
        [{"name": "Volume", "dtype": "Volume", "group_under": "Dimensions"}]
    ).to_csv(legacy_csv_path, index=False)
    gui.load_checkpoint(str(legacy_csv_path))

    assert "Volume" in gui.params_df["name"].tolist()
    assert gui.families_df.empty
    assert gui.family_param_links_df.empty
    assert gui.family_groups_df.empty


def test_unified_test_database_contains_seed_parameters_and_defaults():
    gui = make_test_gui()
    all_air_parameters = gui.params_df.loc[
        gui.params_df["name"].str.startswith("DDM_EQUIP_Air_")
    ]

    assert len(all_air_parameters) == 7
    assert set(all_air_parameters["dtype"]) == {"Number"}
    assert set(all_air_parameters["group_under"]) == {"Mechanical Flow"}
    assert all_air_parameters["formula"].eq("").all()
    assert all_air_parameters["instance_param"].all()
    assert set(all_air_parameters["default_value"]) == {"-999"}

    with gui_module.DEFAULT_CHECKPOINT_PATH.open("rb") as checkpoint_file:
        checkpoint = pickle.load(checkpoint_file)
    checkpoint_air_parameters = checkpoint["params"].loc[
        checkpoint["params"]["name"].str.startswith("DDM_EQUIP_Air_")
    ]
    assert len(checkpoint_air_parameters) == 7
    assert set(checkpoint_air_parameters["default_value"]) == {"-999"}


def test_schedule_header_display_prefers_override_to_parameter_default():
    gui = make_test_gui()
    gui.params_df["header_text"] = gui.params_df["name"]
    gui.params_df.loc[gui.params_df["name"] == "Length", "header_text"] = "Linear Dimension"
    schedule_rows = pd.DataFrame(
        [{"parameter_name": "Length", "header_text_override": ""}]
    )

    assert gui._get_schedule_header_text(schedule_rows, "Length") == "Linear Dimension"
    schedule_rows.at[0, "header_text_override"] = "Schedule Length"
    assert gui._get_schedule_header_text(schedule_rows, "Length") == "Schedule Length"


if __name__ == "__main__":
    test_validation_flags_missing_references()
    test_family_validation_accepts_associated_params()
    test_family_validation_detects_missing_link()
    print("GUI smoke tests passed")
