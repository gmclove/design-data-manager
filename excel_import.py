"""Import the Excel master workbook (``REVIT Schedules_Masters_Macro.xlsm``) into a ``Catalog``.

The workbook has:

- a **Parameters** sheet: one row per shared parameter (name, GUID, data type,
  instance or type, Group Parameter Under, default value, formulas);
- a **Families** sheet: one row per family (Revit category, client and country
  with their abbreviations, description);
- one sheet per **schedule**, every sheet after **Backstage**. Column B labels
  the rows ("Parameter Name", "Data Type", ...); each column from C on is a
  schedule column. Above the Parameter Name row are the column headings (one
  or more stacked lines) and captions spanning several columns: header groups,
  a "Hidden Parameters" group over columns hidden in the finished schedule,
  and the schedule title. Newer sheets also hold Schedule Name Filter, Itemize
  Every Instance and View Template.

The workbook doesn't link families to schedules or parameters, so schedules are
imported stand-alone and families unlinked. Schedule filters are left blank so
each defaults to its schedule's name. Anything that can't be imported is listed
in the report.
"""

from collections import Counter
from dataclasses import dataclass, field

from revit_parameter_manager import Catalog, upgrade_name_terms
from revit_shared_parameter_export import parameter_guid

SCHEDULES_AFTER_SHEET = "Backstage"
# Group Parameter Under values the workbook writes differently from Revit's names.
_GROUP_UNDER_ALIASES = {"Other": None}
# Captions that are workbook tooling, not schedule header groups.
_IGNORED_CAPTIONS = ("combine parameters",)
HIDDEN_CAPTION = "hidden"  # "Hidden Parameters", "HIDDEN", ...


# --- corrections for known mistakes in the master workbook ---------------------
# Reviewed with the user; see chat/workbook-fixes.md. Each applied correction is reported.

