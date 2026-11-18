"""Generate the Revit schedule macro (C#) from the parameter catalog.

The macro, ``CreateSchedulesFromDatabase``, goes in a Revit application macro module
(see ``revit_macro_module``), in that module's namespace. Each schedule in the
database becomes three Revit schedules:

- ``3D - {name}``: a multi-category schedule of the model elements;
- ``{name} - Working``: a Detail Items schedule with every column showing;
- ``{name}``: a Detail Items schedule with the columns marked hidden hidden.

Each lists only elements whose ``IPS_GROUP_Schedule_Name`` is the schedule's
filter value (its name unless set), is itemized or not as set, and gets the
schedule's view template when it has one.

When it runs, the macro asks (in a Windows Forms dialog) whether to rebuild all
schedules or the ones picked from a list, and whether to override Revit schedules
that already exist. Overriding updates them in place, so the Revit schedules follow
the database and keep their place on sheets; otherwise they're left as they are.

The macro keeps each Revit schedule's UniqueId in the project, against the database
schedule's GUID and which of the three it is. So a schedule renamed in the database
or in Revit is still found. When its name differs from the database's, the macro asks
whether to use the database's name, keep the Revit name, leave the schedule unchanged
or create a new schedule. A Revit schedule not tracked yet is matched by name, then
tracked from then on. The record belongs to one project: a schedule copied to another
project is matched by name there.

The generated file is a fixed routine plus a table of schedule data; only the
data changes from one database to the next.
"""

import json
from datetime import datetime
from pathlib import Path

from config.app_paths import BUNDLE_DIR
from revit_parameter_manager import COMMON_PARAM_NAMES, LINKER_PARAMETER, SCHEDULE_FILTER_PARAM

FILTER_PARAMETER = SCHEDULE_FILTER_PARAM
MODEL_PREFIX = "3D - "
# Namespace when no macro module is chosen; copying the file into a module means changing it.
DEFAULT_NAMESPACE = "RevitMacros"
WORKING_SUFFIX = " - Working"
# Extensible Storage schema of the project's record of its schedules. Never change it: projects
# would lose their record.
TRACKING_SCHEMA_GUID = "b7d4e2a6-5c1f-4f83-9a2e-6d0c8e3f1a57"
# Characters Revit doesn't allow in view names.
INVALID_VIEW_NAME_CHARACTERS = set('\\:{}[]|;<>?`~')


def revit_schedule_names(name):
    """The three Revit schedules made for database schedule ``name``: model, working, finished."""
    return [MODEL_PREFIX + name, name + WORKING_SUFFIX, name]


