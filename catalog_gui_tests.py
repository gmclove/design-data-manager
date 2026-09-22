import importlib.util
from pathlib import Path
import tkinter as tk

import pandas as pd

from parameter_catalog_gui import ParameterCatalogGUI


def load_model_module():
    module_path = Path(__file__).with_name("revit-parameter-manager.py")
    spec = importlib.util.spec_from_file_location("revit_parameter_manager_model", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyText:
    def delete(self, *args, **kwargs):
        pass

    def insert(self, *args, **kwargs):
        pass


def load_test_case():
    params_df = pd.read_csv("test_data/parameter_catalog_test_data.csv", keep_default_na=False)
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
    ]
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
        ]
    )

    gui = ParameterCatalogGUI.__new__(ParameterCatalogGUI)
    gui.params_df = params_df
    gui.families_df = families_df
    gui.family_param_links_df = family_param_links_df
    gui.warning_text = DummyText()
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
        ]
    )
    return gui


def test_schedule_name_is_required_and_unique():
    module = load_model_module()
    Schedule = module.Schedule

    first = Schedule(name="Mechanical Schedule")
    assert first.name == "Mechanical Schedule"

    try:
        Schedule(name="Mechanical Schedule")
        raise AssertionError("Duplicate schedule names should fail")
    except ValueError:
        pass


def test_validation_flags_missing_references():
    gui = load_test_case()
    gui.validate_all()

    missing_ref_row = gui.params_df[gui.params_df["name"] == "MissingRef"].iloc[0]
    assert str(missing_ref_row["status"]).lower() == "error"
    assert "GhostParam" in str(missing_ref_row["validation_message"])


def test_family_validation_accepts_associated_params():
    gui = load_test_case()
    gui.validate_all()

    family_a = gui.families_df[gui.families_df["name"] == "Family_A"].iloc[0]
    assert str(family_a["status"]).lower() == "ready"
    assert str(family_a["validation_message"]).strip() == ""


def test_family_validation_detects_missing_link():
    gui = load_test_case()
    gui.family_param_links_df = gui.family_param_links_df[gui.family_param_links_df["family_name"] != "Family_A"]
    gui.validate_all()

    family_a = gui.families_df[gui.families_df["name"] == "Family_A"].iloc[0]
    assert str(family_a["status"]).lower() == "error"


def test_gui_cell_edit_updates_dataframe():
    gui = load_test_case()
    gui._apply_cell_value("params", 0, "formula", "Width + Height")

    assert gui.params_df.at[0, "formula"] == "Width + Height"
    assert gui.params_df.at[0, "status"] == "Ready"


def test_group_override_entry_updates_schedule_table():
    gui = load_test_case()
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


def test_wide_variety_examples_cover_multiple_families_and_schedules():
    gui = load_test_case()
    gui.validate_all()

    assert len(gui.params_df) >= 15
    assert len(gui.families_df) >= 10
    assert len(gui.family_groups_df) >= 10
    assert set(gui.families_df["name"]) >= {"Family_A", "Family_B", "Family_C", "Family_D", "Family_E", "Family_F", "Family_G", "Family_H", "Family_I", "Family_J"}
    assert set(gui.family_groups_df["group_name"]) >= {"Schedule A", "Envelope Schedule", "Mechanical Schedule", "Facade Review", "Opening Schedule"}
    assert gui.family_groups_df["status"].str.lower().isin(["ready"]).all()


def test_expanded_case_includes_more_family_and_schedule_variants():
    gui = load_test_case()
    assert "Family_H" in gui.families_df["name"].tolist()
    assert "Family_I" in gui.families_df["name"].tolist()
    assert "Family_J" in gui.families_df["name"].tolist()
    assert "Mechanical Schedule" in gui.family_groups_df["group_name"].tolist()
    assert "Facade Review" in gui.family_groups_df["group_name"].tolist()
    assert "Opening Schedule" in gui.family_groups_df["group_name"].tolist()


def test_gui_has_more_interface_playground_examples_for_manual_review():
    gui = load_test_case()
    assert "HeadHeight" in gui.params_df["name"].tolist()
    assert "FacadeRatio" in gui.params_df["name"].tolist()
    assert "Family_F" in gui.families_df["name"].tolist()
    assert "Family_G" in gui.families_df["name"].tolist()
    assert gui.family_groups_df["family_name"].str.contains("Family_F|Family_G").any()


def test_main_tabs_are_parameters_families_and_schedules():
    root = tk.Tk()
    root.withdraw()
    try:
        gui = ParameterCatalogGUI(root)
        tab_texts = [gui.notebook.tab(tab_id, "text") for tab_id in gui.notebook.tabs()]
        assert tab_texts == ["Parameters", "Families", "Schedules"]
    finally:
        root.destroy()


if __name__ == "__main__":
    test_validation_flags_missing_references()
    test_family_validation_accepts_associated_params()
    test_family_validation_detects_missing_link()
    print("GUI smoke tests passed")
