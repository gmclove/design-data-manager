import pytest

openpyxl = pytest.importorskip("openpyxl")
from openpyxl.styles import Border, Font, Side  # noqa: E402
from openpyxl.worksheet.table import Table  # noqa: E402

import excel_import  # noqa: E402
from excel_import import import_workbook  # noqa: E402

THIN = Side(style="thin")
BOXED = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def make_workbook(path):
    """A small master workbook in the same shape as the real one."""
    wb = openpyxl.Workbook()
    params = wb.active
    params.title = "Parameters"
    params.append([])
    params.append([None, None, "GUID", "Properties Palette (Group Parameter Under)", None, None, None, None,
                   None, None, None, "Parameter Name", "Data Type", "Instance or Type", None, None, None, None,
                   None, None, None, None, "Value (Type or Instance Default)", "Formula (Dynamic)", "Formula (Static)"])
    rows = [
        ("11111111-1111-1111-1111-111111111111", "Mechanical – Loads", "IPS_Flow_CFM", "Number", "Instance", -999, None, None),
        ("22222222-2222-2222-2222-222222222222", "Other", "IPS_Tag", "Text", "Type", None, None, None),
        ("33333333-3333-3333-3333-333333333333", "Data", "IPS_Note", "Text", "Instance", None, "IPS_Tag", "IPS_Tag"),
        ("44444444-4444-4444-4444-444444444444", "Data", "IPS_Area", "Number", "Instance", None, "IPS_Flow_CFM * 1", "IPS_Flow_CFM * 2"),
    ]
    for guid, group, name, dtype, kind, value, dynamic, static in rows:
        row = [None] * 25
        row[2], row[3], row[11], row[12], row[13] = guid, group, name, dtype, kind
        row[22], row[23], row[24] = value, dynamic, static
        params.append(row)

    families = wb.create_sheet("Families")
    families.append([])
    header = [None] * 17
    header[1], header[3], header[4], header[7] = "Revit Family Category", "Client", "Country", "Description"
    header[5], header[6] = "Family Category 1", "Family Category 2"
    header[9], header[10], header[16] = "Client Abbrev.", "Country Abbrev.", "Family Name"
    header[11], header[12], header[13] = "Family Category 1 Abbrev.", "Family Category 2 Abbrev.", "Revit View Abbrev."
    families.append(header)
    rows = (
        ("IPS-US_Pump", "Mechanical Equipment", "Equipment", "Pump", "EQUIP", "PUMP", "3D"),
        ("IPS-US_Pump", "Mechanical Equipment", "Equipment", "Pump", "EQUIP", "PUMP", "3D"),
        ("IPS-US_Tag_2D", "Multi-Category Tags", "General", None, "GEN", None, "2D"),
        ("IPS-US_Tag_3D", "Multi-Category Tags", "General", None, "GEN", None, "3D"),
        ("IPS-US_Line_2D", "Detail Item", "General", None, "GEN", None, "2D"),
    )
    for name, category, category_1, category_2, code_1, code_2, view in rows:
        row = [None] * 17
        row[1], row[3], row[4], row[7], row[9], row[10], row[16] = (
            category, "IPS", "United States", "Pump", "IPS", "US", name)
        row[5], row[6], row[11], row[12], row[13] = category_1, category_2, code_1, code_2, view
        families.append(row)

    wb.create_sheet("Not A Schedule")
    backstage = wb.create_sheet("Backstage")
    # The Category 1 code table, listing one no family uses yet.
    for row in (("Category 1", "Category 1 Abbrev."), ("Equipment", "EQUIP"), ("Piping", "PIPE")):
        backstage.append(row)
    backstage.add_table(Table(displayName="famCat1", ref="A1:B3"))

    sheet = wb.create_sheet("Pump")
    sheet["B6"], sheet["C6"] = "Schedule Name Filter:", "equip, "
    sheet["B7"], sheet["C7"] = "Itemize Every Instance:", False
    sheet["B8"], sheet["C8"] = "View Template:", "IPS_Schedule_Standard"
    # Row 10: hidden group over C, the title over D-G. Row 11: a group boxed into one cell.
    sheet["C10"] = "Hidden Parameters"
    sheet["C10"].border = BOXED
    sheet["D10"] = "PUMP SCHEDULE"
    sheet["D11"] = "PERFORMANCE"
    sheet["D11"].border = BOXED
    sheet["F11"] = "Combine Parameters"
    sheet["E12"] = "FLOW"
    sheet["E12"].border = Border(left=THIN, right=THIN)
    headings = {"C": "TAG", "D": "FLOW", "E": "AREA", "F": "NOTE", "G": "EXTRA"}
    for column, text in headings.items():
        sheet[f"{column}14"] = text
        sheet[f"{column}14"].border = BOXED
    # Row 12: a caption merged over F-G, with a border inside the merge (as the workbook has).
    sheet["F12"] = "OTHER DATA"
    sheet["F12"].border = Border(right=THIN)
    sheet.merge_cells("F12:G12")
    # A plain (not bold) note to the workbook's editors, among the captions.
    sheet["G11"] = "IGNORE FOR NOW"
    for cell in ("C10", "D10", "D11", "F11", "E12", "F12"):
        sheet[cell].font = Font(bold=True)  # the workbook's captions are bold
    sheet["D13"] = "SUPPLY"
    sheet["D13"].border = BOXED
    sheet["E13"], sheet["F13"], sheet["G13"] = "TOTAL", "GENERAL", "MORE"
    sheet["B15"] = "Parameter Name"
    for column, name in {"C": "IPS_Tag", "D": "IPS_Flow_CFM", "E": "IPS_Area", "F": "IPS_Note", "G": "IPS_New"}.items():
        sheet[f"{column}15"] = name
    sheet["B16"], sheet["G16"] = "Data Type", "Yes/No"
    sheet["B17"], sheet["G17"] = "Group Parameter Under", "Data"
    sheet["B18"], sheet["G18"] = "Type or Instance", "Instance"
    sheet["B19"] = "REMOVE:"
    sheet["F19"] = False

    gone = wb.create_sheet("Broken")
    gone["C5"] = "No parameter name row here"
    wb.save(path)
    return path