def _csharp_string(value) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def schedule_specs(catalog):
    """What the macro builds: ``(specs, notes)``.

    A spec is ``{"name", "guid", "filter_value", "itemize", "view_template",
    "columns": [{"parameter", "header", "width_feet", "hidden", "parts"}],
    "header_groups": [{"caption", "parameters"}]}``, plus ``"sorting"`` (``Schedule.sorting_dict``, its
    levels only on these columns) when the schedule is sorted or has grand totals. Notes explain each database schedule
    left out, and are shown in Revit when the macro runs.
    """
    specs = []
    notes = []
    taken = {}
    for schedule in catalog.schedules:
        name = schedule.name
        bad_characters = sorted(set(name) & INVALID_VIEW_NAME_CHARACTERS)
        if bad_characters:
            notes.append(f"{name}: Revit view names can't contain {' '.join(bad_characters)}; skipped.")
            continue
        clash = next((taken[revit_name] for revit_name in revit_schedule_names(name) if revit_name in taken), None)
        if clash is not None:
            notes.append(f"{name}: its Revit schedule names clash with schedule '{clash}'; skipped.")
            continue

        columns = [
            {
                "parameter": param.name,
                "header": param.header_text or param.name,
                "width_feet": param.grid_column_width / 12,
                "hidden": param.name in schedule.hidden_field_names,
                # A combined parameter's parts; none for a parameter.
                "parts": [dict(part) for part in param.parts] if getattr(param, "is_combined", False) else [],
            }
            for param in schedule.params
            if schedule.field_names is not None or param.name not in COMMON_PARAM_NAMES
        ]
        if not columns:
            notes.append(f"{name}: no columns; skipped.")
            continue

        for revit_name in revit_schedule_names(name):
            taken[revit_name] = name
        # Sort levels on the columns Revit gets (not on a combined parameter, which Revit can't sort by).
        sortable = {column["parameter"] for column in columns if not column["parts"]}
        sorting = schedule.sorting_dict()
        sorting["sort_group_fields"] = [
            field for field in sorting["sort_group_fields"] if field["parameter"] in sortable
        ]
        # Innermost (narrowest) groups first: Revit groups headers that are already grouped.
        header_groups = sorted(schedule.header_groups, key=lambda group: len(group["parameter_names"]))
        spec = {
            "name": name,
            "guid": schedule.guid,
            "filter_value": schedule.resolved_filter_value,
            "itemize": schedule.itemize,
            "view_template": schedule.view_template or "",
            "columns": columns,
            "header_groups": [
                {"caption": group["caption"], "parameters": list(group["parameter_names"])}
                for group in header_groups
            ],
        }
        # Only a sorted schedule has "sorting", as the add-in writes it, so specs compare the same.
        if sorting["sort_group_fields"] or sorting["show_grand_total"]:
            spec["sorting"] = sorting
        specs.append(spec)
    return specs, notes


def _spec_source(spec):
    lines = [
        f"            new DdmSchedule({_csharp_string(spec['name'])}, {_csharp_string(spec['guid'])}, "
        f"{_csharp_string(spec['filter_value'])}, "
        f"{'true' if spec['itemize'] else 'false'}, {_csharp_string(spec['view_template'])},"
    ]
    lines.append("                new[]")
    lines.append("                {")
    for column in spec["columns"]:
        parts = ""
        if column.get("parts"):
            parts = ", new[] { " + ", ".join(
                "new DdmPart({}, {}, {}, {})".format(*(
                    _csharp_string(part[key]) for key in ("parameter", "prefix", "suffix", "separator")
                ))
                for part in column["parts"]
            ) + " }"
        lines.append(
            "                    new DdmColumn("
            f"{_csharp_string(column['parameter'])}, {_csharp_string(column['header'])}, "
            f"{column['width_feet']:.12g}, {'true' if column['hidden'] else 'false'}{parts}),"
        )
    lines.append("                },")
    if spec["header_groups"]:
        lines.append("                new[]")
        lines.append("                {")
        for group in spec["header_groups"]:
            parameters = ", ".join(_csharp_string(name) for name in group["parameters"])
            lines.append(
                f"                    new DdmHeaderGroup({_csharp_string(group['caption'])}, new[] {{ {parameters} }}),"
            )
        lines.append("                }" + _sorting_source(spec) + "),")
    else:
        lines.append("                Array.Empty<DdmHeaderGroup>()" + _sorting_source(spec) + "),")
    return lines


def _csharp_bool(value) -> str:
    return "true" if value else "false"


def _sorting_source(spec) -> str:
    """The DdmSchedule's last argument, sorting; nothing for an unsorted schedule (the default)."""
    sorting = spec.get("sorting")
    if not sorting or (not sorting["sort_group_fields"] and not sorting["show_grand_total"]):
        return ""
    levels = ", ".join(
        "new DdmSortLevel({}, {}, {}, {}, {}, {}, {})".format(
            _csharp_string(field["parameter"]), *(
                _csharp_bool(field[key]) for key in (
                    "descending", "show_header", "show_footer", "show_footer_title", "show_footer_count",
                    "show_blank_line",
                )
            )
        )
        for field in sorting["sort_group_fields"]
    )
    levels_source = f"new[] {{ {levels} }}" if levels else "Array.Empty<DdmSortLevel>()"
    return (
        f", new DdmSorting({levels_source}, {_csharp_bool(sorting['show_grand_total'])}, "
        f"{_csharp_bool(sorting['show_grand_total_title'])}, {_csharp_bool(sorting['show_grand_total_count'])}, "
        f"{_csharp_string(sorting['grand_total_title'])})"
    )


