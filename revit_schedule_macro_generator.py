"""Generate the Revit schedule macro (C#) from the parameter catalog.

The macro, ``CreateSchedulesFromDatabase``, goes in the ``GLoveMacros`` application
module. Each schedule in the database becomes three Revit schedules:

- ``3D - {name}``: a multi-category schedule of the model elements;
- ``{name} - Working``: a Detail Items schedule with every column showing;
- ``{name}``: a Detail Items schedule with the columns marked hidden hidden.

Each lists only elements whose ``IPS_GROUP_Schedule_Name`` is the database
schedule's name. Running the macro again updates schedules it made before, so
the Revit schedules follow the database.

The generated file is a fixed routine plus a table of schedule data; only the
data changes from one database to the next.
"""

import json
from pathlib import Path

from revit_parameter_manager import COMMON_PARAM_NAMES

FILTER_PARAMETER = "IPS_GROUP_Schedule_Name"
MODEL_PREFIX = "3D - "
WORKING_SUFFIX = " - Working"
# Characters Revit doesn't allow in view names.
INVALID_VIEW_NAME_CHARACTERS = set('\\:{}[]|;<>?`~')


def revit_schedule_names(name):
    """The three Revit schedules made for database schedule ``name``: model, working, finished."""
    return [MODEL_PREFIX + name, name + WORKING_SUFFIX, name]


def _csharp_string(value) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def schedule_specs(catalog):
    """What the macro builds: ``(specs, notes)``.

    A spec is ``{"name", "columns": [{"parameter", "header", "width_feet", "hidden"}],
    "header_groups": [{"caption", "parameters"}]}``. Notes explain each database schedule
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
            }
            for param in schedule.params
            if schedule.field_names is not None or param.name not in COMMON_PARAM_NAMES
        ]
        if not columns:
            notes.append(f"{name}: no columns; skipped.")
            continue

        for revit_name in revit_schedule_names(name):
            taken[revit_name] = name
        # Innermost (narrowest) groups first: Revit groups headers that are already grouped.
        header_groups = sorted(schedule.header_groups, key=lambda group: len(group["parameter_names"]))
        specs.append({
            "name": name,
            "columns": columns,
            "header_groups": [
                {"caption": group["caption"], "parameters": list(group["parameter_names"])}
                for group in header_groups
            ],
        })
    return specs, notes


def _spec_source(spec):
    lines = [f"            new DdmSchedule({_csharp_string(spec['name'])},"]
    lines.append("                new[]")
    lines.append("                {")
    for column in spec["columns"]:
        lines.append(
            "                    new DdmColumn("
            f"{_csharp_string(column['parameter'])}, {_csharp_string(column['header'])}, "
            f"{column['width_feet']:.12g}, {'true' if column['hidden'] else 'false'}),"
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
        lines.append("                }),")
    else:
        lines.append("                Array.Empty<DdmHeaderGroup>()),")
    return lines


def generate_schedule_macro_source(catalog, source_name="the database") -> str:
    """The C# source of the ``CreateSchedulesFromDatabase`` macro for ``catalog``."""
    specs, notes = schedule_specs(catalog)
    data = []
    for spec in specs:
        data.extend(_spec_source(spec))
    note_lines = [f"            {_csharp_string(note)}," for note in notes]
    return (
        MACRO_TEMPLATE
        .replace("/*SOURCE*/", source_name.replace("\n", " "))
        .replace("/*FILTER_PARAMETER*/", _csharp_string(FILTER_PARAMETER))
        .replace("/*MODEL_PREFIX*/", _csharp_string(MODEL_PREFIX))
        .replace("/*WORKING_SUFFIX*/", _csharp_string(WORKING_SUFFIX))
        .replace("            /*NOTES*/\n", "".join(line + "\n" for line in note_lines))
        .replace("            /*SCHEDULES*/\n", "".join(line + "\n" for line in data))
    )


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

