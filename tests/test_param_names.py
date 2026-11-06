"""Parameter names: terms and a shared format, reproducing the master workbook's names."""

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
from revit_parameter_manager import (
    DEFAULT_PARAM_NAME_FORMAT, Catalog, build_param_name, split_param_name, upgrade_name_terms,
)


def terms(parent="", child="", descriptor="", clarifier="", units="", company="IPS"):
    return {
        "company_code": company, "parent_category": parent, "child_category": child,
        "descriptor": descriptor, "clarifier": clarifier, "units": units,
    }


def workbook_terms(*parts):
    """Terms as the workbook holds them: no Company Code."""
    found = terms(*parts)
    del found["company_code"]
    return found


@pytest.mark.parametrize("parts, name", [
    (("SPACE", "Air", "Exh", "OccMax", "CFM"), "IPS_SPACE_Air_ExhOccMax_CFM"),  # no _ before the Clarifier
    (("EQUIP", "", "Cells", "", "QTY"), "IPS_EQUIP_Cells_QTY"),
    (("SOUND", "", "Burner", "Max", "DBA"), "IPS_SOUND_BurnerMax_DBA"),
    (("SPACE", "AirReq", "Transf", "_In", "CFM"), "IPS_SPACE_AirReq_Transf_In_CFM"),  # its own underscore
    (("_ARROW", "Start", "Forward", "", ""), "IPS__ARROW_Start_Forward"),
    (("SPACE", "AirReq", "Duct", "Leak ", "PRCNT"), "IPS_SPACE_AirReq_DuctLeak _PRCNT"),  # spaces are kept
])
def test_the_default_format_builds_the_workbook_names(parts, name):
    assert build_param_name(terms(*parts)) == name
    assert build_param_name(upgrade_name_terms(workbook_terms(*parts))) == name


@pytest.mark.parametrize("parts, name", [
    (("FILTER", "Final", "", "MERV_Rating", ""), "IPS_FILTER_Final_MERV_Rating"),
    (("FILTER", "", "", "MERV_Rating", ""), "IPS_FILTER_MERV_Rating"),
    (("X", "Y", "", "_Z", ""), "IPS_X_Y__Z"),  # the workbook's formula gives this too
])
def test_a_workbook_clarifier_without_a_descriptor_becomes_the_descriptor(parts, name):
    upgraded = upgrade_name_terms(workbook_terms(*parts))
    assert upgraded["clarifier"] == "" and upgraded["descriptor"] == parts[3]
    assert build_param_name(upgraded) == name


def test_a_format_uses_prefixes_suffixes_order_and_use_like_family_names():
    values = terms("FAN", "RA", "Hertz", "Max", "HZ")
    custom = [dict(part) for part in DEFAULT_PARAM_NAME_FORMAT]
    assert build_param_name(values, custom) == "IPS_FAN_RA_HertzMax_HZ"
    custom[4]["prefix"] = "-"
    assert build_param_name(values, custom) == "IPS_FAN_RA_Hertz-Max_HZ"
    custom[0]["use"] = False  # the new first term loses its prefix
    assert build_param_name(values, custom) == "FAN_RA_Hertz-Max_HZ"
    custom[5]["suffix"] = "!"
    assert build_param_name(values, custom) == "FAN_RA_Hertz-Max_HZ!"
    custom[1], custom[2] = custom[2], custom[1]
    assert build_param_name(values, custom) == "RA_FAN_Hertz-Max_HZ!"
    assert build_param_name(terms(company=""), custom) == ""


@pytest.mark.parametrize("name", [
    "IPS_COIL_Htg_Air_Max_CFM", "IPS_EQUIP_Cells_QTY", "IPS__ARROW_End", "IPS_NAME", "IPS_COIL_Htg_PD_IN_WC",
    "IPS_A__B", "IPS_SPACE_AirReq_DuctLeak _PRCNT", "IPS_TAG_TERM_1_Prefix", "IPS_Low-Wall-Return_X",
])
def test_a_guess_always_rebuilds_the_name(name):
    assert build_param_name(split_param_name(name, {"IN_WC", "CFM"})) == name