# (sheet, parameter as written, heading for a column with no parameter) -> parameter to use
# instead, or None to leave the column out.
COLUMN_FIXES = {
    ("Pump", "IPS_SPACE_AirReq_Recirc", None): "IPS_EQUIP_BOD_Manuf",
    ("VAV Unit", "IPS_SPACE_AirReq_Recirc", None): "IPS_EQUIP_EquipAssoc_SysOrService",
    ("Air Term", "IPS_SPACE_AirReq_Recirc", None): "IPS_EQUIP_Area_Served",
    ("Air Valve Schedule", "IPS_SPACE_AirReq_Recirc", None): "IPS_EQUIP_Airflow_Max_CFM",
    ("Air Curtain", "IPS_SPACE_AirReq_Recirc", None): "IPS_EQUIP_Max_Length",
    ("Air Device", "IPS_SPACE_AirReq_Recirc", None): "IPS_EQUIP_Material_TYPE",
    ("Water Treatment", "IPS_SPACE_AirReq_Recirc", None): "IPS_EQUIP_Water_Design_GPM",
    ("_CTRL", "IPS_SPACE_AirReq_Recirc", None): "IPS_CTRL_06_Notes",
    ("_TAG", "IPS_SPACE_AirReq_Recirc", None): "IPS_TAG_TERM_3_Middle",
    ("Valves", "IPS_SPACE_AirReq_Recirc", None): "IPS_TAG_TERM_3_Middle",
    ("_Arch - Level", "IPS_SPACE_AirReq_Recirc", None): "IPS_NAME",
    ("_Array", "IPS_SPACE_AirReq_Recirc", None): "IPS_NAME",
    ("_Arch - Levels", "IPS_SPACE_AirReq_Recirc", None): "IPS_GROUP_Mech_Waterside",
    ("_Arch - Rooms", "IPS_SPACE_AirReq_Recirc", None): None,
    ("_Line - Pipe - Water", "IPS_SPACE_AirReq_Recirc", None): None,
    ("_Line - Pipe - Steam", "IPS_SPACE_AirReq_Recirc", None): None,
    ("Chiller (Water-Cooled)", "IPS_EQUIP_Evap_GPM", None): "IPS_EQUIP_Evap_Design_GPM",
    ("Chiller (Air-Cooled)", "IPS_EQUIP_Evap_GPM", None): "IPS_EQUIP_Evap_Design_GPM",
    ("Heat Pump (Air-Water)", "IPS_EQUIP_Evap_GPM", None): "IPS_EQUIP_Evap_Design_GPM",
    ("Hydronic Snow Melt Flr Manifold", "IPS_COIL_Htg_Total_MBH_per_SF", None): "IPS_COIL_Htg_MBH_per_SF",
    ("Radiator (Fin Tube) (HHW)", "IPS_COIL_Htg_Total_MBH_per_FT", None): "IPS_COIL_Htg_MBH_per_FT",
    ("Radiant Panel (HHW-CHW)", "IPS_COIL_Htg_Total_MBH_per_FT", None): "IPS_COIL_Htg_MBH_per_FT",
    ("Steam Trap", "IPS_EQUIP_CapacityDesign_PPH", None): "IPS_EQUIP_Capacity_Design_PPH",
    ("Steam Pressure Relief Valve", "IPS_EQUIP_Capacity_PPH", None): "IPS_EQUIP_Capacity_Max_PPH",
    ("_CTRL", "IPS_CTRL_11_PilotLightColor", None): "IPS_CTRL_07_PilotLightColor",
    ("_CTRL", "IPS_CTRL_Signal_Analog", None): "IPS_CTRL_01_Analog_YN",
    ("_CTRL", "IPS_CTRL_Signal_Input", None): "IPS_CTRL_01_Input_YN",
    ("_CTRL", "IPS_CTRL_12_DetailVarient", None): "IPS_CTRL_08_DetailVariant",
    ("Heat Pump (Water-Water)", "IPS_COIL_LoadSide_Water_GPM", None): "IPS_COIL_Clg_LoadSide_GPM",
    ("_Line - Duct", "", "DUCT DIA. (IN.)"): "IPS_DUCT_Dia_IN",
}
# Columns left over from export layouts: not parameters, left out without a report line.
LEFTOVER_COLUMNS = {"Name", "NAME", "Column1"}
# Parameters the workbook's schedules need but never defined: (name, data type, group under).
NEW_PARAMETERS = (
    ("IPS_CTRL_08_DetailVariant", "Text", "Identity Data"),
    ("IPS_COIL_Clg_LoadSide_GPM", "Number", "Mechanical - Flow"),
    ("IPS_DUCT_Dia_IN", "Text", "Dimensions"),
)
# Parameter -> (text in its formula, replacement).
FORMULA_FIXES = {"IPS_SPACE_AirReq_Transf_Net_CFM": ("IPS_ROOM_Transfer_", "IPS_SPACE_Transfer_")}
# Family rows that are unfinished placeholders.
SKIPPED_FAMILIES = {"IPS-US_CTRL"}


@dataclass
class ImportResult:
    catalog: Catalog
    summary: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    corrections: list = field(default_factory=list)