def generate_schedule_macro_source(catalog, source_name="the database", namespace=DEFAULT_NAMESPACE,
                                   widths_folder="", sync_path="") -> str:
    """The C# source of the ``CreateSchedulesFromDatabase`` macro for ``catalog``,
    in ``namespace`` (the macro module's). ``ExportScheduleWidths`` writes to ``widths_folder``."""
    specs, notes = schedule_specs(catalog)
    data = []
    for spec in specs:
        data.extend(_spec_source(spec))
    note_lines = [f"            {_csharp_string(note)}," for note in notes]
    return (
        _macro_template()
        .replace("/*SOURCE*/", source_name.replace("\n", " "))
        .replace("/*NAMESPACE*/", namespace)
        .replace("/*WIDTHS_FOLDER*/", _csharp_string(widths_folder))
        .replace("/*SYNC_PATH*/", _csharp_string(sync_path))
        .replace("            /*NOTES*/\n", "".join(line + "\n" for line in note_lines))
        .replace("            /*SCHEDULES*/\n", "".join(line + "\n" for line in data))
    )


# The version of the schedules file; the add-in's DdmScheduleData.Version must match.
SCHEDULE_DATA_VERSION = 1


def linker_data(catalog):
    """What the add-in's Linker buttons need: the Linker ID parameter and, for each family that has
    it, its role ("primary" holds the design data, "linked" is a tag-only copy), the prefix for new
    IDs and the tag parameters to copy, with GUIDs so renamed parameters still match in Revit."""
    def guid(name):
        param = catalog.get_param(name)
        return (param.guid or "") if param is not None else ""

    return {
        "parameter": LINKER_PARAMETER,
        "guid": guid(LINKER_PARAMETER),
        "families": {
            name: {
                "role": info["role"],
                "prefix": info["prefix"],
                "tag_parameters": [{"name": tag, "guid": guid(tag)} for tag in info["tag_parameters"]],
            }
            for name, info in sorted(catalog.linker_families().items())
        },
    }


def generate_schedule_data(catalog, source_name="the database", saved_at=None):
    """The schedules file the Revit add-in builds from, as a dict (written as JSON by Save):
    ``{"version", "source", "saved_at", "notes", "schedules": [<schedule_specs spec>], "linker"}``.
    ``linker`` (see ``linker_data``) is optional: older add-ins ignore it."""
    specs, notes = schedule_specs(catalog)
    if saved_at is None:
        saved_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return {"version": SCHEDULE_DATA_VERSION, "source": source_name, "saved_at": saved_at,
            "notes": notes, "schedules": specs, "linker": linker_data(catalog)}


# Shape of the files ExportScheduleWidths writes (read by revit_widths):
# {"version", "project", "exported_at", "skipped_database_schedules",
#  "schedules": [{"name", "category", "columns": [{"parameter", "guid", "heading", "width_feet", "hidden"}]}]}
WIDTHS_EXPORT_VERSION = 1


# Header line that marks a file as generated, so an older copy can be found and replaced.
GENERATED_HEADER = "// Generated by Design Data Manager"
# Earlier versions of the generator started their files with this.
_OLD_GENERATED_HEADERS = ("// Generated by Revit Parameter Manager",)
MACRO_FILE_NAME = "CreateSchedulesFromDatabase.cs"