def test_a_guess_uses_known_units_and_capitals():
    assert split_param_name("IPS_COIL_Htg_PD_IN_WC")["units"] == "WC"
    assert split_param_name("IPS_COIL_Htg_PD_IN_WC", {"IN_WC"}) == terms("COIL", "Htg", "PD", "", "IN_WC")
    assert split_param_name("IPS__ARROW_End") == terms("_ARROW", "", "End")
    assert split_param_name("Rough Width") is None
    assert split_param_name("IPS_") is None


def test_terms_never_rename_and_a_rename_clears_them():
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
    assert not any(param.name_terms.values())


def test_changing_the_format_renames_nothing_and_keeps_the_recorded_terms():
    catalog = Catalog()
    param = catalog.add_param("IPS_FAN_RA_Hertz_HZ", "Text")
    param.set_name_terms(terms("FAN", "RA", "Hertz", "", "HZ"))
    guid = param.guid
    custom = [dict(part) for part in catalog.param_name_format]
    custom[1]["prefix"] = "-"
    catalog.set_param_name_format(custom)
    assert (param.name, param.guid) == ("IPS_FAN_RA_Hertz_HZ", guid)
    assert param.has_name_terms and param.name_terms["parent_category"] == "FAN"


def test_term_values_list_what_is_in_use():
    catalog = Catalog()
    catalog.add_param("IPS_FAN_RA_Hertz_HZ", "Text").set_name_terms(terms("FAN", "RA", "Hertz", "", "HZ"))
    catalog.add_param("IPS_COIL_Clg_Flow_GPM", "Text")
    catalog.add_param("Rough Width", "Text")
    assert catalog.param_term_values("parent_category") == ["COIL", "FAN"]
    assert catalog.param_term_values("units") == ["GPM", "HZ"]
    assert catalog.param_term_values("company_code") == ["IPS"]


def term_catalog():
    catalog = Catalog()
    catalog.add_param("IPS_SPACE_AirReq_DuctLeak _PRCNT", "Text").set_name_terms(
        terms("SPACE", "AirReq", "Duct", "Leak ", "PRCNT"))
    catalog.add_param("IPS_EQUIP_Cells_QTY", "Text")
    return catalog


def test_terms_and_the_format_survive_a_json_save(tmp_path):
    path = tmp_path / "database.ddm.json"
    catalog = term_catalog()
    custom = [dict(part) for part in catalog.param_name_format]
    custom[4]["prefix"] = "-"
    catalog.set_param_name_format(custom)
    catalog.save(path)
    loaded = Catalog.load(path)[0]
    assert loaded.param_name_format == custom
    # Terms stay, though the format now builds a different name for them.
    assert loaded.params[0].name_terms == terms("SPACE", "AirReq", "Duct", "Leak ", "PRCNT")
    assert loaded.params[0].has_name_terms and not loaded.params[1].has_name_terms


def test_terms_survive_a_csv_save(tmp_path):
    path = tmp_path / "database.ddm.csv"
    write_database_csv(term_catalog(), path)
    tables, header_groups = read_database_csv(path)
    loaded = catalog_from_tables(header_groups=header_groups, **tables)[0]
    assert loaded.params[0].name_terms == terms("SPACE", "AirReq", "Duct", "Leak ", "PRCNT")
    assert loaded.params[0].has_name_terms and not loaded.params[1].has_name_terms


