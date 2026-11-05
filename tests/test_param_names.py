"""The parameter naming scheme: the master workbook's Parameter Name Editor."""

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

import ddm_gui as gui_module
from ddm_gui import DDMGUI
from ddm_tables import catalog_from_tables, read_database_csv, write_database_csv
from excel_import import read_name_terms
from revit_parameter_manager import Catalog, build_param_name, split_param_name


def terms(parent="", child="", descriptor="", clarifier="", units=""):
    return {
        "parent_category": parent, "child_category": child, "descriptor": descriptor,
        "clarifier": clarifier, "units": units,
    }


@pytest.mark.parametrize("parts, name", [
    (("SPACE", "Air", "Exh", "OccMax", "CFM"), "IPS_SPACE_Air_ExhOccMax_CFM"),  # no _ before the Clarifier
    (("EQUIP", "", "Cells", "", "QTY"), "IPS_EQUIP_Cells_QTY"),
    (("SOUND", "", "Burner", "Max", "DBA"), "IPS_SOUND_BurnerMax_DBA"),
    (("FILTER", "Final", "", "MERV_Rating", ""), "IPS_FILTER_Final_MERV_Rating"),  # Clarifier alone
    (("SPACE", "AirReq", "Transf", "_In", "CFM"), "IPS_SPACE_AirReq_Transf_In_CFM"),  # its own underscore
    (("_ARROW", "Start", "Forward", "", ""), "IPS__ARROW_Start_Forward"),
    (("SPACE", "AirReq", "Duct", "Leak ", "PRCNT"), "IPS_SPACE_AirReq_DuctLeak _PRCNT"),  # the workbook's stray space
    (("", "", "", "", ""), ""),
])
def test_names_build_as_the_workbook_formula_does(parts, name):
    assert build_param_name(terms(*parts)) == name


@pytest.mark.parametrize("name", [
    "IPS_COIL_Htg_Air_Max_CFM", "IPS_EQUIP_Cells_QTY", "IPS__ARROW_End", "IPS_NAME", "IPS_COIL_Htg_PD_IN_WC",
    "IPS_A__B", "IPS_SPACE_AirReq_DuctLeak _PRCNT", "IPS_TAG_TERM_1_Prefix", "IPS_Low-Wall-Return_X",
])
def test_a_guess_always_rebuilds_the_name(name):
    assert build_param_name(split_param_name(name, {"IN_WC", "CFM"})) == name


def test_a_guess_uses_known_units_and_capitals():
    assert split_param_name("IPS_COIL_Htg_PD_IN_WC")["units"] == "WC"
    guess = split_param_name("IPS_COIL_Htg_PD_IN_WC", {"IN_WC"})
    assert guess == terms("COIL", "Htg", "PD", "", "IN_WC")
    assert split_param_name("IPS__ARROW_End") == terms("_ARROW", "", "End")
    assert split_param_name("Rough Width") is None
    assert split_param_name("IPS_") is None


def test_terms_never_rename_and_a_rename_outdates_them():
    catalog = Catalog()
    param = catalog.add_param("IPS_FAN_RA_Hertz_HZ", "Text")
    guid = param.guid
    assert not param.has_name_terms
    assert param.name_terms == terms("FAN", "RA", "Hertz", "", "HZ")  # a guess

    assert not param.set_name_terms(terms("FAN", "SA", "Hertz", "", "HZ"))  # would build another name
    assert not param.has_name_terms
    assert param.set_name_terms(terms("FAN", "RA", "Her", "tz", "HZ"))
    assert param.name_terms["clarifier"] == "tz"
    assert (param.name, param.guid) == ("IPS_FAN_RA_Hertz_HZ", guid)

    param.rename("IPS_FAN_SA_Hertz_HZ", keep_guid=True)
    assert not param.has_name_terms
    assert param.name_terms == terms("FAN", "SA", "Hertz", "", "HZ")
    assert "name_terms" not in param.to_dict()


