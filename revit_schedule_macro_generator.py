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
from pathlib import Path

from revit_parameter_manager import COMMON_PARAM_NAMES, SCHEDULE_FILTER_PARAM

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
        # Innermost (narrowest) groups first: Revit groups headers that are already grouped.
        header_groups = sorted(schedule.header_groups, key=lambda group: len(group["parameter_names"]))
        specs.append({
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
        })
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
        lines.append("                }),")
    else:
        lines.append("                Array.Empty<DdmHeaderGroup>()),")
    return lines


def generate_schedule_macro_source(catalog, source_name="the database", namespace=DEFAULT_NAMESPACE,
                                   widths_folder="") -> str:
    """The C# source of the ``CreateSchedulesFromDatabase`` macro for ``catalog``,
    in ``namespace`` (the macro module's). ``ExportScheduleWidths`` writes to ``widths_folder``."""
    specs, notes = schedule_specs(catalog)
    data = []
    for spec in specs:
        data.extend(_spec_source(spec))
    note_lines = [f"            {_csharp_string(note)}," for note in notes]
    return (
        MACRO_TEMPLATE
        .replace("/*SOURCE*/", source_name.replace("\n", " "))
        .replace("/*NAMESPACE*/", namespace)
        .replace("/*FILTER_PARAMETER*/", _csharp_string(FILTER_PARAMETER))
        .replace("/*MODEL_PREFIX*/", _csharp_string(MODEL_PREFIX))
        .replace("/*WORKING_SUFFIX*/", _csharp_string(WORKING_SUFFIX))
        .replace("/*TRACKING_SCHEMA*/", TRACKING_SCHEMA_GUID)
        .replace("/*WIDTHS_FOLDER*/", _csharp_string(widths_folder))
        .replace("/*WIDTHS_VERSION*/", str(WIDTHS_EXPORT_VERSION))
        .replace("            /*NOTES*/\n", "".join(line + "\n" for line in note_lines))
        .replace("            /*SCHEDULES*/\n", "".join(line + "\n" for line in data))
    )


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