def test_a_csv_saved_before_terms_loads(tmp_path):
    path = tmp_path / "database.ddm.csv"
    write_database_csv(term_catalog(), path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.drop(columns=list(terms())).to_csv(path, index=False)
    tables, header_groups = read_database_csv(path)
    assert not catalog_from_tables(header_groups=header_groups, **tables)[0].params[0].has_name_terms


def test_terms_saved_before_company_code_are_upgraded(tmp_path):
    json_path, csv_path = tmp_path / "database.ddm.json", tmp_path / "database.ddm.csv"
    catalog = Catalog()
    catalog.add_param("IPS_FILTER_Final_MERV_Rating", "Text").set_name_terms(
        terms("FILTER", "Final", "MERV_Rating"))
    write_database_csv(catalog, csv_path)
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    row = frame["record_type"] == "parameter"
    frame.loc[row, "descriptor"], frame.loc[row, "clarifier"] = "", "MERV_Rating"
    frame.drop(columns=["company_code"]).to_csv(csv_path, index=False)
    tables, header_groups = read_database_csv(csv_path)
    from_csv = catalog_from_tables(header_groups=header_groups, **tables)[0]

    data = catalog.to_dict()
    data["params"][0]["name_terms"] = workbook_terms("FILTER", "Final", "", "MERV_Rating")
    del data["param_name_format"]
    from_json = Catalog.from_dict(data)

    for loaded in (from_csv, from_json):
        param = loaded.params[0]
        assert param.name_terms == terms("FILTER", "Final", "MERV_Rating")
        assert build_param_name(param.name_terms, loaded.param_name_format) == param.name


def name_editor_workbook(path):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Parameters"
    sheet.append(["Parameter Parent Category ", "Parameter Child Category", "Parameter Descriptor",
                  "Parameter Clarifier", "Parameter Units", "Parameter Name", "Data Type", "GUID"])
    sheet.append(["SPACE", "Air", "Exh", "OccMax", "CFM", "IPS_SPACE_Air_ExhOccMax_CFM", "Number", "guid-1"])
    sheet.append(["SPACE", "AirReq", "Duct", "Leak ", "PRCNT", "IPS_SPACE_AirReq_DuctLeak _PRCNT", "Text", "guid-2"])
    sheet.append(["FILTER", "Final", None, "MERV_Rating", None, "IPS_FILTER_Final_MERV_Rating", "Text", "guid-3"])
    sheet.append(["WRONG", "", "", "", "", "IPS_FAN_RA_Hertz_HZ", "Text", "guid-4"])
    wb.save(path)


def test_the_workbook_terms_fill_an_existing_catalog_without_renaming(tmp_path):
    path = tmp_path / "master.xlsx"
    name_editor_workbook(path)
    catalog = Catalog()
    exh = catalog.add_param("IPS_SPACE_Air_ExhOccMax_CFM", "Number")
    leak = catalog.add_param("IPS_SPACE_AirReq_DuctLeak _PRCNT", "Text")
    merv = catalog.add_param("IPS_FILTER_Final_MERV_Rating", "Text")
    fan = catalog.add_param("IPS_FAN_RA_Hertz_HZ", "Text")
    extra = catalog.add_param("IPS_DUCT_Dia_IN", "Text")
    before = [(param.name, param.guid) for param in catalog.params]

    recorded, problems = read_name_terms(path, catalog)

    assert recorded == 3
    assert problems == ["Parameters: 'IPS_FAN_RA_Hertz_HZ' doesn't match its Parameter Name Editor terms; terms left out."]
    assert [(param.name, param.guid) for param in catalog.params] == before
    assert exh.name_terms == terms("SPACE", "Air", "Exh", "OccMax", "CFM")
    assert leak.name_terms["clarifier"] == "Leak "  # kept, so it still builds the name
    assert merv.name_terms == terms("FILTER", "Final", "MERV_Rating")
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


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def label_texts(window):
    return {child.cget("text") for child in descendants(window) if isinstance(child, ttk.Label)}


def button_texts(window):
    return {child.cget("text") for child in descendants(window) if isinstance(child, ttk.Button)}


def test_both_name_builders_offer_the_same_options(builder_gui):
    builder_gui.catalog.add_family("Family_A", description="Pump")
    family = builder_gui._open_family_name_builder(0)
    param = builder_gui._open_param_name_builder(0)
    shared = {"Use", "Term", "Prefix", "Suffix", "Order", "New Name:"}
    assert shared <= label_texts(family) and shared <= label_texts(param)
    assert "Value (This Family)" in label_texts(family) and "Value (This Parameter)" in label_texts(param)
    assert {"▲", "▼", "Cancel"} <= button_texts(family) & button_texts(param)
    assert "Rename This Family" in button_texts(family) and "Rename This Parameter" in button_texts(param)
    assert {"Company Code", "Parent Category", "Child Category", "Descriptor", "Clarifier", "Units"} <= label_texts(param)
    checks = [child for child in descendants(param) if isinstance(child, ttk.Checkbutton)]
    assert len(checks) == 6


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
    format_before = [dict(part) for part in builder_gui.catalog.param_name_format]
    window = builder_gui._open_param_name_builder(0)
    window.term_vars["child_category"].set("SA")
    window.move(1, 1)
    window.save()
    assert param.name == "IPS_FAN_RA_Hertz_HZ"
    assert param.name_terms["child_category"] == "RA"
    assert builder_gui.catalog.param_name_format == format_before
    assert window.winfo_exists()  # still open to fix the name


def test_the_format_controls_rebuild_the_name_and_save_for_every_parameter(builder_gui, monkeypatch):
    monkeypatch.setattr(gui_module.messagebox, "askyesnocancel", lambda *_a, **_k: False)
    first, second = builder_gui.catalog.params[:2]
    second_name = second.name
    window = builder_gui._open_param_name_builder(0)

    window.move(2, -1)  # Child Category before Parent Category
    assert window.name_var.get() == "IPS_RA_FAN_Hertz_HZ"
    window.move(1, 1)
    assert window.name_var.get() == "IPS_FAN_RA_Hertz_HZ"
    prefixes = [child for child in descendants(window)
                if type(child) is ttk.Entry and child.cget("width") == 8]
    prefixes[2 * 5].insert(0, "-")  # the Units row's Prefix, before its _
    assert window.name_var.get() == "IPS_FAN_RA_Hertz-_HZ"
    checks = [child for child in descendants(window) if isinstance(child, ttk.Checkbutton)]
    checks[0].invoke()  # stop using Company Code
    assert window.name_var.get() == "FAN_RA_Hertz-_HZ"

    window.save()
    assert first.name == "FAN_RA_Hertz-_HZ" and first.has_name_terms
    assert builder_gui.catalog.param_name_format[0]["use"] is False
    assert builder_gui.catalog.param_name_format[5]["prefix"] == "-_"
    assert second.name == second_name  # others aren't renamed

    # The next parameter opened keeps its name until something changes, then follows the format.
    window = builder_gui._open_param_name_builder(1)
    assert window.name_var.get() == second_name
    window.term_vars["units"].set("CFM")
    assert window.name_var.get() == "COIL_Clg_Flow-_CFM"
    window.destroy()


def test_a_recorded_parameter_shows_what_a_changed_format_builds(builder_gui, monkeypatch):
    first = builder_gui.catalog.params[0]
    custom = [dict(part) for part in builder_gui.catalog.param_name_format]
    custom[1]["prefix"] = "-"
    builder_gui.catalog.set_param_name_format(custom)
    window = builder_gui._open_param_name_builder(0)
    assert first.name == "IPS_FAN_RA_Hertz_HZ"
    assert window.name_var.get() == "IPS-FAN_RA_Hertz_HZ"
    assert "The Format Builds A Different Name; Renaming Asks About The GUID." in label_texts(window)
    window.destroy()
    assert first.name == "IPS_FAN_RA_Hertz_HZ"


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
    assert window.term_vars["company_code"].get() == "IPS"
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

        add = next(child for child in descendants(gui.params_tab)
                   if isinstance(child, ttk.Button) and child.cget("text") == "Add Parameter...")
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