def install_macro(source, module_dir):
    """Write the macro into a Revit macro module's source folder.

    Any other generated macro file there is removed: two copies would define
    ``CreateSchedulesFromDatabase`` twice and the module wouldn't build. Returns
    ``(path, removed_paths)``, or ``(None, [])`` when the folder doesn't exist.
    """
    module_dir = Path(module_dir)
    if not module_dir.is_dir():
        return None, []
    target = module_dir / MACRO_FILE_NAME
    removed = []
    for path in sorted(module_dir.glob("*.cs")):
        if path.name == target.name:
            continue
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            first_line = handle.readline()
        if first_line.startswith((GENERATED_HEADER,) + _OLD_GENERATED_HEADERS):
            path.unlink()
            removed.append(path)
    target.write_text(source, encoding="utf-8")
    return target, removed


# The routine the macro runs is shared with the Revit add-in, as C# files in revit-addin/Shared
# (bundled into the .exe). The macro wraps it: ThisApplication holds the database's schedules and
# its public methods, the ones Macro Manager lists, run the routine.
SHARED_SOURCE_DIR = BUNDLE_DIR / "revit-addin" / "Shared"
SHARED_SOURCE_FILES = ("ScheduleData.cs", "ScheduleRoutine.cs")


def _shared_source():
    """The shared C# files as ``(usings, bodies)``: their ``using`` lines, merged, and the rest."""
    usings, bodies = [], []
    for name in SHARED_SOURCE_FILES:
        lines = (SHARED_SOURCE_DIR / name).read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
        for line in lines:
            if line.startswith("using ") and line not in usings:
                usings.append(line)
        bodies.append("\n".join(line for line in lines if not line.startswith(("using ", "//"))).strip("\n"))
    return usings, bodies


def _macro_template():
    usings, bodies = _shared_source()
    return (
        GENERATED_HEADER + """ from /*SOURCE*/. Saving the database rewrites this file;
// don't edit it by hand. Build its macro module in the Macro Manager, then run
// CreateSchedulesFromDatabase (or SendSchedulesToDatabase, ExportScheduleWidths). The routine itself is the Revit add-in's
// (revit-addin/Shared in the Design Data Manager), copied in below.
""" + "\n".join(usings) + """

namespace /*NAMESPACE*/
{
    using DesignDataManager.Schedules;

    public partial class ThisApplication
    {
        // Database schedules the generator left out, and why.
        private static readonly string[] DdmGeneratorNotes =
        {
            /*NOTES*/
        };

        private static readonly DdmSchedule[] DdmSchedules =
        {
            /*SCHEDULES*/
        };

        // Where ExportScheduleWidths writes, one file per project, for the Design Data Manager to read.
        private const string DdmWidthsFolder = /*WIDTHS_FOLDER*/;
        // Where SendSchedulesToDatabase writes, for the Design Data Manager's Review Revit Changes.
        private const string DdmSyncPath = /*SYNC_PATH*/;

        /// <summary>
        /// Create or update three Revit schedules for each database schedule chosen: a
        /// multi-category model schedule ("3D - name"), a Detail Items working schedule showing
        /// every column ("name - Working") and a Detail Items schedule with hidden columns hidden
        /// ("name").
        /// </summary>
        public void CreateSchedulesFromDatabase()
        {
            new DdmScheduleRoutine(DdmSchedules, DdmGeneratorNotes).CreateSchedules(ActiveUIDocument?.Document, MainWindowHandle);
        }

        /// <summary>
        /// Write the column widths of this project's schedules to a file, so the Design Data
        /// Manager can find each parameter's typical width. Changes nothing in Revit.
        /// </summary>
        public void ExportScheduleWidths()
        {
            new DdmScheduleRoutine(DdmSchedules, DdmGeneratorNotes).ExportScheduleWidths(ActiveUIDocument?.Document, DdmWidthsFolder);
        }

        /// <summary>
        /// Write what this project's schedules look like to a file, so the Design Data Manager can
        /// show how they differ from the database (Review Revit Changes). Changes nothing in Revit.
        /// </summary>
        public void SendSchedulesToDatabase()
        {
            new DdmScheduleRoutine(DdmSchedules, DdmGeneratorNotes).SendSchedules(ActiveUIDocument?.Document, DdmSyncPath);
        }
    }
}

""" + "\n\n".join(bodies) + "\n"
    )
