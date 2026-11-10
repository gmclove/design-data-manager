"""Typical column widths from Revit schedules.

The macro's ``ExportScheduleWidths`` writes one file per Revit project (see
``revit_schedule_macro_generator``) with the column widths of the project's own schedules. Here
those files are read, each parameter's typical width is worked out, and chosen ones become the
parameters' Default Column Widths.

The typical width (user, 2026-11-09) is the most common width among columns someone has adjusted:
columns still at Revit's width for a newly added field, and hidden columns, don't count. A tie goes
to the wider width.
"""

import json
from collections import Counter
from pathlib import Path

# The width Revit gives a field added to a schedule, in inches. Columns at this width were never
# adjusted, so they don't count. Check it against a real export.
REVIT_DEFAULT_COLUMN_WIDTH_IN = 1.0
# Widths are compared in 1/16" steps.
WIDTH_STEP_IN = 1 / 16


def snap_width(inches):
    """``inches`` to the nearest 1/16"."""
    return round(round(float(inches) / WIDTH_STEP_IN) * WIDTH_STEP_IN, 4)


def load_width_exports(folder):
    """Every ``*.widths.json`` file in ``folder``, as ``[(path, data)]``; unreadable ones are skipped
    and listed as ``(path, error)`` in the second value returned."""
    exports, problems = [], []
    for path in sorted(Path(folder).glob("*.widths.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or not isinstance(data.get("schedules"), list):
                raise ValueError("not a column widths export")
        except (OSError, ValueError) as exc:
            problems.append((path, str(exc)))
            continue
        exports.append((path, data))
    return exports, problems


def typical_widths(catalog, exports):
    """One row per catalog parameter found in the exports, sorted by name::

        {"parameter", "current_default", "typical", "agree", "adjusted_uses", "total_uses",
         "projects", "schedules", "spread"}

    ``typical`` is ``None`` when every use is at Revit's default width. ``spread`` lists every
    adjusted width as ``[(width, count)]``, most used first.
    """
    # A column's parameter: by shared parameter GUID (a rename keeps it), then by name.
    by_guid = {(param.guid or "").lower(): param for param in catalog.params if param.guid}
    uses = {}
    for _path, data in exports:
        project = data.get("project") or ""
        for schedule in data.get("schedules", []):
            for column in schedule.get("columns", []):
                guid = (column.get("guid") or "").lower()
                param = by_guid.get(guid) if guid else None
                if param is None:
                    param = catalog.get_param(column.get("parameter") or "")
                if param is None or column.get("hidden"):
                    continue
                try:
                    width = snap_width(float(column["width_feet"]) * 12)
                except (KeyError, TypeError, ValueError):
                    continue
                entry = uses.setdefault(param.name, {"param": param, "widths": [], "total": 0,
                                                     "projects": set(), "schedules": []})
                entry["total"] += 1
                if width == snap_width(REVIT_DEFAULT_COLUMN_WIDTH_IN) or width <= 0:
                    continue
                entry["widths"].append(width)
                entry["projects"].add(project)
                label = f"{project}: {schedule.get('name', '')}"
                if label not in entry["schedules"]:
                    entry["schedules"].append(label)

    rows = []
    for name, entry in uses.items():
        counts = Counter(entry["widths"])
        spread = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
        typical = spread[0][0] if spread else None
        rows.append({
            "parameter": name,
            "current_default": entry["param"].grid_column_width,
            "typical": typical,
            "agree": counts[typical] if typical is not None else 0,
            "adjusted_uses": len(entry["widths"]),
            "total_uses": entry["total"],
            "projects": sorted(entry["projects"]),
            "schedules": entry["schedules"],
            "spread": spread,
        })
    return sorted(rows, key=lambda row: row["parameter"].lower())


def apply_typical_widths(catalog, choices):
    """Make ``choices`` (``{parameter name: width in inches}``) the parameters' Default Column Widths.

    Schedules without their own width follow the new default; a schedule's own width equal to the
    new default is cleared, since it no longer says anything; other schedule widths stay (user,
    2026-11-09). Returns ``{"parameters", "overrides_cleared", "schedules_changed"}``.
    """
    changed, cleared, schedules_changed = [], 0, set()
    for name, width in choices.items():
        param = catalog.get_param(name)
        if param is None:
            raise ValueError(f"Parameter not found: {name}")
        width = snap_width(width)
        if param.grid_column_width == width:
            continue
        for schedule in catalog.schedules:
            if name not in {column.name for column in schedule.params}:
                continue
            override = schedule.grid_column_width_overrides.get(name)
            if override is None:
                schedules_changed.add(schedule.name)
            elif snap_width(override) == width:
                del schedule.grid_column_width_overrides[name]
                cleared += 1
        param.grid_column_width = width
        changed.append(name)
    return {"parameters": changed, "overrides_cleared": cleared, "schedules_changed": sorted(schedules_changed)}