def _text(value):
    """A cell as clean text: numbers without a needless ``.0``, ``None`` as ``""``."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def _group_under(value):
    text = _text(value).replace("–", "-").replace("—", "-")
    if text in _GROUP_UNDER_ALIASES:
        return _GROUP_UNDER_ALIASES[text]
    return text or None


def _header_columns(ws, required, search_rows=20):
    """``(row, {header: column})`` for the first row holding every ``required`` header."""
    for row in ws.iter_rows(min_row=1, max_row=search_rows):
        found = {_text(cell.value): cell.column for cell in row if _text(cell.value)}
        if all(name in found for name in required):
            return row[0].row, found
    raise ValueError(f"Sheet '{ws.title}' has no header row with {', '.join(required)}.")


# --- parameters ---------------------------------------------------------------

def _import_parameters(wb, catalog, result):
    ws = wb["Parameters"]
    header_row, columns = _header_columns(ws, ("Parameter Name", "Data Type", "GUID"))
    col = lambda name: columns.get(name)  # noqa: E731
    formula_differs = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        get = lambda name: row[col(name) - 1] if col(name) and col(name) <= len(row) else None  # noqa: E731
        name = _text(get("Parameter Name"))
        if not name:
            continue
        if catalog.get_param(name) is not None:
            result.issues.append(f"Parameters: '{name}' is listed twice; kept the first.")
            continue
        static, dynamic = _text(get("Formula (Static)")), _text(get("Formula (Dynamic)"))
        if static and dynamic and static != dynamic:
            formula_differs.append(name)
        try:
            catalog.add_param(
                name,
                _text(get("Data Type")),
                guid=_text(get("GUID")) or None,
                group_under=_group_under(get("Properties Palette (Group Parameter Under)")),
                value=_text(get("Value (Type or Instance Default)")) or None,
                formula=static or dynamic or None,
                instance_param=_text(get("Instance or Type")).lower() != "type",
            )
        except ValueError as exc:
            result.issues.append(f"Parameters: '{name}' skipped: {exc}")
    for name, dtype, group_under in NEW_PARAMETERS:
        if catalog.get_param(name) is None:
            catalog.add_param(name, dtype, guid=parameter_guid(name), group_under=group_under)
            result.corrections.append(f"Parameters: added '{name}' ({dtype}, {group_under}), which schedules need.")
    for name, (old, new) in FORMULA_FIXES.items():
        param = catalog.get_param(name)
        if param is not None and param.formula and old in param.formula:
            param.formula = param.formula.replace(old, new)
            result.corrections.append(f"Parameters: '{name}' formula now uses {new}... instead of {old}...")
    for name in formula_differs:
        result.issues.append(
            f"Parameters: '{name}' has different Static and Dynamic formulas; imported the Static one."
        )
    result.issues.extend(_read_name_terms(ws, catalog)[1])


# The Parameter Name Editor columns on the Parameters sheet, and the name term each one holds.
NAME_TERM_COLUMNS = {
    "Parameter Parent Category": "parent_category",
    "Parameter Child Category": "child_category",
    "Parameter Descriptor": "descriptor",
    "Parameter Clarifier": "clarifier",
    "Parameter Units": "units",
}


# Parameter names the workbook has wrong (chat/workbook-fixes.md). The GUID stays: same parameter.
PARAMETER_RENAMES = {"IPS_SPACE_AirReq_DuctLeak _PRCNT": "IPS_SPACE_AirReq_DuctLeak_PRCNT"}


def _apply_parameter_renames(catalog, result):
    """Correct ``PARAMETER_RENAMES``, along with the terms and every reference to the name."""
    for old, new in PARAMETER_RENAMES.items():
        param = catalog.get_param(old)
        if param is None or catalog.get_param(new) is not None:
            continue
        terms = {term: value.strip() for term, value in param.name_terms.items()}
        catalog.rename_param(old, new, keep_guid=True)
        param.set_name_terms(terms)
        result.corrections.append(f"Parameters: renamed '{old}' to '{new}'.")


def _term_text(value):
    """A name term's cell, spaces and all: the workbook's names keep them."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _read_name_terms(ws, catalog):
    """Record the Parameter Name Editor's terms on the catalog's parameters, matched by name.

    Nothing is renamed. Returns ``(number recorded, [problem, ...])``.
    """
    header_row, columns = _header_columns(ws, ("Parameter Name",))
    if not all(header in columns for header in NAME_TERM_COLUMNS):
        return 0, []
    recorded, problems = 0, []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        param = catalog.get_param(_text(row[columns["Parameter Name"] - 1]))
        if param is None:
            continue
        terms = {term: _term_text(row[columns[header] - 1]) for header, term in NAME_TERM_COLUMNS.items()}
        if param.set_name_terms(upgrade_name_terms(terms)):
            recorded += 1
        else:
            problems.append(f"Parameters: '{param.name}' doesn't match its Parameter Name Editor terms; terms left out.")
    return recorded, problems