MACRO_TEMPLATE = GENERATED_HEADER + """ from /*SOURCE*/. Saving the database rewrites this file;
// don't edit it by hand. Build the GLoveMacros module in the Macro Manager, then run
// CreateSchedulesFromDatabase.
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using System;
using System.Collections.Generic;
using System.Linq;

namespace GLoveMacros
{
    public partial class ThisApplication
    {
        private const string DdmTitle = "Schedule Generator";

        // A schedule lists the elements whose value of this parameter is the schedule's name.
        private const string DdmFilterParameter = /*FILTER_PARAMETER*/;
        private const string DdmModelPrefix = /*MODEL_PREFIX*/;
        private const string DdmWorkingSuffix = /*WORKING_SUFFIX*/;

        // Database schedules the generator left out, and why.
        private static readonly string[] DdmGeneratorNotes =
        {
            /*NOTES*/
        };

        private static readonly DdmSchedule[] DdmSchedules =
        {
            /*SCHEDULES*/
        };

        /// <summary>
        /// Create or update three Revit schedules for each database schedule: a multi-category
        /// model schedule ("3D - name"), a Detail Items working schedule showing every column
        /// ("name - Working") and a Detail Items schedule with hidden columns hidden ("name").
        /// </summary>
        public void CreateSchedulesFromDatabase()
        {
            Document? doc = ActiveUIDocument?.Document;
            if (doc == null)
            {
                TaskDialog.Show(DdmTitle, "No active Revit document is open.");
                return;
            }

            var created = new List<string>();
            var updated = new List<string>();
            var problems = new List<string>(DdmGeneratorNotes);
            ElementId detailItems = new ElementId(BuiltInCategory.OST_DetailComponents);

            foreach (DdmSchedule spec in DdmSchedules)
            {
                DdmBuildSchedule(doc, DdmModelPrefix + spec.Name, ElementId.InvalidElementId, spec, true, created, updated, problems);
                DdmBuildSchedule(doc, spec.Name + DdmWorkingSuffix, detailItems, spec, false, created, updated, problems);
                DdmBuildSchedule(doc, spec.Name, detailItems, spec, true, created, updated, problems);
            }

            string message = $"Created {created.Count} schedule(s), updated {updated.Count}.";
            if (problems.Count > 0)
            {
                message += "\\n\\nProblems:\\n" + string.Join("\\n", problems);
            }
            TaskDialog.Show(DdmTitle, message);
        }

        private static void DdmBuildSchedule(
            Document doc, string viewName, ElementId categoryId, DdmSchedule spec, bool hideHiddenColumns,
            List<string> created, List<string> updated, List<string> problems)
        {
            ViewSchedule? existing = new FilteredElementCollector(doc)
                .OfClass(typeof(ViewSchedule))
                .Cast<ViewSchedule>()
                .FirstOrDefault(view => !view.IsTemplate && view.Name == viewName);
            if (existing != null && !existing.Definition.CategoryId.Equals(categoryId))
            {
                problems.Add($"{viewName}: a schedule with this name lists a different category; left unchanged.");
                return;
            }

            using (var tx = new Transaction(doc, (existing == null ? "Create" : "Update") + " Schedule - " + viewName))
            {
                try
                {
                    tx.Start();
                    ViewSchedule schedule = existing ?? ViewSchedule.CreateSchedule(doc, categoryId);
                    if (existing == null)
                    {
                        schedule.Name = viewName;
                    }

                    ScheduleDefinition definition = schedule.Definition;
                    definition.ClearFilters();
                    definition.ClearFields();
                    IList<SchedulableField> schedulable = definition.GetSchedulableFields();

                    var visible = new List<string>();
                    ScheduleField? filterField = null;
                    foreach (DdmColumn column in spec.Columns)
                    {
                        SchedulableField? candidate = DdmFindField(doc, schedulable, column.Parameter);
                        if (candidate == null)
                        {
                            problems.Add($"{viewName}: no schedulable parameter '{column.Parameter}'; column left out.");
                            continue;
                        }
                        ScheduleField field = definition.AddField(candidate);
                        field.ColumnHeading = column.Header;
                        field.GridColumnWidth = column.WidthFeet;
                        field.IsHidden = hideHiddenColumns && column.Hidden;
                        try
                        {
                            field.HorizontalAlignment = ScheduleHorizontalAlignment.Center;
                        }
                        catch (Autodesk.Revit.Exceptions.ApplicationException)
                        {
                            // Some fields can't be centered; keep the default alignment.
                        }
                        if (!field.IsHidden)
                        {
                            visible.Add(column.Parameter);
                        }
                        if (column.Parameter == DdmFilterParameter)
                        {
                            filterField = field;
                        }
                    }
                    if (definition.GetFieldCount() == 0)
                    {
                        tx.RollBack();
                        problems.Add($"{viewName}: none of its parameters can be scheduled here; not {(existing == null ? "created" : "updated")}.");
                        return;
                    }

                    if (filterField == null)
                    {
                        SchedulableField? candidate = DdmFindField(doc, schedulable, DdmFilterParameter);
                        if (candidate != null)
                        {
                            filterField = definition.AddField(candidate);
                            filterField.IsHidden = true;
                        }
                    }
                    if (filterField == null)
                    {
                        problems.Add($"{viewName}: no '{DdmFilterParameter}' parameter to filter on; it lists every element of its category.");
                    }
                    else
                    {
                        definition.AddFilter(new ScheduleFilter(filterField.FieldId, ScheduleFilterType.Equal, spec.Name));
                    }

                    foreach (DdmHeaderGroup group in spec.HeaderGroups)
                    {
                        List<int> columns = group.Parameters
                            .Select(parameter => visible.IndexOf(parameter))
                            .Where(index => index >= 0)
                            .OrderBy(index => index)
                            .ToList();
                        if (columns.Count == 0)
                        {
                            continue;
                        }
                        int left = columns[0];
                        int right = columns[columns.Count - 1];
                        if (right - left + 1 != columns.Count || !schedule.CanGroupHeaders(0, left, 0, right))
                        {
                            problems.Add($"{viewName}: couldn't group headers under '{group.Caption}'.");
                            continue;
                        }
                        schedule.GroupHeaders(0, left, 0, right, group.Caption);
                    }

                    tx.Commit();
                    (existing == null ? created : updated).Add(viewName);
                }
                catch (Exception ex)
                {
                    if (tx.GetStatus() == TransactionStatus.Started)
                    {
                        tx.RollBack();
                    }
                    problems.Add($"{viewName}: {ex.Message}");
                }
            }
        }

        private static SchedulableField? DdmFindField(Document doc, IList<SchedulableField> fields, string parameter)
        {
            // Prefer the instance parameter when a name is schedulable more than one way.
            return fields
                .Where(field => field.GetName(doc) == parameter)
                .OrderBy(field => field.FieldType == ScheduleFieldType.Instance ? 0 : 1)
                .FirstOrDefault();
        }

        private sealed class DdmColumn
        {
            public DdmColumn(string parameter, string header, double widthFeet, bool hidden)
            {
                Parameter = parameter;
                Header = header;
                WidthFeet = widthFeet;
                Hidden = hidden;
            }

            public string Parameter { get; }
            public string Header { get; }
            public double WidthFeet { get; }
            public bool Hidden { get; }
        }

        private sealed class DdmHeaderGroup
        {
            public DdmHeaderGroup(string caption, string[] parameters)
            {
                Caption = caption;
                Parameters = parameters;
            }

            public string Caption { get; }
            public string[] Parameters { get; }
        }

        private sealed class DdmSchedule
        {
            public DdmSchedule(string name, DdmColumn[] columns, DdmHeaderGroup[] headerGroups)
            {
                Name = name;
                Columns = columns;
                HeaderGroups = headerGroups;
            }

            public string Name { get; }
            public DdmColumn[] Columns { get; }
            public DdmHeaderGroup[] HeaderGroups { get; }
        }
    }
}
"""