@pytest.fixture
def imported(tmp_path):
    return import_workbook(make_workbook(tmp_path / "master.xlsx"))


def test_parameters_import_with_guids_groups_values_and_formulas(imported):
    catalog = imported.catalog
    flow = catalog.get_param("IPS_Flow_CFM")
    assert (flow.guid, flow.dtype, flow.group_under, flow.value, flow.instance_param) == (
        "11111111-1111-1111-1111-111111111111", "Number", "Mechanical - Loads", "-999", True)
    tag = catalog.get_param("IPS_Tag")
    assert (tag.group_under, tag.instance_param) == (None, False)  # "Other" is Revit's no-group
    assert catalog.get_param("IPS_Area").formula == "IPS_Flow_CFM * 2"  # the Static formula
    assert any("'IPS_Area' has different Static and Dynamic formulas" in issue for issue in imported.issues)


def test_parameter_name_editor_terms_import_with_the_parameters(tmp_path):
    path = tmp_path / "master.xlsx"
    make_workbook(path)
    wb = openpyxl.load_workbook(path)
    sheet = wb["Parameters"]
    # The real sheet's headings, including the stray space on the first.
    headings = ("Parameter Parent Category ", "Parameter Child Category", "Parameter Descriptor",
                "Parameter Clarifier", "Parameter Units")
    for column, heading in enumerate(headings, start=5):
        sheet.cell(2, column).value = heading
    rows = {3: ("Flow", None, None, None, "CFM"), 4: ("Tag", None, None, None, None),
            5: ("No", "te", None, None, None), 6: ("Area", None, None, None, None)}
    for row, terms in rows.items():
        for column, term in enumerate(terms, start=5):
            sheet.cell(row, column).value = term
    wb.save(path)

    result = import_workbook(path)

    flow = result.catalog.get_param("IPS_Flow_CFM")
    assert flow.has_name_terms and flow.name_terms["units"] == "CFM"
    assert result.catalog.get_param("IPS_Tag").has_name_terms
    note = result.catalog.get_param("IPS_Note")  # No_te builds another name, so its terms stay out
    assert not note.has_name_terms
    assert "Parameters: 'IPS_Note' doesn't match its Parameter Name Editor terms; terms left out." in result.issues