def test_a_name_outside_the_scheme_has_blank_terms():
    param = Catalog().add_param("Rough Width", "Text")
    assert param.name_terms == terms()
    assert build_param_name(param.name_terms) == ""


def test_term_values_list_what_is_in_use():
    catalog = Catalog()
    catalog.add_param("IPS_FAN_RA_Hertz_HZ", "Text").set_name_terms(terms("FAN", "RA", "Hertz", "", "HZ"))
    catalog.add_param("IPS_COIL_Clg_Flow_GPM", "Text")
    catalog.add_param("Rough Width", "Text")
    assert catalog.param_term_values("parent_category") == ["COIL", "FAN"]
    assert catalog.param_term_values("units") == ["GPM", "HZ"]


def term_catalog():
    catalog = Catalog()
    catalog.add_param("IPS_SPACE_AirReq_DuctLeak _PRCNT", "Text").set_name_terms(
        terms("SPACE", "AirReq", "Duct", "Leak ", "PRCNT"))
    catalog.add_param("IPS_EQUIP_Cells_QTY", "Text")
    return catalog


def test_terms_survive_a_json_save(tmp_path):
    path = tmp_path / "database.ddm.json"
    term_catalog().save(path)
    loaded = Catalog.load(path)
    loaded = loaded[0] if isinstance(loaded, tuple) else loaded
    assert loaded.params[0].name_terms == terms("SPACE", "AirReq", "Duct", "Leak ", "PRCNT")
    assert loaded.params[0].has_name_terms and not loaded.params[1].has_name_terms


def test_terms_survive_a_csv_save(tmp_path):
    path = tmp_path / "database.ddm.csv"
    write_database_csv(term_catalog(), path)
    tables, header_groups = read_database_csv(path)
    loaded = catalog_from_tables(header_groups=header_groups, **tables)[0]
    assert loaded.params[0].name_terms == terms("SPACE", "AirReq", "Duct", "Leak ", "PRCNT")
    assert loaded.params[0].has_name_terms and not loaded.params[1].has_name_terms


