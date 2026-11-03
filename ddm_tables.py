"""Convert between the parameter ``Catalog`` and the GUI's flat tables.

The tables are the readable CSV format and what the Revit exporters consume:
parameters, families, family-parameter links, schedule entries (one row per
family and parameter in a schedule) and schedule header groups.

``catalog_from_tables`` builds a catalog from tables that may contain problems
(unknown links, invalid widths, duplicate names, ...). The catalog can't hold
invalid data, so each problem is fixed or skipped and reported in the returned
list of issues. ``tables_from_catalog`` goes the other way and never fails.
"""

import json
import math

import pandas as pd

from config.revit_dtype_definitions import get_dtype_row
from config.revit_family_category_definitions import get_family_category_row
from revit_parameter_manager import COMMON_PARAM_NAMES, Catalog, Param
from revit_shared_parameter_export import parameter_guid

DEFAULT_GRID_COLUMN_WIDTH_IN = 1.0

PARAM_COLUMNS = [
    "name", "header_text", "grid_column_width", "dtype", "group_under", "formula",
    "instance_param", "default_value", "status", "validation_message", "guid",
]
FAMILY_COLUMNS = [
    "name", "client", "client_code", "country", "country_code", "category", "description",
    "status", "validation_message",
]
LINK_COLUMNS = ["family_name", "parameter_name"]
ENTRY_COLUMNS = [
    "family_name", "group_name", "parameter_name", "header_text_override",
    "grid_column_width_override", "hidden", "override_entry", "schedule_filter", "itemize",
    "view_template", "status", "validation_message",
]
CSV_COLUMNS = [
    "record_type", "name", "guid", "header_text", "grid_column_width", "dtype", "group_under",
    "formula", "instance_param", "default_value", "status", "validation_message", "client", "client_code",
    "country", "country_code", "category", "description", "family_name", "parameter_name", "group_name",
    "header_text_override", "grid_column_width_override", "hidden", "override_entry",
    "schedule_filter", "itemize", "view_template", "caption",
    "parameter_names", "top_row", "bottom_row",
]
_CSV_RECORD_TYPES = {
    "parameter": "params",
    "family": "families",
    "link": "links",
    "schedule_column": "columns",
    "schedule_entry": "entries",
}
_TRUE_TEXT = {"true", "1", "yes", "y"}
_FALSE_TEXT = {"false", "0", "no", "n"}