def read_name_terms(path, catalog):
    """Record the workbook's name terms on an existing catalog, changing nothing else.

    Returns ``(number recorded, [problem, ...])``.
    """
    import openpyxl  # only needed for imports, so the app runs without it

    return _read_name_terms(openpyxl.load_workbook(path, data_only=True)["Parameters"], catalog)


# --- families -----------------------------------------------------------------

# Excel tables (on the Backstage sheet) listing each Category 1 and 2 with its code, so names
# no family uses yet are kept too.
CODE_TABLES = {"category_1": "famCat1", "category_2": "FamCat2"}
# Families sheet columns holding each kind's name and code.
FAMILY_CODE_COLUMNS = {
    "client": ("Client", "Client Abbrev."),
    "country": ("Country", "Country Abbrev."),
    "category_1": ("Family Category 1", "Family Category 1 Abbrev."),
    "category_2": ("Family Category 2", "Family Category 2 Abbrev."),
}


def _lookup_table(wb, table_name):
    """The Excel table ``table_name``'s first two columns as ``{name: code}``; ``{}`` if missing."""
    for ws in wb.worksheets:
        if table_name in ws.tables:
            rows = list(ws[ws.tables[table_name].ref])[1:]
            return {_text(row[0].value): _text(row[1].value) for row in rows if _text(row[0].value)}
    return {}


def _set_code(catalog, result, kind, name, code, where):
    if name and code and catalog.code(kind, name) != code:
        try:
            catalog.set_code(kind, name, code)
        except ValueError as exc:
            result.issues.append(f"{where}: {exc}")


def _import_families(wb, catalog, result):
    for kind, table_name in CODE_TABLES.items():
        for name, code in _lookup_table(wb, table_name).items():
            _set_code(catalog, result, kind, name, code, f"Table {table_name}")
    ws = wb["Families"]
    header_row, columns = _header_columns(ws, ("Family Name", "Revit Family Category"))
    # The Revit View code (2D / 3D) of each Revit category's families, for its Category Code.
    view_codes = {}
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        get = lambda name: _text(row[columns[name] - 1]) if name in columns and columns[name] <= len(row) else ""  # noqa: E731
        name = get("Family Name")
        if not name:
            continue
        if name in SKIPPED_FAMILIES:
            correction = f"Families: left out '{name}', an unfinished placeholder row."
            if correction not in result.corrections:
                result.corrections.append(correction)
            continue
        if catalog.get_family(name) is not None:
            result.issues.append(f"Families: '{name}' is listed twice; kept the first.")
            continue
        for kind, (name_column, code_column) in FAMILY_CODE_COLUMNS.items():
            _set_code(catalog, result, kind, get(name_column), get(code_column), f"Families: '{name}'")
        category = get("Revit Family Category") or None
        if category:
            view_codes.setdefault(category, set()).add(get("Revit View Abbrev."))
        details = {
            "client": get("Client") or None, "country": get("Country") or None,
            "category_1": get("Family Category 1") or None, "category_2": get("Family Category 2") or None,
            "description": get("Description") or None,
        }
        try:
            catalog.add_family(name, category=category, **details)
        except ValueError as exc:
            result.issues.append(f"Families: '{name}' imported without its category: {exc}")
            catalog.add_family(name, **details)

    # Category Code: 3D for categories placed in floor plans, 2D for drafting views; a
    # category whose families use both (or no view) gets none.
    for category, codes in sorted(view_codes.items()):
        if len(codes) == 1 and "" not in codes:
            _set_code(catalog, result, "category", category, codes.pop(), "Families")