def test_the_workbook_stray_space_is_on_the_list_of_renames():
    assert excel_import.PARAMETER_RENAMES["IPS_SPACE_AirReq_DuctLeak _PRCNT"] == "IPS_SPACE_AirReq_DuctLeak_PRCNT"


def test_wrong_parameter_names_are_corrected_on_import_keeping_the_guid(tmp_path, monkeypatch):
    monkeypatch.setattr(excel_import, "PARAMETER_RENAMES", {"IPS_Tag": "IPS_Label"})
    path = tmp_path / "master.xlsx"
    make_workbook(path)

    result = import_workbook(path)

    assert result.catalog.get_param("IPS_Tag") is None
    param = result.catalog.get_param("IPS_Label")
    assert param.guid == "22222222-2222-2222-2222-222222222222"
    assert result.catalog.get_param("IPS_Note").formula == "IPS_Label"  # references follow
    assert "Parameters: renamed 'IPS_Tag' to 'IPS_Label'." in result.corrections


def test_families_import_with_client_and_country_codes(imported):
    catalog = imported.catalog
    fam = catalog.get_family("IPS-US_Pump")
    assert (fam.category, fam.client_code, fam.country_code, fam.description) == (
        "Mechanical Equipment", "IPS", "US", "Pump")
    assert fam.status == "Warning"  # no parameters yet; not an error
    assert any("'IPS-US_Pump' is listed twice" in issue for issue in imported.issues)


def test_families_import_categories_with_codes_and_category_codes_from_their_views(imported):
    catalog = imported.catalog
    fam = catalog.get_family("IPS-US_Pump")
    assert (fam.category_1, fam.category_1_code, fam.category_2, fam.category_2_code) == (
        "Equipment", "EQUIP", "Pump", "PUMP")
    assert catalog.code("category_1", "Piping") == "PIPE"  # from the code table, though unused
    # A category's code is its families' view: one view gives it, both views give none.
    assert catalog.code("category", "Mechanical Equipment") == "3D"
    assert catalog.code("category", "Detail Item") == "2D"
    assert catalog.code("category", "Multi-Category Tags") == ""
    assert catalog.build_family_name(fam) == "IPS-US_EQUIP_PUMP_Pump_3D"


def test_schedule_sheets_after_backstage_become_standalone_schedules(imported):
    catalog = imported.catalog
    assert [schedule.name for schedule in catalog.schedules] == ["Pump"]
    assert any("'Broken': no 'Parameter Name' row" in issue for issue in imported.issues)
    schedule = catalog.get_schedule("Pump")
    assert schedule.fams == []
    assert schedule.filter_value is None  # defaults to the schedule's name
    assert (schedule.itemize, schedule.view_template) == (False, "IPS_Schedule_Standard")
    assert [param.name for param in schedule.params] == ["IPS_Tag", "IPS_Flow_CFM", "IPS_Area", "IPS_Note", "IPS_New"]
    assert schedule.hidden_field_names == {"IPS_Tag"}