def text(value):
    """``value`` as stripped text; ``None`` and NaN become ``""``."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def parse_bool(value):
    """Parse a true/false cell. Raises ``ValueError`` for anything else."""
    if isinstance(value, bool):
        return value
    normalized = text(value).lower()
    if normalized in _TRUE_TEXT:
        return True
    if normalized in _FALSE_TEXT:
        return False
    raise ValueError("Instance Param must be true or false.")


def parse_width(value):
    """Parse a grid column width in inches; blank means the default."""
    if not text(value):
        return DEFAULT_GRID_COLUMN_WIDTH_IN
    return Param._coerce_grid_column_width(value)


def _rows(frame):
    if frame is None:
        return []
    return frame.to_dict(orient="records")


# --- tables -> catalog --------------------------------------------------------

def catalog_from_tables(params=None, families=None, links=None, entries=None, header_groups=None,
                        columns=None):
    """Build a ``Catalog`` from table rows. Returns ``(catalog, issues)``.

    ``params``, ``families``, ``links`` and ``entries`` are DataFrames (or
    ``None``); ``header_groups`` maps schedule name to a list of group dicts.
    """
    catalog = Catalog()
    issues = []
    _load_params(catalog, _rows(params), issues)
    _load_families(catalog, _rows(families), _rows(links), issues)
    # Column rows first: they set each schedule's column order.
    _load_schedules(catalog, _rows(columns) + _rows(entries), header_groups or {}, issues)
    return catalog, issues


def _load_params(catalog, rows, issues):
    for number, row in enumerate(rows, start=1):
        name = text(row.get("name"))
        if not name:
            issues.append(f"Parameter row {number} has no name; skipped.")
            continue
        if catalog.get_param(name) is not None:
            issues.append(f"Duplicate parameter '{name}'; kept the first.")
            continue

        dtype = text(row.get("dtype"))
        if get_dtype_row(dtype) is None:
            issues.append(f"Parameter '{name}' has unknown data type '{dtype}'; loaded as Text.")
            dtype = "Text"
        try:
            instance_param = parse_bool(row.get("instance_param", True))
        except ValueError:
            issues.append(f"Parameter '{name}': Instance Param must be true or false; loaded as true.")
            instance_param = True
        try:
            width = parse_width(row.get("grid_column_width"))
        except ValueError as exc:
            issues.append(f"Parameter '{name}': {exc} Loaded as {DEFAULT_GRID_COLUMN_WIDTH_IN:g}.")
            width = DEFAULT_GRID_COLUMN_WIDTH_IN
        header_text = text(row.get("header_text"))
        value = text(row.get("default_value", row.get("value")))

        catalog.add_param(
            name,
            dtype,
            guid=parameter_guid(name, row.get("guid")),
            group_under=text(row.get("group_under")) or None,
            value=value or None,
            formula=text(row.get("formula")) or None,
            instance_param=instance_param,
            header_text=None if header_text == name else header_text or None,
            grid_column_width=width,
        )


def _load_families(catalog, family_rows, link_rows, issues):
    for number, row in enumerate(family_rows, start=1):
        name = text(row.get("name"))
        if not name:
            issues.append(f"Family row {number} has no name; skipped.")
            continue
        if catalog.get_family(name) is not None:
            issues.append(f"Duplicate family '{name}'; kept the first.")
            continue
        category = text(row.get("category")) or None
        if category is not None and get_family_category_row(category) is None:
            issues.append(f"Family '{name}' has unknown category '{category}'; category cleared.")
            category = None
        _load_codes(catalog, name, row, issues)
        catalog.add_family(
            name,
            client=text(row.get("client")) or None,
            country=text(row.get("country")) or None,
            description=text(row.get("description")) or None,
            category=category,
        )

    seen = set()
    for row in link_rows:
        family_name = text(row.get("family_name"))
        param_name = text(row.get("parameter_name"))
        if not family_name or not param_name:
            continue
        if (family_name, param_name) in seen:
            issues.append(f"Duplicate link '{family_name}' -> '{param_name}'; kept one.")
            continue
        seen.add((family_name, param_name))
        fam = catalog.get_family(family_name)
        param = catalog.get_param(param_name)
        if fam is None:
            issues.append(f"Link to unknown family '{family_name}' ('{param_name}'); skipped.")
            continue
        if param is None:
            issues.append(f"Family '{family_name}' links unknown parameter '{param_name}'; skipped.")
            continue
        fam.add_param(param)
    for fam in catalog.families:
        fam.validate()


def _load_codes(catalog, family_name, row, issues):
    """Codes sit on each family row; the first family to give a client (or country) a code sets it."""
    for kind in ("client", "country"):
        name = text(row.get(kind))
        code = text(row.get(f"{kind}_code"))
        if not name or not code:
            continue
        current = catalog.code(kind, name)
        if current and current != code:
            issues.append(
                f"Family '{family_name}' gives {kind} '{name}' code '{code}', "
                f"but it already has '{current}'; kept '{current}'."
            )
            continue
        try:
            catalog.set_code(kind, name, code)
        except ValueError as exc:
            issues.append(f"Family '{family_name}': {exc} Code not loaded.")


def _load_schedules(catalog, entry_rows, header_groups, issues):
    schedules = {}
    for row in entry_rows:
        schedule_name = text(row.get("group_name"))
        family_name = text(row.get("family_name"))
        param_name = text(row.get("parameter_name"))
        if not schedule_name:
            continue
        entry = schedules.setdefault(schedule_name, {
            # Fields keep the order they first appear in: the schedule's column order.
            "families": [], "fields": {}, "headers": {}, "widths": {}, "values": [], "hidden": set(),
            "filter": "", "itemize": True, "view_template": "",
        })
        # Schedule-wide settings repeat on every row of the schedule; the first one given wins.
        if not entry["filter"]:
            entry["filter"] = text(row.get("schedule_filter"))
        if not entry["view_template"]:
            entry["view_template"] = text(row.get("view_template"))
        if text(row.get("itemize")):
            try:
                entry["itemize"] = entry["itemize"] and parse_bool(row.get("itemize"))
            except ValueError:
                issues.append(f"Schedule '{schedule_name}': Itemize must be true or false; itemized.")
        # A row without a family is a schedule column on its own (a schedule can stand alone).
        if family_name:
            fam = catalog.get_family(family_name)
            if fam is None:
                issues.append(f"Schedule '{schedule_name}' uses unknown family '{family_name}'; skipped.")
                continue
            if family_name not in entry["families"]:
                entry["families"].append(family_name)
        if not param_name:
            continue
        if catalog.get_param(param_name) is None and param_name not in COMMON_PARAM_NAMES:
            issues.append(f"Schedule '{schedule_name}' uses unknown parameter '{param_name}'; skipped.")
            continue
        entry["fields"][param_name] = None

        header_text = text(row.get("header_text_override"))
        if header_text:
            entry["headers"].setdefault(param_name, header_text)
        width = text(row.get("grid_column_width_override"))
        if width:
            try:
                entry["widths"].setdefault(param_name, Param._coerce_grid_column_width(width))
            except ValueError as exc:
                issues.append(f"Schedule '{schedule_name}', '{param_name}': {exc} Override skipped.")
        try:
            if text(row.get("hidden")) and parse_bool(row.get("hidden")):
                entry["hidden"].add(param_name)
        except ValueError:
            issues.append(f"Schedule '{schedule_name}', '{param_name}': Hidden must be true or false; shown.")
        value = text(row.get("override_entry"))
        if value:
            entry["values"].append((family_name, param_name, value))

    for schedule_name, entry in schedules.items():
        schedule = catalog.add_schedule(
            schedule_name,
            entry["families"],
            field_names=list(entry["fields"]),
            header_text_overrides=entry["headers"],
            grid_column_width_overrides=entry["widths"],
            hidden_field_names=entry["hidden"],
            filter_value=entry["filter"] or None,
            itemize=entry["itemize"],
            view_template=entry["view_template"] or None,
        )
        for family_name, param_name, value in entry["values"]:
            fam = catalog.get_family(family_name)
            if param_name not in {param.name for param in fam.params}:
                issues.append(
                    f"Schedule '{schedule_name}' overrides '{param_name}' on family '{family_name}', "
                    "which doesn't have it; skipped."
                )
                continue
            schedule.override_family_param(family_name, param_name, value=value)

    for schedule_name, groups in header_groups.items():
        schedule = catalog.get_schedule(schedule_name)
        for group in groups:
            caption = group.get("caption", "")
            if schedule is None:
                issues.append(f"Header group '{caption}' is for unknown schedule '{schedule_name}'; skipped.")
                continue
            try:
                schedule.add_header_group(
                    caption,
                    group.get("parameter_names", []),
                    top_row=group.get("top_row", 0),
                    bottom_row=group.get("bottom_row", group.get("top_row", 0)),
                )
            except ValueError as exc:
                issues.append(f"Schedule '{schedule_name}', header group '{caption}': {exc} Skipped.")


# --- catalog -> tables --------------------------------------------------------

def _blank(value):
    return "" if value is None else value


def params_table(catalog):
    return pd.DataFrame(
        [
            {
                "name": param.name,
                "header_text": param.header_text,
                "grid_column_width": param.grid_column_width,
                "dtype": param.dtype,
                "group_under": _blank(param.group_under),
                "formula": _blank(param.formula),
                "instance_param": bool(param.instance_param),
                "default_value": _blank(param.value),
                "status": param.status,
                "validation_message": param.validation_message,
                "guid": param.guid,
            }
            for param in catalog.params
        ],
        columns=PARAM_COLUMNS,
    )


def families_table(catalog):
    return pd.DataFrame(
        [
            {
                "name": _blank(fam.name),
                "client": _blank(fam.client),
                "client_code": fam.client_code,
                "country": _blank(fam.country),
                "country_code": fam.country_code,
                "category": _blank(fam.category),
                "description": _blank(fam.description),
                "status": fam.status,
                "validation_message": fam.validation_message,
            }
            for fam in catalog.families
        ],
        columns=FAMILY_COLUMNS,
    )


def links_table(catalog):
    return pd.DataFrame(
        [
            {"family_name": fam.name, "parameter_name": param.name}
            for fam in catalog.families
            for param in fam.custom_params
        ],
        columns=LINK_COLUMNS,
    )


def _schedule_rows(catalog, columns):
    """With ``columns``, one row per schedule column in column order (no family);
    otherwise one row per family and column (the schedule's families)."""
    rows = []

    def entry(schedule, family_name, param_name, value=None):
        width = schedule.grid_column_width_overrides.get(param_name)
        return {
            "family_name": family_name,
            "group_name": schedule.name,
            "parameter_name": param_name,
            "header_text_override": schedule.header_text_overrides.get(param_name, ""),
            "grid_column_width_override": "" if width is None else width,
            "hidden": param_name in schedule.hidden_field_names,
            "schedule_filter": _blank(schedule.filter_value),
            "itemize": schedule.itemize,
            "view_template": _blank(schedule.view_template),
            "override_entry": _blank(value),
            "status": schedule.status,
            "validation_message": schedule.validation_message,
        }

    for schedule in catalog.schedules:
        if columns:
            if schedule.field_names is not None:
                rows.extend(entry(schedule, "", param.name) for param in schedule.params)
            continue
        for fam in schedule.fams:
            family_overrides = schedule.family_overrides.get(fam.name, {})
            for param_name in schedule.family_param_names(fam):
                if schedule.field_names is None and param_name in COMMON_PARAM_NAMES:
                    continue
                rows.append(entry(schedule, fam.name, param_name, family_overrides.get(param_name, {}).get("value")))
    return pd.DataFrame(rows, columns=ENTRY_COLUMNS)


def entries_table(catalog):
    """One row per schedule, family and column."""
    return _schedule_rows(catalog, columns=False)


def schedule_columns_table(catalog):
    """One row per schedule column, in column order: what a schedule shows even without families."""
    return _schedule_rows(catalog, columns=True)


def header_groups_by_schedule(catalog):
    return {
        schedule.name: [dict(group, parameter_names=list(group["parameter_names"])) for group in schedule.header_groups]
        for schedule in catalog.schedules
        if schedule.header_groups
    }


# --- CSV ----------------------------------------------------------------------

def write_database_csv(catalog, csv_path):
    """Write the catalog as one readable CSV with a ``record_type`` column."""
    records = []
    for record_type, table in (
        ("parameter", params_table(catalog)),
        ("family", families_table(catalog)),
        ("link", links_table(catalog)),
        ("schedule_column", schedule_columns_table(catalog)),
        ("schedule_entry", entries_table(catalog)),
    ):
        for row in table.to_dict(orient="records"):
            records.append({"record_type": record_type, **row})
    for schedule_name, groups in header_groups_by_schedule(catalog).items():
        for group in groups:
            records.append({
                "record_type": "header_group",
                "group_name": schedule_name,
                "caption": group.get("caption", ""),
                "parameter_names": json.dumps(group.get("parameter_names", [])),
                "top_row": group.get("top_row", 0),
                "bottom_row": group.get("bottom_row", group.get("top_row", 0)),
            })

    frame = pd.DataFrame(records, columns=CSV_COLUMNS)
    frame = frame.where(pd.notna(frame), "")
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")


def read_database_csv(csv_path):
    """Read a database CSV into ``(tables, header_groups)`` for ``catalog_from_tables``.

    A CSV without a ``record_type`` column is a legacy parameter-only list.
    """
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if "record_type" not in frame.columns:
        return {"params": frame}, {}

    record_types = set(frame["record_type"].astype(str)) - {""}
    unsupported = record_types - set(_CSV_RECORD_TYPES) - {"header_group"}
    if unsupported:
        raise ValueError("Unsupported CSV record type(s): {}".format(", ".join(sorted(unsupported))))

    tables = {
        table_name: frame[frame["record_type"] == record_type]
        for record_type, table_name in _CSV_RECORD_TYPES.items()
    }

    header_groups = {}
    for row in frame[frame["record_type"] == "header_group"].to_dict(orient="records"):
        try:
            parameter_names = json.loads(row.get("parameter_names") or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid parameter list in a CSV header-group record.") from exc
        if not isinstance(parameter_names, list):
            raise ValueError("CSV header-group parameter_names must be a JSON list.")
        top_row = _parse_row_index(row.get("top_row", ""), 0)
        header_groups.setdefault(row.get("group_name", ""), []).append({
            "caption": row.get("caption", ""),
            "parameter_names": parameter_names,
            "top_row": top_row,
            "bottom_row": _parse_row_index(row.get("bottom_row", ""), top_row),
        })
    return tables, header_groups


def _parse_row_index(value, default):
    if not text(value):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("CSV header-group row indices must be whole numbers.") from None
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError("CSV header-group row indices must be whole numbers.")
    return int(number)


def tables_from_legacy_pickle(payload):
    """Tables from a pre-JSON ``.ddm.pkl`` checkpoint payload."""
    tables = {
        "params": payload.get("params"),
        "families": payload.get("families"),
        "links": payload.get("family_param_links"),
        "entries": payload.get("family_groups"),
    }
    return tables, payload.get("schedule_header_groups", {}) or {}