# --- schedules ----------------------------------------------------------------

def _has_border(side):
    return side is not None and side.style is not None


def _caption_span(ws, row, column, last_column):
    """The columns a caption at ``(row, column)`` spans: on to the next border or text."""
    end = column
    while end < last_column:
        here, after = ws.cell(row, end), ws.cell(row, end + 1)
        if _text(after.value) or _has_border(here.border.right) or _has_border(after.border.left):
            break
        end += 1
    return column, end


def _widen_boxed_captions(captions, caption_rows, last_column):
    """Give captions boxed into one cell (e.g. "HEATING COIL") the width they label.

    A caption whose borders span several columns keeps that span. One boxed into a
    single cell covers the captions below it that start before the next caption on
    its row; with none below, it runs to that next caption, inside the caption above.
    Rows are done bottom-up so a widened caption can bound the one above it.
    """
    spans = {(row, first): (first, last) for row, _text, first, last in captions}
    widened = []
    for row, text, first, last in sorted(captions, key=lambda caption: -caption[0]):
        if first == last:
            later = [c for c in caption_rows[row] if c > first]
            reach = (later[0] - 1) if later else last_column
            # The nearest caption row below with captions starting under this one.
            nearest = min((r for r in caption_rows if r > row and any(
                first <= c <= reach and (r, c) in spans for c in caption_rows[r])), default=None)
            below = [
                spans[(nearest, c)] for c in caption_rows.get(nearest, [])
                if first <= c <= reach and (nearest, c) in spans
            ]
            if below:
                last = min(reach, max(end for _start, end in below))
            else:
                above = [
                    spans[(r, c)] for r in sorted(caption_rows, reverse=True) if r < row
                    for c in caption_rows[r] if (r, c) in spans and spans[(r, c)][0] <= first <= spans[(r, c)][1]
                ]
                last = min(reach, above[0][1]) if above else reach
            spans[(row, first)] = (first, last)
        widened.append((row, text, first, last))
    return sorted(widened)