def test_stacked_headings_and_boxed_group_captions(imported):
    schedule = imported.catalog.get_schedule("Pump")
    headers = {param.name: param.header_text for param in schedule.params}
    assert headers["IPS_Flow_CFM"] == "SUPPLY FLOW"
    assert headers["IPS_Area"] == "TOTAL AREA"
    groups = {group["caption"]: group["parameter_names"] for group in schedule.header_groups}
    # "PERFORMANCE" is boxed into D11 but covers the "FLOW" group (D-E) below it.
    assert groups["PERFORMANCE"] == ["IPS_Flow_CFM", "IPS_Area"]
    assert "PUMP SCHEDULE" not in groups  # the title
    assert "Combine Parameters" not in groups
    assert "Hidden Parameters" not in groups
    # A merged caption spans its merged cells, not just up to the border inside them.
    assert groups["OTHER DATA"] == ["IPS_Note", "IPS_New"]
    # Plain text among the captions is a note, not a group.
    assert "IGNORE FOR NOW" not in groups
    assert "Schedule 'Pump': note 'IGNORE FOR NOW' isn't a header group; left out." in imported.issues


def test_gui_import_replaces_the_database_and_survives_a_save(tmp_path):
    from tests.test_ddm_gui import make_test_gui

    gui = make_test_gui()
    gui.checkpoint_path = tmp_path / "database.ddm.json"
    result = gui.import_excel_workbook(str(make_workbook(tmp_path / "master.xlsx")), confirm=False)

    assert gui.catalog is result.catalog
    assert [schedule.name for schedule in gui.catalog.schedules] == ["Pump"]
    gui.save_checkpoint()

    for saved in ("database.ddm.json", "database.ddm.csv"):
        reloaded = make_test_gui()
        reloaded.load_checkpoint(str(tmp_path / saved))
        schedule = reloaded.catalog.get_schedule("Pump")
        assert [param.name for param in schedule.params] == [param.name for param in result.catalog.schedules[0].params]
        assert schedule.hidden_field_names == {"IPS_Tag"}
        assert schedule.header_groups == result.catalog.schedules[0].header_groups
        assert reloaded.catalog.get_family("IPS-US_Pump").client_code == "IPS"


def test_known_workbook_mistakes_are_corrected(tmp_path, monkeypatch):
    import excel_import

    path = make_workbook(tmp_path / "master.xlsx")
    wb = openpyxl.load_workbook(path)
    sheet = wb["Pump"]
    sheet["G15"] = "IPS_Typo"            # a misnamed parameter
    sheet["H14"], sheet["H15"] = "NOTE 2", "IPS_Stray"  # a stray column to drop
    sheet["I14"] = "WIDTH"               # a heading with no parameter
    sheet["J14"], sheet["J15"] = "x", "Column1"  # an export leftover
    wb.save(path)
    monkeypatch.setattr(excel_import, "COLUMN_FIXES", {
        ("Pump", "IPS_Typo", None): "IPS_Note",
        ("Pump", "IPS_Stray", None): None,
        ("Pump", "", "WIDTH"): "IPS_Width",
    })
    monkeypatch.setattr(excel_import, "NEW_PARAMETERS", (("IPS_Width", "Text", "Dimensions"),))
    monkeypatch.setattr(excel_import, "FORMULA_FIXES", {"IPS_Area": ("* 2", "* 3")})
    monkeypatch.setattr(excel_import, "SKIPPED_FAMILIES", {"IPS-US_Pump"})

    result = import_workbook(path)

    catalog = result.catalog
    columns = [param.name for param in catalog.get_schedule("Pump").params]
    assert columns == ["IPS_Tag", "IPS_Flow_CFM", "IPS_Area", "IPS_Note", "IPS_Width"]
    width = catalog.get_param("IPS_Width")
    assert (width.dtype, width.group_under) == ("Text", "Dimensions")
    assert catalog.get_param("IPS_Area").formula == "IPS_Flow_CFM * 3"
    assert catalog.get_family("IPS-US_Pump") is None
    assert len(result.corrections) == 6  # new parameter, formula, family, three columns
    assert not any("Column1" in line for line in result.issues + result.corrections)


def test_a_parameter_only_on_a_schedule_is_defined_from_the_schedule(imported):
    new = imported.catalog.get_param("IPS_New")
    assert (new.dtype, new.group_under, new.instance_param) == ("Yes/No", "Data", True)
    assert any("'IPS_New' isn't on the Parameters sheet" in issue for issue in imported.issues)
