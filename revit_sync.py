"""Compare what a Revit project's schedules look like with the database, and take changes back.

The macro ``SendSchedulesToDatabase`` writes ``<database>.revit-sync.json``. This module reads it
and lists the differences; the user decides on each one, and the ones they accept are applied to
the catalog. Nothing here changes the catalog until ``apply_differences``.

Headers and widths are compared on all three Revit schedules, since the database keeps one value
for all of them and an edit can be made on any. The rest (name, which columns, their order, hidden
columns, itemize) comes from the finished schedule ``{name}``; if the columns of the other two no
longer match it, that is listed for information.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from revit_parameter_manager import COMMON_PARAM_NAMES, SCHEDULE_FILTER_PARAM, normalized_sorting, sorting_summary
from revit_schedule_macro_generator import schedule_specs

SYNC_FORMAT_VERSION = 1
FINISHED_ROLE = "Finished"
OTHER_ROLES = ("Model", "Working")
# Finished last: if more than one value is accepted for a column, the last one applied wins.
ALL_ROLES = OTHER_ROLES + (FINISHED_ROLE,)
# Revit stores widths as floating point feet; smaller differences than this aren't a change.
WIDTH_TOLERANCE_INCHES = 0.01

NAME = "name"
COLUMN_REMOVED = "column_removed"
COLUMN_ADDED = "column_added"
COLUMN_ORDER = "column_order"
HEADING = "heading"
WIDTH = "width"
HIDDEN = "hidden"
ITEMIZE = "itemize"
SORTING = "sorting"
INFORMATION = "information"
# Columns change first, so settings can then apply to a column that was just added.
APPLY_ORDER = (NAME, COLUMN_REMOVED, COLUMN_ADDED, COLUMN_ORDER, HEADING, WIDTH, HIDDEN, ITEMIZE, SORTING)
CHANGE_LABELS = {
    NAME: "Name",
    COLUMN_REMOVED: "Column Removed in Revit",
    COLUMN_ADDED: "Column Added in Revit",
    COLUMN_ORDER: "Column Order",
    HEADING: "Header",
    WIDTH: "Column Width (in)",
    HIDDEN: "Hidden Column",
    ITEMIZE: "Itemize Every Instance",
    SORTING: "Sorting/Grouping",
    INFORMATION: "Information",
}


class SyncFileError(ValueError):
    """The sync file can't be read or isn't one this version understands."""


@dataclass
class Difference:
    """One thing that differs. ``can_apply`` is false for rows that are only for information."""

    schedule_name: str
    kind: str
    parameter: str = ""
    database_value: str = ""
    revit_value: str = ""
    note: str = ""
    can_apply: bool = True
    schedule_guid: Optional[str] = None
    # What to apply: the new value, in the catalog's terms.
    value: Any = field(default=None, repr=False)
    # Which side changed it since the project's last sync: REVIT_CHANGED or BOTH_CHANGED; blank
    # when the project has no last sync for the schedule (a plain comparison).
    origin: str = ""

    @property
    def key(self):
        """What identifies this difference across comparisons: same schedule, field and Revit value."""
        return (self.schedule_guid, self.kind, self.parameter, self.revit_value)

    @property
    def change(self):
        label = CHANGE_LABELS[self.kind]
        return f"{label}: {self.parameter}" if self.parameter else label


def read_sync_file(path):
    """The sync file's contents. Raises ``SyncFileError`` if it isn't usable."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise SyncFileError(f"Couldn't read the file: {exc}") from exc
    except ValueError as exc:
        raise SyncFileError(f"The file isn't valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("schedules"), list):
        raise SyncFileError("The file isn't a Revit sync file.")
    if data.get("version") != SYNC_FORMAT_VERSION:
        raise SyncFileError(
            f"The file is version {data.get('version')}; this app reads version {SYNC_FORMAT_VERSION}. "
            "Save the database, rebuild the macro and send the schedules again."
        )
    return data


def _value_text(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _width_text(inches):
    return f"{inches:.3f}".rstrip("0").rstrip(".")


def _join(names):
    return ", ".join(names)


def _other_schedule_note(schedule_name, finished, other, spec_names):
    """Information row when another Revit schedule's columns no longer match the finished one."""
    unavailable = set(other.get("unavailable", ())) | set(finished.get("unavailable", ()))

    def shared(sent):
        return [
            column["parameter"]
            for column in sent["columns"]
            if column["parameter"] not in unavailable
            and (column["parameter"] != SCHEDULE_FILTER_PARAM or SCHEDULE_FILTER_PARAM in spec_names)
        ]

    if shared(other) == shared(finished):
        return None
    return Difference(
        schedule_name, INFORMATION, can_apply=False,
        revit_value=other["name"],
        note=f"Its columns differ from '{finished['name']}'. Only that schedule's columns are compared.",
    )


def _setting_differences(spec, roles):
    """Headers and widths that differ from the database, on any of the Revit schedules. Schedules
    with the same value share a row, which says where the value is unless it's all of them."""
    database_columns = {column["parameter"]: column for column in spec["columns"]}
    # {(kind, parameter): {value: [Revit schedule names]}}, in the order the columns come.
    found = {}
    for role in ALL_ROLES:
        sent = roles.get(role)
        for column in (sent or {}).get("columns", ()):
            parameter = column["parameter"]
            wanted = database_columns.get(parameter)
            if wanted is None:
                continue
            if column["heading"] != wanted["header"]:
                found.setdefault((HEADING, parameter), {}).setdefault(column["heading"], []).append(sent["name"])
            inches = column["width_feet"] * 12
            if abs(inches - wanted["width_feet"] * 12) > WIDTH_TOLERANCE_INCHES:
                value = round(inches, 3)
                found.setdefault((WIDTH, parameter), {}).setdefault(value, []).append(sent["name"])

    differences = []
    for (kind, parameter), values in found.items():
        wanted = database_columns[parameter]
        for value, names in values.items():
            notes = []
            if len(names) < len(roles):
                notes.append(f"In {_join(names)}.")
            if len(values) > 1:
                notes.append("Revit's schedules have different values here. If you accept more than one, the last listed wins.")
            database_value = wanted["header"] if kind == HEADING else _width_text(wanted["width_feet"] * 12)
            revit_value = value if kind == HEADING else _width_text(value)
            differences.append(Difference(
                spec["name"], kind, parameter, database_value, revit_value, " ".join(notes), True,
                spec["guid"], (parameter, value),
            ))
    return differences


def _schedule_differences(catalog, spec, finished):
    guid = spec["guid"]
    name = spec["name"]
    differences = []

    def add(kind, parameter="", database_value="", revit_value="", value=None, note="", can_apply=True):
        differences.append(Difference(
            name, kind, parameter, _value_text(database_value), _value_text(revit_value), note, can_apply, guid, value,
        ))

    if finished["name"] != name:
        add(NAME, database_value=name, revit_value=finished["name"], value=finished["name"],
            note=f"Accepting keeps the filter value '{spec['filter_value']}', so it lists the same elements.")
    if bool(finished["itemize"]) != bool(spec["itemize"]):
        add(ITEMIZE, database_value=spec["itemize"], revit_value=finished["itemize"], value=bool(finished["itemize"]))
    # Older add-ins don't send sorting; an older last sync has none (not sorted).
    if "sorting" in finished:
        database_sorting = normalized_sorting(spec.get("sorting"))
        revit_sorting = normalized_sorting(finished["sorting"])
        if revit_sorting != database_sorting:
            database_text, revit_text = sorting_summary(database_sorting), sorting_summary(revit_sorting)
            if database_text == revit_text:
                # Same order, different headers, footers, blank lines or totals.
                database_text += " (Other Settings Differ)"
            add(SORTING, database_value=database_text, revit_value=revit_text, value=revit_sorting)

    database_columns = {column["parameter"]: column for column in spec["columns"]}
    unavailable = set(finished.get("unavailable", ()))
    # The macro adds the filter column itself, hidden, when the database doesn't list it.
    revit_columns = {
        column["parameter"]: column
        for column in finished["columns"]
        if column["parameter"] != SCHEDULE_FILTER_PARAM or column["parameter"] in database_columns
    }

    for parameter, column in database_columns.items():
        if parameter in revit_columns:
            continue
        if parameter in unavailable:
            add(INFORMATION, parameter, can_apply=False,
                note="Revit can't schedule this parameter here, so the macro leaves the column out.")
        else:
            add(COLUMN_REMOVED, parameter, database_value=column["header"], revit_value="(none)", value=parameter)

    shared_database = [parameter for parameter in database_columns if parameter in revit_columns]
    shared_revit = [parameter for parameter in revit_columns if parameter in database_columns]
    if shared_database != shared_revit:
        add(COLUMN_ORDER, database_value=_join(shared_database), revit_value=_join(shared_revit),
            value=list(revit_columns))

    for parameter, column in revit_columns.items():
        wanted = database_columns.get(parameter)
        if wanted is None:
            if catalog.get_param(parameter) is None:
                add(INFORMATION, parameter, revit_value=column["heading"], can_apply=False,
                    note="This Revit column's parameter isn't in the database, so it can't be added.")
                continue
            add(COLUMN_ADDED, parameter, database_value="(none)", revit_value=column["heading"],
                value={"parameter": parameter, "heading": column["heading"], "inches": column["width_feet"] * 12,
                       "hidden": column["hidden"], "order": list(revit_columns)})
            continue
        if bool(column["hidden"]) != bool(wanted["hidden"]):
            add(HIDDEN, parameter, database_value=wanted["hidden"], revit_value=column["hidden"],
                value=(parameter, bool(column["hidden"])))
    return differences


# Which side changed a difference since the last sync.
REVIT_CHANGED = "revit"
BOTH_CHANGED = "both"
BOTH_CHANGED_NOTE = "Changed in Revit and in the database since the last sync: accept to take Revit's, or leave it to keep the database's."


def schedule_differences(catalog, data):
    """Everything that differs between the catalog and the sync file's contents, by schedule.

    When the project remembers what was last synced for a schedule (``data["synced"]``: schedule
    GUID to the spec last applied or accepted), each difference says which side changed it:
    changed in Revit only (``REVIT_CHANGED``), or on both sides (``BOTH_CHANGED``, with a note).
    Differences only the database made are left out, since the add-in applies them to Revit when
    the database is saved; one information row per schedule counts them.
    """
    specs, _notes = schedule_specs(catalog)
    differences = _differences(catalog, specs, data)
    synced = data.get("synced") or {}
    if not synced:
        return differences
    baseline_specs = [synced[spec["guid"]] for spec in specs if spec["guid"] in synced]
    since_sync = {difference.key: difference for difference in _differences(catalog, baseline_specs, data, notes=False)}

    result, database_only = [], {}
    for difference in differences:
        if difference.schedule_guid not in synced or not difference.can_apply:
            result.append(difference)
            continue
        before = since_sync.get(difference.key)
        if before is None:
            # Revit still has what was last synced: only the database changed this.
            database_only.setdefault(difference.schedule_guid, []).append(difference)
            continue
        if before.database_value == difference.database_value:
            difference.origin = REVIT_CHANGED
        else:
            difference.origin = BOTH_CHANGED
            difference.note = " ".join(part for part in (BOTH_CHANGED_NOTE, difference.note) if part)
        result.append(difference)
    for guid, changes in database_only.items():
        result.append(Difference(
            changes[0].schedule_name, INFORMATION, can_apply=False, schedule_guid=guid,
            note=f"Changed in the database since the last sync ({len(changes)}): Revit gets "
                 f"{'it' if len(changes) == 1 else 'them'} when you save and apply in Revit.",
        ))
    return result


def _differences(catalog, specs, data, notes=True):
    """The differences between ``specs`` and the Revit schedules in ``data``."""
    sent = {}
    for entry in data["schedules"]:
        sent.setdefault(entry["guid"], {})[entry["role"]] = entry

    differences = []
    known = set()
    for spec in specs:
        known.add(spec["guid"])
        roles = sent.get(spec["guid"])
        if not roles:
            continue
        differences.extend(_setting_differences(spec, roles))
        finished = roles.get(FINISHED_ROLE)
        if finished is None:
            if not notes:
                continue
            differences.append(Difference(
                spec["name"], INFORMATION, can_apply=False,
                note="The Revit project has no finished schedule for this one, so it wasn't compared.",
            ))
            continue
        differences.extend(_schedule_differences(catalog, spec, finished))
        if not notes:
            continue
        spec_names = {column["parameter"] for column in spec["columns"]}
        for role in OTHER_ROLES:
            if role in roles:
                note = _other_schedule_note(spec["name"], finished, roles[role], spec_names)
                if note is not None:
                    differences.append(note)

    if not notes:
        return differences
    for guid, roles in sent.items():
        if guid not in known:
            names = _join(entry["name"] for entry in roles.values())
            differences.append(Difference(
                names, INFORMATION, can_apply=False, revit_value=names,
                note="No longer in the database.",
            ))
    for name in data.get("unlinked", ()):
        differences.append(Difference(
            name, INFORMATION, can_apply=False, revit_value=name,
            note="Not linked to a database schedule.",
        ))
    return differences


def _current_columns(schedule):
    names = [param.name for param in schedule.params]
    if schedule.field_names is None:
        # Matches what the macro builds: every parameter but the common ones.
        return [name for name in names if name not in COMMON_PARAM_NAMES]
    return names


def _reorder(schedule, revit_order):
    position = {name: index for index, name in enumerate(revit_order)}
    current = _current_columns(schedule)
    # Sorting is stable: a column Revit doesn't have keeps its place among those at the end.
    schedule.set_field_names(sorted(current, key=lambda name: position.get(name, len(position))))


def _with_column_added(current, parameter, revit_order):
    """``current`` with ``parameter`` after the column it follows in Revit. The other columns stay
    in their order: changing that is a separate choice."""
    before = set(revit_order[:revit_order.index(parameter)])
    position = max((index + 1 for index, name in enumerate(current) if name in before), default=0)
    return current[:position] + [parameter] + current[position:]


def _apply_one(catalog, schedule, difference):
    kind = difference.kind
    value = difference.value
    if kind == NAME:
        # A schedule with no filter value filters on its name; keep the elements it lists.
        old_name = schedule.name
        schedule.name = value
        if schedule.filter_value is None:
            schedule.filter_value = old_name
    elif kind == COLUMN_REMOVED:
        schedule.set_field_names([name for name in _current_columns(schedule) if name != value])
    elif kind == COLUMN_ADDED:
        parameter = value["parameter"]
        if catalog.get_param(parameter) is None:
            raise ValueError(f"'{parameter}' isn't a parameter in the database.")
        schedule.set_field_names(_with_column_added(_current_columns(schedule), parameter, value["order"]))
        schedule.override_param(parameter, header_text=value["heading"], grid_column_width=value["inches"])
        schedule.set_field_hidden(parameter, bool(value["hidden"]))
    elif kind == COLUMN_ORDER:
        _reorder(schedule, value)
    elif kind == HEADING:
        schedule.override_param(value[0], header_text=value[1])
    elif kind == WIDTH:
        schedule.override_param(value[0], grid_column_width=value[1])
    elif kind == HIDDEN:
        schedule.set_field_hidden(value[0], value[1])
    elif kind == ITEMIZE:
        schedule.itemize = value
    elif kind == SORTING:
        # Raises if Revit sorts by a column the database schedule doesn't have.
        schedule.set_sorting(
            value["sort_group_fields"], value["show_grand_total"], value["show_grand_total_title"],
            value["show_grand_total_count"], value["grand_total_title"],
        )
    else:
        raise ValueError(f"Can't apply a change of kind '{kind}'.")


def apply_differences(catalog, accepted):
    """Apply the accepted differences to the catalog. Returns ``(applied, problems)``, as
    messages; a difference that can't be applied is reported and the others still go ahead."""
    applied = []
    problems = []
    by_guid = {schedule.guid: schedule for schedule in catalog.schedules}
    for difference in sorted(
        (item for item in accepted if item.can_apply),
        key=lambda item: APPLY_ORDER.index(item.kind),
    ):
        schedule = by_guid.get(difference.schedule_guid)
        label = f"{difference.schedule_name}: {difference.change}"
        if schedule is None:
            problems.append(f"{label}: the schedule is no longer in the database.")
            continue
        try:
            _apply_one(catalog, schedule, difference)
        except ValueError as exc:
            problems.append(f"{label}: {exc}")
        else:
            applied.append(label)
    return applied, problems