def test_a_database_saved_before_terms_loads(tmp_path):
    path = tmp_path / "database.ddm.csv"
    write_database_csv(term_catalog(), path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.drop(columns=["parent_category", "child_category", "descriptor", "clarifier", "units"]).to_csv(path, index=False)
    tables, header_groups = read_database_csv(path)
    assert not catalog_from_tables(header_groups=header_groups, **tables)[0].params[0].has_name_terms


def name_editor_workbook(path):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Parameters"
    sheet.append(["Parameter Parent Category ", "Parameter Child Category", "Parameter Descriptor",
                  "Parameter Clarifier", "Parameter Units", "Parameter Name", "Data Type", "GUID"])
    sheet.append(["SPACE", "Air", "Exh", "OccMax", "CFM", "IPS_SPACE_Air_ExhOccMax_CFM", "Number", "guid-1"])
    sheet.append(["SPACE", "AirReq", "Duct", "Leak ", "PRCNT", "IPS_SPACE_AirReq_DuctLeak _PRCNT", "Text", "guid-2"])
    sheet.append(["WRONG", "", "", "", "", "IPS_FAN_RA_Hertz_HZ", "Text", "guid-3"])
    for name in ("Families", "Backstage"):
        wb.create_sheet(name)
    wb.save(path)


def test_the_workbook_terms_fill_an_existing_catalog_without_renaming(tmp_path):
    path = tmp_path / "master.xlsx"
    name_editor_workbook(path)
    catalog = Catalog()
    exh = catalog.add_param("IPS_SPACE_Air_ExhOccMax_CFM", "Number")
    leak = catalog.add_param("IPS_SPACE_AirReq_DuctLeak _PRCNT", "Text")
    fan = catalog.add_param("IPS_FAN_RA_Hertz_HZ", "Text")
    extra = catalog.add_param("IPS_DUCT_Dia_IN", "Text")
    before = [(param.name, param.guid) for param in catalog.params]

    recorded, problems = read_name_terms(path, catalog)

    assert recorded == 2
    assert problems == ["Parameters: 'IPS_FAN_RA_Hertz_HZ' doesn't match its Parameter Name Editor terms; terms left out."]
    assert [(param.name, param.guid) for param in catalog.params] == before
    assert exh.name_terms == terms("SPACE", "Air", "Exh", "OccMax", "CFM")
    assert leak.name_terms["clarifier"] == "Leak "  # kept, so it still builds the name
    assert not fan.has_name_terms and not extra.has_name_terms


# --- the builder --------------------------------------------------------------

@pytest.fixture
def builder_gui():
    root = tk.Tk()
    root.withdraw()
    gui = DDMGUI.__new__(DDMGUI)
    gui.root = root
    gui.catalog = Catalog()
    gui.param_tree = None
    gui.validate_all = lambda: None
    gui.messages = []
    gui._append_message = gui.messages.append
    gui.catalog.add_param("IPS_FAN_RA_Hertz_HZ", "Text", guid="guid-1").set_name_terms(
        terms("FAN", "RA", "Hertz", "", "HZ"))
    gui.catalog.add_param("IPS_COIL_Clg_Flow_GPM", "Text", guid="guid-2")
    gui.catalog.add_param("Rough Width", "Text", guid="guid-3")
    yield gui
    root.destroy()


def no_guid_question(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("asked about the GUID")
    monkeypatch.setattr(gui_module.messagebox, "askyesnocancel", fail)


@pytest.mark.parametrize("row", [0, 1, 2])
def test_opening_and_saving_changes_no_name_or_guid(builder_gui, monkeypatch, row):
    no_guid_question(monkeypatch)
    param = builder_gui.catalog.params[row]
    name, guid = param.name, param.guid
    window = builder_gui._open_param_name_builder(row)
    assert window.name_var.get() == name
    window.save()
    assert (param.name, param.guid) == (name, guid)
    assert builder_gui.messages == []
    assert not window.winfo_exists()


def test_guessed_terms_can_be_corrected_without_a_rename(builder_gui, monkeypatch):
    no_guid_question(monkeypatch)
    param = builder_gui.catalog.params[1]
    window = builder_gui._open_param_name_builder(1)
    assert window.term_vars["descriptor"].get() == "Flow"
    window.term_vars["descriptor"].set("Fl")
    window.term_vars["clarifier"].set("ow")
    assert window.name_var.get() == "IPS_COIL_Clg_Flow_GPM"
    window.save()
    assert param.has_name_terms and param.name_terms["clarifier"] == "ow"
    assert param.guid == "guid-2"


def test_a_changed_term_renames_after_the_guid_question(builder_gui, monkeypatch):
    asked = []
    monkeypatch.setattr(gui_module.messagebox, "askyesnocancel", lambda *_a, **_k: asked.append(True) or False)
    param = builder_gui.catalog.params[0]
    window = builder_gui._open_param_name_builder(0)
    window.term_vars["child_category"].set("SA")
    assert window.name_var.get() == "IPS_FAN_SA_Hertz_HZ"
    window.save()
    assert asked == [True]
    assert (param.name, param.guid) == ("IPS_FAN_SA_Hertz_HZ", "guid-1")  # "No" keeps the GUID
    assert param.name_terms["child_category"] == "SA" and param.has_name_terms
    assert builder_gui.messages == ["Renamed parameter 'IPS_FAN_RA_Hertz_HZ' to 'IPS_FAN_SA_Hertz_HZ'."]


def test_cancelling_the_guid_question_changes_nothing(builder_gui, monkeypatch):
    monkeypatch.setattr(gui_module.messagebox, "askyesnocancel", lambda *_a, **_k: None)
    param = builder_gui.catalog.params[0]
    window = builder_gui._open_param_name_builder(0)
    window.term_vars["child_category"].set("SA")
    window.save()
    assert param.name == "IPS_FAN_RA_Hertz_HZ"
    assert param.name_terms["child_category"] == "RA"
    assert window.winfo_exists()  # still open to fix the name


def test_long_names_get_the_workbook_warning(builder_gui):
    window = builder_gui._open_param_name_builder(0)
    assert window.long_name.get() == ""
    window.term_vars["descriptor"].set("AVeryLongDescriptorForThisFan")
    assert "Long Name Detected" in window.long_name.get()


def test_add_parameter_builds_a_new_parameter(builder_gui, monkeypatch):
    no_guid_question(monkeypatch)
    window = builder_gui._open_param_name_builder()
    assert window.name_var.get() == ""
    assert window.new_fields["dtype"].get() == "Text"
    for term, value in terms("FAN", "SA", "Press", "Max", "IN_WC").items():
        window.term_vars[term].set(value)
    window.new_fields["instance_param"].set("Type")
    window.save()
    param = builder_gui.catalog.get_param("IPS_FAN_SA_PressMax_IN_WC")
    assert param is not None and param.has_name_terms and param.guid
    assert param.instance_param is False
    assert builder_gui.messages == ["Added parameter 'IPS_FAN_SA_PressMax_IN_WC'."]
    assert not window.winfo_exists()


@pytest.mark.parametrize("fill", [{}, {"parent_category": "FAN", "child_category": "RA", "descriptor": "Hertz", "units": "HZ"}])
def test_add_parameter_refuses_a_blank_or_used_name(builder_gui, monkeypatch, fill):
    errors = []
    monkeypatch.setattr(gui_module.messagebox, "showerror", lambda title, message, **_k: errors.append(message))
    window = builder_gui._open_param_name_builder()
    for term, value in fill.items():
        window.term_vars[term].set(value)
    window.save()
    assert len(errors) == 1 and len(builder_gui.catalog.params) == 3
    assert window.winfo_exists()


def test_clicking_a_name_and_the_add_button_open_the_builder_in_the_real_window(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_module, "DEFAULT_CHECKPOINT_PATH", tmp_path / "missing" / "database.ddm.json")
    root = tk.Tk()
    root.geometry("1200x800")
    try:
        gui = DDMGUI(root)
        gui.notebook.select(gui.params_tab)
        root.update()
        tree = gui.param_tree
        first = gui.catalog.params[0]
        x, y, width, height = tree.bbox(tree.get_children()[0], "#1")
        opened = []
        original = gui._open_param_name_builder
        monkeypatch.setattr(gui, "_open_param_name_builder", lambda *args: opened.append(original(*args)) or opened[-1])

        gui._on_tree_click(SimpleNamespace(x=x + width // 2, y=y + height // 2), "params")
        assert opened[0].name_var.get() == first.name
        assert getattr(gui, "_pending_tree_edit", None) is None  # no in-place edit is on its way
        opened[0].destroy()

        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    yield child
                yield from buttons(child)

        # The button was bound before the method was wrapped, so use its own command.
        add = next(button for button in buttons(gui.params_tab) if button.cget("text") == "Add Parameter...")
        add.invoke()
        window = next(child for child in root.winfo_children()
                      if isinstance(child, tk.Toplevel) and child.title() == "Parameter Name Builder")
        window.term_vars["parent_category"].set("FAN")
        window.term_vars["descriptor"].set("Brand")
        gui._search_vars["params"].set("no such parameter")
        count = len(gui.catalog.params)
        window.save()
        root.update()
        assert len(gui.catalog.params) == count + 1
        assert gui.catalog.params[-1].name == "IPS_FAN_Brand"
        # The new row is selected and in view, even though a search was hiding it.
        assert gui._search_vars["params"].get() == ""
        assert tree.selection() == (str(count),)
    finally:
        root.destroy()