def _read_schedule_sheet(ws):
    """Everything one schedule sheet says, as plain data (no catalog changes)."""
    labels = {}
    for row in range(1, min(ws.max_row, 80) + 1):
        label = _text(ws.cell(row, 2).value).rstrip(":").strip().lower()
        if label:
            labels.setdefault(label, row)
    name_row = labels.get("parameter name")
    if name_row is None:
        return None
    last_column = ws.max_column

    def label_value(label, column=3):
        return ws.cell(labels[label], column).value if label in labels else None

    removed = set()
    if "remove" in labels:
        removed = {c for c in range(3, last_column + 1) if ws.cell(labels["remove"], c).value is True}
    columns = {}
    corrections = []
    for c in range(3, last_column + 1):
        name = _text(ws.cell(name_row, c).value)
        if not name or c in removed or name in LEFTOVER_COLUMNS:
            continue
        if (ws.title, name, None) in COLUMN_FIXES:
            fixed = COLUMN_FIXES[(ws.title, name, None)]
            corrections.append(
                f"Schedule '{ws.title}': column '{name}' "
                + (f"is now '{fixed}'." if fixed else "left out (no heading; a stray parameter).")
            )
            if fixed is None:
                continue
            name = fixed
        columns[c] = name

    attribute_rows = {
        "dtype": labels.get("data type"),
        "group_under": labels.get("group parameter under"),
        "instance": labels.get("type or instance", labels.get("instance or type")),
    }
    definitions = {
        name: {key: ws.cell(row, c).value if row else None for key, row in attribute_rows.items()}
        for c, name in columns.items()
    }

    labelled_rows = set(labels.values())

    def row_texts(row):
        return {
            c: _text(ws.cell(row, c).value) for c in range(3, last_column + 1)
            if _text(ws.cell(row, c).value) and not isinstance(ws.cell(row, c).value, bool)
        }

    # Heading rows sit right above the Parameter Name row and have text over most columns
    # (a heading can stack over several rows); rows above them hold captions.
    heading_rows = []
    row = name_row - 1
    while row >= 4 and row not in labelled_rows:
        texts = row_texts(row)
        if sum(1 for c in columns if c in texts) * 2 < len(columns):
            break
        heading_rows.insert(0, row)
        row -= 1
    first_heading_row = heading_rows[0] if heading_rows else name_row

    # A column with a heading but no parameter, when a correction names its parameter.
    for c in range(3, last_column + 1):
        if c in columns or c in removed or _text(ws.cell(name_row, c).value):
            continue
        heading = " ".join(row_texts(row).get(c, "") for row in heading_rows).strip()
        fixed = COLUMN_FIXES.get((ws.title, "", heading))
        if fixed:
            columns[c] = fixed
            corrections.append(f"Schedule '{ws.title}': column '{heading}' had no parameter; now '{fixed}'.")
    columns = dict(sorted(columns.items()))

    headings = {c: [] for c in columns}
    for row in heading_rows:
        for c, text in row_texts(row).items():
            if c in headings:
                headings[c].append(text)
    # A merged caption spans exactly its merged cells.
    merged = {(cells.min_row, cells.min_col): (cells.min_col, cells.max_col) for cells in ws.merged_cells.ranges}
    captions = []  # (row, caption, first column, last column)
    caption_rows = {}
    notes = []
    for row in range(4, first_heading_row):
        if row in labelled_rows:
            continue
        texts = row_texts(row)
        # Captions are bold; plain text up here is a note to the workbook's editors.
        notes.extend(text for c, text in texts.items() if not ws.cell(row, c).font.b)
        texts = {c: text for c, text in texts.items() if ws.cell(row, c).font.b}
        caption_rows[row] = sorted(texts)
        for c, text in texts.items():
            if not text.lower().startswith(_IGNORED_CAPTIONS):
                first, last = merged.get((row, c)) or _caption_span(ws, row, c, last_column)
                captions.append((row, text, first, last))
    captions = _widen_boxed_captions(captions, caption_rows, last_column)

    hidden = set()
    for _row, text, first, last in captions:
        if text.lower().startswith(HIDDEN_CAPTION):
            hidden.update(c for c in range(first, last + 1) if c in columns)
    visible = {c for c in columns if c not in hidden}
    groups = []
    for row, text, first, last in captions:
        spanned = [c for c in range(first, last + 1) if c in columns]
        if not spanned or text.lower().startswith(HIDDEN_CAPTION):
            continue
        if visible and visible <= set(spanned):
            continue  # the schedule title
        groups.append((row, text, [columns[c] for c in spanned]))

    itemize = label_value("itemize every instance")
    return {
        "columns": [columns[c] for c in sorted(columns)],
        "headings": {columns[c]: " ".join(lines) for c, lines in headings.items() if lines},
        "hidden": {columns[c] for c in hidden},
        "groups": groups,
        "definitions": definitions,
        "corrections": corrections,
        "notes": notes,
        "itemize": True if itemize is None else bool(itemize),
        "view_template": _text(label_value("view template")) or None,
    }