MACRO_TEMPLATE = GENERATED_HEADER + """ from /*SOURCE*/. Saving the database rewrites this file;
// don't edit it by hand. Build its macro module in the Macro Manager, then run
// CreateSchedulesFromDatabase (or ExportScheduleWidths).
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.ExtensibleStorage;
using Autodesk.Revit.UI;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Drawing = System.Drawing;
using WinForms = System.Windows.Forms;

namespace /*NAMESPACE*/
{
    public partial class ThisApplication
    {
        private const string DdmTitle = "Schedule Generator";

        // A schedule lists the elements whose value of this parameter is the schedule's filter value.
        private const string DdmFilterParameter = /*FILTER_PARAMETER*/;
        private const string DdmModelPrefix = /*MODEL_PREFIX*/;
        private const string DdmWorkingSuffix = /*WORKING_SUFFIX*/;

        // Where ExportScheduleWidths writes, one file per project, for the Design Data Manager to read.
        private const string DdmWidthsFolder = /*WIDTHS_FOLDER*/;
        private const int DdmWidthsVersion = /*WIDTHS_VERSION*/;

        // Which of a database schedule's three Revit schedules this is, in the project's record.
        private const string DdmModelRole = "Model";
        private const string DdmWorkingRole = "Working";
        private const string DdmFinishedRole = "Finished";

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
        /// Create or update three Revit schedules for each database schedule chosen: a
        /// multi-category model schedule ("3D - name"), a Detail Items working schedule showing
        /// every column ("name - Working") and a Detail Items schedule with hidden columns
        /// hidden ("name"). A dialog asks which schedules to build and whether to override
        /// schedules that already exist. The project records which Revit schedules are which, so
        /// a rename on either side finds the same schedules, and the macro asks what to do.
        /// </summary>
        public void CreateSchedulesFromDatabase()
        {
            Document? doc = ActiveUIDocument?.Document;
            if (doc == null)
            {
                TaskDialog.Show(DdmTitle, "No active Revit document is open.");
                return;
            }

            var tracker = new DdmTracker(doc);
            DdmChoice? choice = DdmAskWhatToBuild(doc, tracker, MainWindowHandle);
            if (choice == null)
            {
                return;
            }

            var created = new List<string>();
            var updated = new List<string>();
            var renamed = new List<string>();
            var namePrompt = new DdmNamePrompt();
            var skipped = new List<string>();
            var problems = new List<string>(DdmGeneratorNotes);
            ElementId detailItems = new ElementId(BuiltInCategory.OST_DetailComponents);

            foreach (DdmSchedule spec in DdmSchedules.Where(spec => choice.Names.Contains(spec.Name)))
            {
                DdmBuildSchedule(doc, tracker, namePrompt, DdmModelRole, DdmModelPrefix + spec.Name, ElementId.InvalidElementId, spec, true, choice.OverrideExisting, created, updated, renamed, skipped, problems);
                DdmBuildSchedule(doc, tracker, namePrompt, DdmWorkingRole, spec.Name + DdmWorkingSuffix, detailItems, spec, false, choice.OverrideExisting, created, updated, renamed, skipped, problems);
                DdmBuildSchedule(doc, tracker, namePrompt, DdmFinishedRole, spec.Name, detailItems, spec, true, choice.OverrideExisting, created, updated, renamed, skipped, problems);
            }

            string message = $"Created {created.Count} schedule(s), updated {updated.Count}.";
            if (renamed.Count > 0)
            {
                message += $"\\n\\nRenamed {renamed.Count} to the database's name:\\n" + DdmShortList(renamed);
            }
            if (skipped.Count > 0)
            {
                message += $"\\n\\nLeft {skipped.Count} existing schedule(s) as they were:\\n"
                    + DdmShortList(skipped);
            }
            if (problems.Count > 0)
            {
                message += "\\n\\nProblems:\\n" + string.Join("\\n", problems);
            }
            TaskDialog.Show(DdmTitle, message);
        }

        /// <summary>
        /// Write the column widths of this project's schedules to a file, so the Design Data
        /// Manager can find each parameter's typical width. Changes nothing in Revit. Schedules this
        /// macro builds from the database are left out: they only repeat the database's widths.
        /// </summary>
        public void ExportScheduleWidths()
        {
            Document? doc = ActiveUIDocument?.Document;
            if (doc == null)
            {
                TaskDialog.Show(DdmTitle, "No active Revit document is open.");
                return;
            }
            if (DdmWidthsFolder.Length == 0)
            {
                TaskDialog.Show(DdmTitle, "This macro doesn't know where the database is. Save the database in the Design Data Manager and build the macro again.");
                return;
            }

            var tracker = new DdmTracker(doc);
            HashSet<string> recorded = tracker.RecordedIds();
            var databaseNames = new HashSet<string>(DdmSchedules.SelectMany(
                spec => new[] { DdmModelPrefix + spec.Name, spec.Name + DdmWorkingSuffix, spec.Name }));
            var schedules = new List<object>();
            int skipped = 0;
            int columnCount = 0;
            IEnumerable<ViewSchedule> views = new FilteredElementCollector(doc)
                .OfClass(typeof(ViewSchedule))
                .Cast<ViewSchedule>()
                .Where(view => !view.IsTemplate && !view.IsTitleblockRevisionSchedule && !view.IsInternalKeynoteSchedule)
                .OrderBy(view => view.Name);
            foreach (ViewSchedule view in views)
            {
                if (recorded.Contains(view.UniqueId) || databaseNames.Contains(view.Name))
                {
                    skipped++;
                    continue;
                }
                List<object> columns = DdmDescribeWidths(doc, view.Definition);
                if (columns.Count == 0)
                {
                    continue;
                }
                columnCount += columns.Count;
                schedules.Add(new
                {
                    name = view.Name,
                    category = Category.GetCategory(doc, view.Definition.CategoryId)?.Name ?? "Multi-Category",
                    columns,
                });
            }

            string fileName = string.Concat(doc.Title.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c));
            string target = Path.Combine(DdmWidthsFolder, fileName + ".widths.json");
            try
            {
                Directory.CreateDirectory(DdmWidthsFolder);
                string json = JsonSerializer.Serialize(new
                {
                    version = DdmWidthsVersion,
                    project = doc.Title,
                    exported_at = DateTimeOffset.Now.ToString("yyyy-MM-dd HH:mm"),
                    skipped_database_schedules = skipped,
                    schedules,
                }, new JsonSerializerOptions { WriteIndented = true });
                // Through a temporary file, so the app never reads a half-written one.
                string temporary = target + ".tmp";
                File.WriteAllText(temporary, json);
                File.Move(temporary, target, true);
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
            {
                TaskDialog.Show(DdmTitle, $"Couldn't write {target}:\\n{ex.Message}");
                return;
            }

            TaskDialog.Show(DdmTitle,
                $"Exported the column widths of {schedules.Count} schedule(s), {columnCount} columns, to:\\n{target}"
                + $"\\n\\nLeft out {skipped} schedule(s) the Design Data Manager builds."
                + "\\n\\nIn the Design Data Manager, click Column Widths From Revit on the Parameters tab.");
        }

        /// <summary>A schedule's parameter columns: name, shared parameter GUID, heading, width, hidden.</summary>
        private static List<object> DdmDescribeWidths(Document doc, ScheduleDefinition definition)
        {
            var columns = new List<object>();
            foreach (ScheduleFieldId id in definition.GetFieldOrder())
            {
                ScheduleField field = definition.GetField(id);
                // Only parameters: calculated values and the like have no database parameter.
                if (field.FieldType == ScheduleFieldType.Formula || field.FieldType == ScheduleFieldType.Percentage
                    || field.FieldType == ScheduleFieldType.Count)
                {
                    continue;
                }
                string? guid = (doc.GetElement(field.ParameterId) as SharedParameterElement)?.GuidValue.ToString();
                columns.Add(new
                {
                    parameter = field.GetName(),
                    guid,
                    heading = field.ColumnHeading,
                    width_feet = field.GridColumnWidth,
                    hidden = field.IsHidden,
                });
            }
            return columns;
        }

        private static string DdmShortList(List<string> names)
        {
            const int shown = 15;
            string list = string.Join("\\n", names.Take(shown));
            return names.Count > shown ? list + $"\\n...and {names.Count - shown} more" : list;
        }

        /// <summary>
        /// Ask which schedules to build (all, or those checked in a searchable list) and whether
        /// to override Revit schedules that already exist. Returns null if the user cancels.
        /// </summary>
        private static DdmChoice? DdmAskWhatToBuild(Document doc, DdmTracker tracker, IntPtr owner)
        {
            var inProject = new HashSet<string>(new FilteredElementCollector(doc)
                .OfClass(typeof(ViewSchedule))
                .Cast<ViewSchedule>()
                .Where(view => !view.IsTemplate)
                .Select(view => view.Name));
            var alreadyBuilt = new HashSet<string>(DdmSchedules
                .Where(spec => DdmRevitNames(spec.Name).Any(inProject.Contains) || tracker.HasAny(spec))
                .Select(spec => spec.Name));
            List<string> names = DdmSchedules.Select(spec => spec.Name).ToList();
            var chosen = new HashSet<string>();

            using var form = new WinForms.Form
            {
                Text = DdmTitle,
                Font = new Drawing.Font("Segoe UI", 9F),
                AutoScaleMode = WinForms.AutoScaleMode.Font,
                StartPosition = WinForms.FormStartPosition.CenterParent,
                Size = new Drawing.Size(560, 680),
                MinimumSize = new Drawing.Size(420, 420),
                MinimizeBox = false,
                MaximizeBox = false,
                ShowInTaskbar = false,
            };
            var allRadio = new WinForms.RadioButton { Text = $"Rebuild All Schedules ({names.Count})", Checked = true, AutoSize = true };
            var selectedRadio = new WinForms.RadioButton { Text = "Rebuild Selected Schedules:", AutoSize = true };
            var search = new WinForms.TextBox { PlaceholderText = "Search", Dock = WinForms.DockStyle.Fill };
            var list = new WinForms.CheckedListBox { CheckOnClick = true, IntegralHeight = false, Dock = WinForms.DockStyle.Fill };
            var selectAll = new WinForms.Button { Text = "Select All", AutoSize = true };
            var clear = new WinForms.Button { Text = "Clear", AutoSize = true };
            var note = new WinForms.Label
            {
                Text = "\\u2713 = already in this project (its 3 Revit schedules, or some of them).",
                AutoSize = true,
                ForeColor = Drawing.SystemColors.GrayText,
            };
            var overrideBox = new WinForms.CheckBox { Text = "Override Existing Schedules", Checked = true, AutoSize = true };
            var build = new WinForms.Button { DialogResult = WinForms.DialogResult.OK, AutoSize = true };
            var cancel = new WinForms.Button { Text = "Cancel", DialogResult = WinForms.DialogResult.Cancel, AutoSize = true };

            var listButtons = new WinForms.FlowLayoutPanel { AutoSize = true, Dock = WinForms.DockStyle.Fill, Margin = WinForms.Padding.Empty };
            listButtons.Controls.AddRange(new WinForms.Control[] { selectAll, clear, note });
            var buttons = new WinForms.FlowLayoutPanel
            {
                FlowDirection = WinForms.FlowDirection.RightToLeft,
                AutoSize = true,
                Dock = WinForms.DockStyle.Fill,
                Margin = WinForms.Padding.Empty,
            };
            buttons.Controls.AddRange(new WinForms.Control[] { cancel, build });
            var layout = new WinForms.TableLayoutPanel { Dock = WinForms.DockStyle.Fill, ColumnCount = 1, Padding = new WinForms.Padding(10) };
            layout.ColumnStyles.Add(new WinForms.ColumnStyle(WinForms.SizeType.Percent, 100));
            WinForms.Control[] rows = { allRadio, selectedRadio, search, list, listButtons, overrideBox, buttons };
            foreach (WinForms.Control control in rows)
            {
                layout.RowStyles.Add(control == list
                    ? new WinForms.RowStyle(WinForms.SizeType.Percent, 100)
                    : new WinForms.RowStyle(WinForms.SizeType.AutoSize));
                layout.Controls.Add(control);
            }
            form.Controls.Add(layout);
            form.AcceptButton = build;
            form.CancelButton = cancel;

            bool filling = false;
            void UpdateBuildButton()
            {
                build.Text = allRadio.Checked ? $"Build All ({names.Count})" : $"Build Selected ({chosen.Count})";
                build.Enabled = allRadio.Checked || chosen.Count > 0;
            }
            void FillList()
            {
                filling = true;
                list.BeginUpdate();
                list.Items.Clear();
                string[] words = search.Text.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries);
                foreach (string name in names.Where(name => words.All(word => name.ToLowerInvariant().Contains(word))))
                {
                    list.Items.Add(new DdmListItem(name, alreadyBuilt.Contains(name)), chosen.Contains(name));
                }
                list.EndUpdate();
                filling = false;
            }
            void CheckShown(bool check)
            {
                for (int index = 0; index < list.Items.Count; index++)
                {
                    list.SetItemChecked(index, check);
                }
            }

            list.ItemCheck += (_, e) =>
            {
                if (filling)
                {
                    return;
                }
                string name = ((DdmListItem)list.Items[e.Index]).Name;
                if (e.NewValue == WinForms.CheckState.Checked)
                {
                    chosen.Add(name);
                }
                else
                {
                    chosen.Remove(name);
                }
                // Picking schedules means building the picked ones.
                selectedRadio.Checked = true;
                // ItemCheck comes before the change; count it once the change is made.
                form.BeginInvoke(new Action(UpdateBuildButton));
            };
            search.TextChanged += (_, _) => FillList();
            allRadio.CheckedChanged += (_, _) => UpdateBuildButton();
            selectAll.Click += (_, _) => CheckShown(true);
            clear.Click += (_, _) => CheckShown(false);
            FillList();
            UpdateBuildButton();

            if (form.ShowDialog(new DdmOwner(owner)) != WinForms.DialogResult.OK)
            {
                return null;
            }
            return new DdmChoice(allRadio.Checked ? new HashSet<string>(names) : chosen, overrideBox.Checked);
        }

        private static IEnumerable<string> DdmRevitNames(string name)
        {
            yield return DdmModelPrefix + name;
            yield return name + DdmWorkingSuffix;
            yield return name;
        }

        private static void DdmBuildSchedule(
            Document doc, DdmTracker tracker, DdmNamePrompt namePrompt, string role, string viewName, ElementId categoryId, DdmSchedule spec, bool hideHiddenColumns,
            bool overrideExisting, List<string> created, List<string> updated, List<string> renamed, List<string> skipped, List<string> problems)
        {
            string key = DdmTracker.Key(spec, role);
            ViewSchedule? named = new FilteredElementCollector(doc)
                .OfClass(typeof(ViewSchedule))
                .Cast<ViewSchedule>()
                .FirstOrDefault(view => !view.IsTemplate && view.Name == viewName);
            // The recorded schedule, whatever it's called now; otherwise take over the one with
            // this name, unless it's recorded as another database schedule's.
            ViewSchedule? existing = tracker.Find(key);
            if (existing == null && named != null && !tracker.IsAnothersSchedule(named, key))
            {
                existing = named;
            }
            if (existing != null && !overrideExisting)
            {
                skipped.Add(existing.Name);
                return;
            }

            string finalName = viewName;
            if (existing != null && existing.Name != viewName)
            {
                switch (namePrompt.Ask(existing.Name, viewName))
                {
                    case DdmNameChoice.LeaveUnchanged:
                        skipped.Add(existing.Name);
                        return;
                    case DdmNameChoice.KeepRevitName:
                        finalName = existing.Name;
                        break;
                    case DdmNameChoice.CreateNew:
                        // The old schedule stays in the project, no longer tracked.
                        existing = null;
                        break;
                }
            }
            if (finalName == viewName && named != null && (existing == null || !named.Id.Equals(existing.Id)))
            {
                problems.Add($"{viewName}: another Revit schedule already has this name; left unchanged.");
                return;
            }
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
                    string oldName = schedule.Name;
                    if (oldName != finalName)
                    {
                        schedule.Name = finalName;
                    }

                    // A template that controls fields or filters would block the rebuild; reapplied below.
                    schedule.ViewTemplateId = ElementId.InvalidElementId;
                    ScheduleDefinition definition = schedule.Definition;
                    definition.IsItemized = spec.Itemize;
                    definition.ClearFilters();
                    definition.ClearFields();
                    IList<SchedulableField> schedulable = definition.GetSchedulableFields();

                    var visible = new List<string>();
                    ScheduleField? filterField = null;
                    foreach (DdmColumn column in spec.Columns)
                    {
                        ScheduleField? field;
                        if (column.Parts.Length > 0)
                        {
                            field = DdmAddCombinedField(doc, definition, schedulable, column, viewName, problems);
                            if (field == null)
                            {
                                continue;
                            }
                        }
                        else
                        {
                            SchedulableField? candidate = DdmFindField(doc, schedulable, column.Parameter);
                            if (candidate == null)
                            {
                                problems.Add($"{viewName}: no schedulable parameter '{column.Parameter}'; column left out.");
                                continue;
                            }
                            field = definition.AddField(candidate);
                        }
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
                        definition.AddFilter(new ScheduleFilter(filterField.FieldId, ScheduleFilterType.Equal, spec.FilterValue));
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

                    if (spec.ViewTemplate.Length > 0)
                    {
                        ViewSchedule? template = new FilteredElementCollector(doc)
                            .OfClass(typeof(ViewSchedule))
                            .Cast<ViewSchedule>()
                            .FirstOrDefault(view => view.IsTemplate && view.Name == spec.ViewTemplate);
                        if (template == null)
                        {
                            problems.Add($"{viewName}: no schedule view template named '{spec.ViewTemplate}'; none applied.");
                        }
                        else
                        {
                            schedule.ViewTemplateId = template.Id;
                        }
                    }

                    tracker.Record(key, schedule);
                    tx.Commit();
                    (existing == null ? created : updated).Add(finalName);
                    if (existing != null && oldName != finalName)
                    {
                        renamed.Add($"{oldName} -> {finalName}");
                    }
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

        /// <summary>
        /// Add a combined parameter column: one cell joining its parts' values, each with its
        /// prefix and suffix, and its separator before the next part. Null, with a problem noted,
        /// when a part can't be scheduled here or Revit refuses the parts.
        /// </summary>
        private static ScheduleField? DdmAddCombinedField(
            Document doc, ScheduleDefinition definition, IList<SchedulableField> schedulable, DdmColumn column,
            string viewName, List<string> problems)
        {
            var data = new List<TableCellCombinedParameterData>();
            foreach (DdmPart part in column.Parts)
            {
                SchedulableField? candidate = DdmFindField(doc, schedulable, part.Parameter);
                if (candidate == null)
                {
                    problems.Add($"{viewName}: no schedulable parameter '{part.Parameter}' for combined column '{column.Parameter}'; column left out.");
                    return null;
                }
                TableCellCombinedParameterData item = TableCellCombinedParameterData.Create();
                item.ParamId = candidate.ParameterId;
                item.Prefix = part.Prefix;
                item.Suffix = part.Suffix;
                item.Separator = part.Separator;
                data.Add(item);
            }
            if (!definition.IsValidCombinedParameters(data))
            {
                problems.Add($"{viewName}: Revit won't combine the parts of '{column.Parameter}'; column left out.");
                return null;
            }
            return definition.InsertCombinedParameterField(data, column.Parameter, definition.GetFieldCount());
        }

        private static SchedulableField? DdmFindField(Document doc, IList<SchedulableField> fields, string parameter)
        {
            // Prefer the instance parameter when a name is schedulable more than one way.
            return fields
                .Where(field => field.GetName(doc) == parameter)
                .OrderBy(field => field.FieldType == ScheduleFieldType.Instance ? 0 : 1)
                .FirstOrDefault();
        }

        private enum DdmNameChoice
        {
            UseDatabaseName,
            KeepRevitName,
            LeaveUnchanged,
            CreateNew,
        }

        /// <summary>Asks what to do about a schedule whose name differs from the database's.</summary>
        private sealed class DdmNamePrompt
        {
            private DdmNameChoice? _forTheRest;

            public DdmNameChoice Ask(string revitName, string databaseName)
            {
                if (_forTheRest != null)
                {
                    return _forTheRest.Value;
                }
                var dialog = new TaskDialog(DdmTitle)
                {
                    MainInstruction = "Schedule Name Has Changed",
                    MainContent = $"Revit Name: {revitName}\\nDatabase Name: {databaseName}",
                    VerificationText = "Do the Same for the Rest",
                    CommonButtons = TaskDialogCommonButtons.Cancel,
                };
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Use Database Name", "Rename the Revit schedule and update it.");
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Keep Revit Name", "Update the Revit schedule and leave its name.");
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink3, "Leave Unchanged", "Don't change this Revit schedule.");
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink4, "Create New Schedule", "Build a new schedule with the database name. The old one stays, no longer tracked.");
                TaskDialogResult result = dialog.Show();
                DdmNameChoice choice = result switch
                {
                    TaskDialogResult.CommandLink1 => DdmNameChoice.UseDatabaseName,
                    TaskDialogResult.CommandLink2 => DdmNameChoice.KeepRevitName,
                    TaskDialogResult.CommandLink4 => DdmNameChoice.CreateNew,
                    // Cancel changes nothing.
                    _ => DdmNameChoice.LeaveUnchanged,
                };
                if (result != TaskDialogResult.Cancel && dialog.WasVerificationChecked())
                {
                    _forTheRest = choice;
                }
                return choice;
            }
        }

        /// <summary>
        /// The project's record of which Revit schedule is which: "database GUID|role" to the
        /// Revit schedule's UniqueId, in Extensible Storage on one DataStorage element.
        /// </summary>
        private sealed class DdmTracker
        {
            private const string FieldName = "ScheduleIds";
            private static readonly Guid SchemaId = new Guid("/*TRACKING_SCHEMA*/");

            private readonly Document _doc;
            private readonly Dictionary<string, string> _ids = new Dictionary<string, string>();
            private readonly HashSet<string> _databaseGuids = new HashSet<string>(DdmSchedules.Select(spec => spec.Guid));
            private DataStorage? _storage;

            public DdmTracker(Document doc)
            {
                _doc = doc;
                Schema? schema = Schema.Lookup(SchemaId);
                if (schema == null)
                {
                    return;
                }
                _storage = new FilteredElementCollector(doc)
                    .OfClass(typeof(DataStorage))
                    .Cast<DataStorage>()
                    .FirstOrDefault(element => element.GetEntity(schema).IsValid());
                if (_storage != null)
                {
                    foreach (KeyValuePair<string, string> pair in _storage.GetEntity(schema).Get<IDictionary<string, string>>(FieldName))
                    {
                        _ids[pair.Key] = pair.Value;
                    }
                }
            }

            public static string Key(DdmSchedule spec, string role) => spec.Guid + "|" + role;

            /// <summary>The UniqueIds of every Revit schedule in the record.</summary>
            public HashSet<string> RecordedIds() => new HashSet<string>(_ids.Values);

            /// <summary>The recorded Revit schedule, or null if none or it has been deleted.</summary>
            public ViewSchedule? Find(string key)
            {
                return _ids.TryGetValue(key, out string? id) ? _doc.GetElement(id) as ViewSchedule : null;
            }

            public bool HasAny(DdmSchedule spec)
            {
                return new[] { DdmModelRole, DdmWorkingRole, DdmFinishedRole }.Any(role => Find(Key(spec, role)) != null);
            }

            /// <summary>
            /// Whether the record has this Revit schedule under another key of a schedule still in
            /// the database. Keys of schedules no longer in the database don't count: re-importing
            /// the workbook gives its schedules new GUIDs, and they take over by name.
            /// </summary>
            public bool IsAnothersSchedule(ViewSchedule schedule, string key)
            {
                return _ids.Any(pair => pair.Key != key
                    && pair.Value == schedule.UniqueId
                    && _databaseGuids.Contains(pair.Key.Split('|')[0]));
            }

            /// <summary>Record a Revit schedule; needs an open transaction.</summary>
            public void Record(string key, ViewSchedule schedule)
            {
                _ids[key] = schedule.UniqueId;
                Schema schema = Schema.Lookup(SchemaId) ?? BuildSchema();
                // Not valid if the transaction that created it was rolled back.
                if (_storage == null || !_storage.IsValidObject)
                {
                    _storage = DataStorage.Create(_doc);
                }
                var entity = new Entity(schema);
                entity.Set<IDictionary<string, string>>(FieldName, _ids);
                _storage.SetEntity(entity);
            }

            private static Schema BuildSchema()
            {
                var builder = new SchemaBuilder(SchemaId);
                builder.SetSchemaName("DdmScheduleTracking");
                builder.SetReadAccessLevel(AccessLevel.Public);
                builder.SetWriteAccessLevel(AccessLevel.Public);
                builder.AddMapField(FieldName, typeof(string), typeof(string));
                return builder.Finish();
            }
        }

        private sealed class DdmChoice
        {
            public DdmChoice(HashSet<string> names, bool overrideExisting)
            {
                Names = names;
                OverrideExisting = overrideExisting;
            }

            public HashSet<string> Names { get; }
            public bool OverrideExisting { get; }
        }

        private sealed class DdmListItem
        {
            public DdmListItem(string name, bool inProject)
            {
                Name = name;
                InProject = inProject;
            }

            public string Name { get; }
            public bool InProject { get; }

            public override string ToString() => InProject ? Name + "   \\u2713" : Name;
        }

        // Revit's main window, so the dialog opens over it.
        private sealed class DdmOwner : WinForms.IWin32Window
        {
            public DdmOwner(IntPtr handle)
            {
                Handle = handle;
            }

            public IntPtr Handle { get; }
        }

        private sealed class DdmColumn
        {
            public DdmColumn(string parameter, string header, double widthFeet, bool hidden, DdmPart[]? parts = null)
            {
                Parameter = parameter;
                Header = header;
                WidthFeet = widthFeet;
                Hidden = hidden;
                Parts = parts ?? Array.Empty<DdmPart>();
            }

            // For a combined parameter, its name; otherwise the parameter scheduled.
            public string Parameter { get; }
            public string Header { get; }
            public double WidthFeet { get; }
            public bool Hidden { get; }
            // A combined parameter's parts, in order; empty for a parameter.
            public DdmPart[] Parts { get; }
        }

        private sealed class DdmPart
        {
            public DdmPart(string parameter, string prefix, string suffix, string separator)
            {
                Parameter = parameter;
                Prefix = prefix;
                Suffix = suffix;
                Separator = separator;
            }

            public string Parameter { get; }
            public string Prefix { get; }
            public string Suffix { get; }
            public string Separator { get; }
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
            public DdmSchedule(
                string name, string guid, string filterValue, bool itemize, string viewTemplate,
                DdmColumn[] columns, DdmHeaderGroup[] headerGroups)
            {
                Name = name;
                Guid = guid;
                FilterValue = filterValue;
                Itemize = itemize;
                ViewTemplate = viewTemplate;
                Columns = columns;
                HeaderGroups = headerGroups;
            }

            public string Name { get; }
            public string Guid { get; }
            public string FilterValue { get; }
            public bool Itemize { get; }
            public string ViewTemplate { get; }
            public DdmColumn[] Columns { get; }
            public DdmHeaderGroup[] HeaderGroups { get; }
        }
    }
}
"""