def _import_schedules(wb, catalog, result):
    names = wb.sheetnames
    if SCHEDULES_AFTER_SHEET not in names:
        raise ValueError(f"The workbook has no '{SCHEDULES_AFTER_SHEET}' sheet before its schedules.")
    sheets = {}
    for name in names[names.index(SCHEDULES_AFTER_SHEET) + 1:]:
        sheet = _read_schedule_sheet(wb[name])
        if sheet is None:
            result.issues.append(f"Schedule '{name}': no 'Parameter Name' row; skipped.")
            continue
        sheets[name] = sheet
        result.corrections.extend(sheet["corrections"])
        result.issues.extend(f"Schedule '{name}': note '{note}' isn't a header group; left out." for note in sheet["notes"])

    # Parameters a schedule uses but the Parameters sheet lacks: define them from the schedule.
    for name, sheet in sheets.items():
        for param_name in sheet["columns"]:
            if catalog.get_param(param_name) is not None:
                continue
            definition = sheet["definitions"][param_name]
            try:
                catalog.add_param(
                    param_name, _text(definition["dtype"]), guid=parameter_guid(param_name),
                    group_under=_group_under(definition["group_under"]),
                    instance_param=_text(definition["instance"]).lower() != "type",
                )
                result.issues.append(
                    f"Schedule '{name}': '{param_name}' isn't on the Parameters sheet; "
                    "added it from the schedule's Data Type row (new GUID)."
                )
            except ValueError:
                result.issues.append(
                    f"Schedule '{name}': column '{param_name}' skipped: it isn't on the Parameters sheet "
                    f"and the schedule gives no valid data type ('{_text(definition['dtype'])}')."
                )

    # A parameter's default heading is the one most schedules use; the rest are overrides.
    usage = {}
    for sheet in sheets.values():
        for param_name, heading in sheet["headings"].items():
            usage.setdefault(param_name, Counter())[heading] += 1
    for param_name, counts in usage.items():
        param = catalog.get_param(param_name)
        if param is not None:
            param.header_text = counts.most_common(1)[0][0]

    for name, sheet in sheets.items():
        field_names = []
        for param_name in sheet["columns"]:
            if catalog.get_param(param_name) is None:
                continue
            if param_name in field_names:
                result.issues.append(f"Schedule '{name}': '{param_name}' appears twice; kept the first.")
                continue
            field_names.append(param_name)
        if catalog.get_schedule(name) is not None:
            result.issues.append(f"Schedule '{name}' is listed twice; kept the first.")
            continue
        schedule = catalog.add_schedule(
            name, field_names=field_names, itemize=sheet["itemize"], view_template=sheet["view_template"],
        )
        for param_name, heading in sheet["headings"].items():
            if param_name in field_names and heading != catalog.get_param(param_name).header_text:
                schedule.override_param(param_name, header_text=heading)
        for param_name in sheet["hidden"]:
            if param_name in field_names:
                schedule.set_field_hidden(param_name, True)
        for _row, caption, group_params in sorted(sheet["groups"], key=lambda group: -group[0]):
            group_params = [param_name for param_name in group_params if param_name in field_names]
            if not group_params:
                continue
            try:
                schedule.add_header_group(caption, group_params)
            except ValueError as exc:
                result.issues.append(f"Schedule '{name}': header group '{caption}' skipped: {exc}")


def import_workbook(path):
    """Read the master workbook into a new ``Catalog``. Returns an ``ImportResult``."""
    import openpyxl  # only needed for imports, so the app runs without it

    wb = openpyxl.load_workbook(path, data_only=True)
    catalog = Catalog()
    result = ImportResult(catalog)
    _import_parameters(wb, catalog, result)
    _import_families(wb, catalog, result)
    _import_schedules(wb, catalog, result)
    _apply_parameter_renames(catalog, result)
    catalog.validate()

    columns = sum(len(schedule.params) for schedule in catalog.schedules)
    result.summary = [
        f"Imported {len(catalog.params)} parameters, {len(catalog.families)} families and "
        f"{len(catalog.schedules)} schedules ({columns} columns) from {path}.",
        f"Hidden columns: {sum(len(s.hidden_field_names) for s in catalog.schedules)}; header groups: "
        f"{sum(len(s.header_groups) for s in catalog.schedules)}; clients: {len(catalog.names('client'))}; "
        f"countries: {len(catalog.names('country'))}.",
        "Families aren't linked to schedules or parameters (the workbook doesn't record that); "
        "schedule filters default to the schedule names.",
        f"Applied {len(result.corrections)} correction(s) for known workbook mistakes "
        "(see chat/workbook-fixes.md).",
    ]
    return result
