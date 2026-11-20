// Shared by the Design Data Manager's Revit add-in and the schedule macro it generates; edit it
// here. The macro generator (revit_schedule_macro_generator.py) copies it into the macro.
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

namespace DesignDataManager.Schedules
{
    /// <summary>
    /// Builds the database's schedules in a Revit project, and exports the column widths of the
    /// project's own schedules. The add-in and the macro both run it.
    /// </summary>
    public sealed class DdmScheduleRoutine
    {
        private const string DdmTitle = "Schedule Generator";

        // A schedule lists the elements whose value of this parameter is the schedule's filter value.
        private const string DdmFilterParameter = "IPS_GROUP_Schedule_Name";
        private const string DdmModelPrefix = "3D - ";
        private const string DdmWorkingSuffix = " - Working";

        // The version of the snapshot SendSchedules writes (read by revit_sync.py).
        private const int DdmSyncVersion = 1;

        // The version of the files ExportScheduleWidths writes.
        private const int DdmWidthsVersion = 1;

        // Which of a database schedule's three Revit schedules this is, in the project's record.
        private const string DdmModelRole = "Model";
        private const string DdmWorkingRole = "Working";
        private const string DdmFinishedRole = "Finished";

        // The database's schedules, and the notes on database schedules left out.
        private readonly DdmSchedule[] DdmSchedules;
        private readonly string[] DdmGeneratorNotes;

        public DdmScheduleRoutine(DdmSchedule[] schedules, string[] notes)
        {
            DdmSchedules = schedules;
            DdmGeneratorNotes = notes;
        }

        /// <summary>
        /// Create or update three Revit schedules for each database schedule chosen: a
        /// multi-category model schedule ("3D - name"), a Detail Items working schedule showing
        /// every column ("name - Working") and a Detail Items schedule with hidden columns
        /// hidden ("name"). A dialog asks which schedules to build and whether to override
        /// schedules that already exist. The project records which Revit schedules are which, so
        /// a rename on either side finds the same schedules, and the macro asks what to do.
        /// </summary>
        public void CreateSchedules(Document? doc, IntPtr owner, IEnumerable<string>? preselected = null)
        {
            if (doc == null)
            {
                TaskDialog.Show(DdmTitle, "No active Revit document is open.");
                return;
            }

            var tracker = new DdmTracker(doc, DdmSchedules);
            DdmChoice? choice = DdmAskWhatToBuild(doc, tracker, owner, preselected);
            if (choice == null)
            {
                return;
            }
            TaskDialog.Show(DdmTitle, DdmBuild(doc, tracker, DdmSchedules.Where(spec => choice.Names.Contains(spec.Name)), choice.OverrideExisting));
        }

        /// <summary>
        /// Build or update the three Revit schedules of each of <paramref name="specs"/>; returns the
        /// summary to show. The finished schedule's spec is remembered as the last sync.
        /// </summary>
        private string DdmBuild(Document doc, DdmTracker tracker, IEnumerable<DdmSchedule> specs, bool overrideExisting)
        {
            var created = new List<string>();
            var updated = new List<string>();
            var renamed = new List<string>();
            var namePrompt = new DdmNamePrompt();
            var skipped = new List<string>();
            var problems = new List<string>(DdmGeneratorNotes);
            ElementId detailItems = new ElementId(BuiltInCategory.OST_DetailComponents);

            foreach (DdmSchedule spec in specs)
            {
                DdmBuildSchedule(doc, tracker, namePrompt, DdmModelRole, DdmModelPrefix + spec.Name, ElementId.InvalidElementId, spec, true, overrideExisting, created, updated, renamed, skipped, problems);
                DdmBuildSchedule(doc, tracker, namePrompt, DdmWorkingRole, spec.Name + DdmWorkingSuffix, detailItems, spec, false, overrideExisting, created, updated, renamed, skipped, problems);
                DdmBuildSchedule(doc, tracker, namePrompt, DdmFinishedRole, spec.Name, detailItems, spec, true, overrideExisting, created, updated, renamed, skipped, problems);
            }

            string message = $"Created {created.Count} schedule(s), updated {updated.Count}.";
            if (renamed.Count > 0)
            {
                message += $"\n\nRenamed {renamed.Count} to the database's name:\n" + DdmShortList(renamed);
            }
            if (skipped.Count > 0)
            {
                message += $"\n\nLeft {skipped.Count} existing schedule(s) as they were:\n"
                    + DdmShortList(skipped);
            }
            if (problems.Count > 0)
            {
                message += "\n\nProblems:\n" + string.Join("\n", problems);
            }
            return message;
        }

        // --- a save in the Design Data Manager --------------------------------------------

        /// <summary>
        /// Sort this project's database schedules after a save in the Design Data Manager, against
        /// the last sync. Changed in the database only: offered to apply. Changed in Revit too: left
        /// for Review Revit Changes. Already the same in Revit (accepted from Revit): the last sync
        /// just moves up. Schedules never built here, or unchanged, aren't listed.
        /// </summary>
        public DdmSavedCheck CheckSaved(Document doc)
        {
            var tracker = new DdmTracker(doc, DdmSchedules);
            var check = new DdmSavedCheck();
            foreach (DdmSchedule spec in DdmSchedules)
            {
                string? synced = tracker.Synced(spec.Guid);
                if (synced == null || synced == DdmScheduleData.SpecJson(spec))
                {
                    continue;
                }
                ViewSchedule? finished = DdmFindSchedule(doc, tracker, DdmTracker.Key(spec, DdmFinishedRole), spec.Name);
                if (finished == null)
                {
                    continue;
                }
                if (DdmMatches(doc, finished, spec))
                {
                    check.AlreadyInRevit.Add(spec);
                }
                else if (DdmMatches(doc, finished, DdmScheduleData.ParseSpec(synced)))
                {
                    check.ToApply.Add(spec);
                }
                else
                {
                    check.ChangedInBoth.Add(spec);
                }
            }
            return check;
        }

        /// <summary>Apply a save: rebuild <paramref name="specs"/>' schedules. Returns the summary.</summary>
        public string ApplySaved(Document doc, IEnumerable<DdmSchedule> specs)
        {
            return DdmBuild(doc, new DdmTracker(doc, DdmSchedules), specs, true);
        }

        /// <summary>Make <paramref name="specs"/> the last sync, without changing the schedules.</summary>
        public void MarkSynced(Document doc, IEnumerable<DdmSchedule> specs)
        {
            var tracker = new DdmTracker(doc, DdmSchedules);
            using var tx = new Transaction(doc, "Design Data Sync");
            tx.Start();
            foreach (DdmSchedule spec in specs)
            {
                tracker.RecordSynced(spec.Guid, DdmScheduleData.SpecJson(spec));
            }
            tx.Commit();
        }

        /// <summary>
        /// Whether a Revit schedule shows what <paramref name="spec"/> says: its name, Itemize, and
        /// each column's parameter, order, header, width and Hidden. Columns Revit can't schedule here,
        /// and the filter column the routine adds itself, don't count.
        /// </summary>
        private static bool DdmMatches(Document doc, ViewSchedule schedule, DdmSchedule spec)
        {
            ScheduleDefinition definition = schedule.Definition;
            if (schedule.Name != spec.Name || definition.IsItemized != spec.Itemize)
            {
                return false;
            }
            var wanted = spec.Columns.ToDictionary(column => column.Parameter);
            var revit = new List<ScheduleField>();
            foreach (ScheduleFieldId id in definition.GetFieldOrder())
            {
                ScheduleField field = definition.GetField(id);
                string name = DdmFieldName(doc, field);
                if (field.FieldType == ScheduleFieldType.Formula || field.FieldType == ScheduleFieldType.Percentage
                    || (name == DdmFilterParameter && !wanted.ContainsKey(name)))
                {
                    continue;
                }
                revit.Add(field);
            }
            IList<SchedulableField> schedulable = definition.GetSchedulableFields();
            List<DdmColumn> expected = spec.Columns
                .Where(column => column.Parts.Length > 0 || revit.Any(field => DdmFieldName(doc, field) == column.Parameter)
                    || DdmFindField(doc, schedulable, column.Parameter) != null)
                .ToList();
            if (expected.Count != revit.Count)
            {
                return false;
            }
            for (int index = 0; index < revit.Count; index++)
            {
                ScheduleField field = revit[index];
                DdmColumn column = expected[index];
                if (DdmFieldName(doc, field) != column.Parameter || field.ColumnHeading != column.Header
                    || Math.Abs(field.GridColumnWidth - column.WidthFeet) * 12 > 0.01
                    // The finished schedule hides the hidden columns.
                    || field.IsHidden != column.Hidden)
                {
                    return false;
                }
            }
            // Sorting, leaving out levels on columns Revit can't schedule here (the build does too).
            var names = new HashSet<string>(revit.Select(field => DdmFieldName(doc, field)));
            var wantedSorting = new DdmSorting(
                spec.Sorting.Levels.Where(level => names.Contains(level.Parameter)).ToArray(),
                spec.Sorting.ShowGrandTotal, spec.Sorting.ShowGrandTotalTitle, spec.Sorting.ShowGrandTotalCount,
                spec.Sorting.GrandTotalTitle);
            return JsonSerializer.Serialize(DdmScheduleData.SortingJson(wantedSorting))
                == JsonSerializer.Serialize(DdmScheduleData.SortingJson(DdmReadSorting(doc, definition)));
        }

        private static string DdmFieldName(Document doc, ScheduleField field)
        {
            // A combined column is named after its combined parameter, and a calculated one after itself;
            // Revit has no schedulable field for either (asking throws "not a schedulable field").
            return field.IsCombinedParameterField || field.IsCalculatedField
                || field.FieldType == ScheduleFieldType.CombinedParameter
                ? field.GetName()
                : field.GetSchedulableField().GetName(doc);
        }

        /// <summary>
        /// Write what this project's database schedules look like to <paramref name="syncPath"/>, so the
        /// Design Data Manager can show what changed in Revit. Changes nothing in Revit. With
        /// <paramref name="quiet"/>, it reports only problems (the add-in sends before opening the app).
        /// Returns whether the file was written.
        /// </summary>
        public bool SendSchedules(Document? doc, string syncPath, bool quiet = false, bool review = false)
        {
            if (doc == null)
            {
                TaskDialog.Show(DdmTitle, "No active Revit document is open.");
                return false;
            }
            if (syncPath.Length == 0)
            {
                TaskDialog.Show(DdmTitle, "This doesn't know where the database is. Save the database in the Design Data Manager first.");
                return false;
            }

            var tracker = new DdmTracker(doc, DdmSchedules);
            var found = new List<object>();
            var foundIds = new HashSet<ElementId>();
            var missing = new List<string>();
            foreach (DdmSchedule spec in DdmSchedules)
            {
                var roles = new[]
                {
                    (Role: DdmModelRole, Name: DdmModelPrefix + spec.Name),
                    (Role: DdmWorkingRole, Name: spec.Name + DdmWorkingSuffix),
                    (Role: DdmFinishedRole, Name: spec.Name),
                };
                foreach (var (role, name) in roles)
                {
                    ViewSchedule? schedule = DdmFindSchedule(doc, tracker, DdmTracker.Key(spec, role), name);
                    if (schedule == null)
                    {
                        missing.Add(name);
                        continue;
                    }
                    foundIds.Add(schedule.Id);
                    found.Add(DdmDescribeSchedule(doc, schedule, spec, role));
                }
            }
            List<string> unlinked = new FilteredElementCollector(doc)
                .OfClass(typeof(ViewSchedule))
                .Cast<ViewSchedule>()
                .Where(view => !view.IsTemplate && !view.IsTitleblockRevisionSchedule && !view.IsInternalKeynoteSchedule && !foundIds.Contains(view.Id))
                .Select(view => view.Name)
                .OrderBy(name => name)
                .ToList();

            try
            {
                string json = JsonSerializer.Serialize(new
                {
                    version = DdmSyncVersion,
                    project = doc.Title,
                    sent_at = DateTimeOffset.Now.ToString("yyyy-MM-dd HH:mm:ss"),
                    review,
                    schedules = found,
                    unlinked,
                    // What was last synced, per schedule GUID, for a three-way comparison.
                    synced = tracker.AllSynced().ToDictionary(
                        pair => pair.Key, pair => System.Text.Json.Nodes.JsonNode.Parse(pair.Value)),
                }, new JsonSerializerOptions { WriteIndented = true });
                // Through a temporary file, so the app never reads a half-written one.
                string temporary = syncPath + ".tmp";
                File.WriteAllText(temporary, json);
                File.Move(temporary, syncPath, true);
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
            {
                TaskDialog.Show(DdmTitle, $"Couldn't write {syncPath}:\n{ex.Message}");
                return false;
            }

            if (!quiet)
            {
                string message = $"Sent {found.Count} schedule(s) to:\n{syncPath}\n\nIn the Design Data Manager, click Review Revit Changes.";
                if (missing.Count > 0)
                {
                    message += $"\n\nNot in this project ({missing.Count}):\n" + DdmShortList(missing);
                }
                TaskDialog.Show(DdmTitle, message);
            }
            return true;
        }

        private static object DdmDescribeSchedule(Document doc, ViewSchedule schedule, DdmSchedule spec, string role)
        {
            ScheduleDefinition definition = schedule.Definition;
            var columns = new List<object>();
            var names = new HashSet<string>();
            foreach (ScheduleFieldId id in definition.GetFieldOrder())
            {
                ScheduleField field = definition.GetField(id);
                // Only parameters: calculated values and the like have no database column.
                if (field.FieldType == ScheduleFieldType.Formula || field.FieldType == ScheduleFieldType.Percentage)
                {
                    continue;
                }
                // DdmFieldName: a combined column (e.g. TAG) has no schedulable field to ask.
                string parameter = DdmFieldName(doc, field);
                names.Add(parameter);
                columns.Add(new
                {
                    parameter,
                    heading = field.ColumnHeading,
                    width_feet = field.GridColumnWidth,
                    hidden = field.IsHidden,
                });
            }
            IList<SchedulableField> schedulable = definition.GetSchedulableFields();
            List<string> unavailable = spec.Columns
                .Select(column => column.Parameter)
                .Where(parameter => !names.Contains(parameter) && DdmFindField(doc, schedulable, parameter) == null)
                .ToList();
            return new
            {
                guid = spec.Guid,
                role,
                name = schedule.Name,
                itemize = definition.IsItemized,
                sorting = DdmScheduleData.SortingJson(DdmReadSorting(doc, definition)),
                columns,
                unavailable,
            };
        }

        private static ViewSchedule? DdmScheduleNamed(Document doc, string name)
        {
            return new FilteredElementCollector(doc)
                .OfClass(typeof(ViewSchedule))
                .Cast<ViewSchedule>()
                .FirstOrDefault(view => !view.IsTemplate && view.Name == name);
        }

        /// <summary>
        /// The recorded Revit schedule, whatever it's called now; otherwise the one with this
        /// name, unless it's recorded as another database schedule's.
        /// </summary>
        private static ViewSchedule? DdmFindSchedule(Document doc, DdmTracker tracker, string key, string name)
        {
            ViewSchedule? recorded = tracker.Find(key);
            if (recorded != null)
            {
                return recorded;
            }
            ViewSchedule? named = DdmScheduleNamed(doc, name);
            return named != null && !tracker.IsAnothersSchedule(named, key) ? named : null;
        }

        /// <summary>
        /// Write the column widths of this project's schedules to a file, so the Design Data
        /// Manager can find each parameter's typical width. Changes nothing in Revit. Schedules this
        /// macro builds from the database are left out: they only repeat the database's widths.
        /// </summary>
        public void ExportScheduleWidths(Document? doc, string widthsFolder)
        {
            if (doc == null)
            {
                TaskDialog.Show(DdmTitle, "No active Revit document is open.");
                return;
            }
            if (widthsFolder.Length == 0)
            {
                TaskDialog.Show(DdmTitle, "This macro doesn't know where the database is. Save the database in the Design Data Manager and build the macro again.");
                return;
            }

            var tracker = new DdmTracker(doc, DdmSchedules);
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
            string target = Path.Combine(widthsFolder, fileName + ".widths.json");
            try
            {
                Directory.CreateDirectory(widthsFolder);
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
                TaskDialog.Show(DdmTitle, $"Couldn't write {target}:\n{ex.Message}");
                return;
            }

            TaskDialog.Show(DdmTitle,
                $"Exported the column widths of {schedules.Count} schedule(s), {columnCount} columns, to:\n{target}"
                + $"\n\nLeft out {skipped} schedule(s) the Design Data Manager builds."
                + "\n\nIn the Design Data Manager, click Column Widths From Revit on the Parameters tab.");
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
            string list = string.Join("\n", names.Take(shown));
            return names.Count > shown ? list + $"\n...and {names.Count - shown} more" : list;
        }

        /// <summary>
        /// Ask which schedules to build (all, or those checked in a searchable list) and whether
        /// to override Revit schedules that already exist. Returns null if the user cancels.
        /// </summary>
        private DdmChoice? DdmAskWhatToBuild(Document doc, DdmTracker tracker, IntPtr owner, IEnumerable<string>? preselected = null)
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
            var chosen = new HashSet<string>(preselected ?? Enumerable.Empty<string>());

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
                Text = "\u2713 = already in this project (its 3 Revit schedules, or some of them).",
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
            if (chosen.Count > 0)
            {
                selectedRadio.Checked = true;
            }
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
                    definition.ClearSortGroupFields();
                    definition.ClearFilters();
                    definition.ClearFields();
                    IList<SchedulableField> schedulable = definition.GetSchedulableFields();

                    var visible = new List<string>();
                    // Each column's field, for the sort levels.
                    var fieldIds = new Dictionary<string, ScheduleFieldId>();
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
                        if (column.Parts.Length == 0)
                        {
                            fieldIds[column.Parameter] = field.FieldId;
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
                    DdmApplySorting(definition, spec.Sorting, fieldIds, viewName, problems);

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
                    if (role == DdmFinishedRole)
                    {
                        tracker.RecordSynced(spec.Guid, DdmScheduleData.SpecJson(spec));
                    }
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
        /// Set the Sorting/Grouping tab (but Itemize): a level sorts by one of the columns just added;
        /// one whose column couldn't be added is left out, with a problem noted.
        /// </summary>
        private static void DdmApplySorting(
            ScheduleDefinition definition, DdmSorting sorting, Dictionary<string, ScheduleFieldId> fieldIds,
            string viewName, List<string> problems)
        {
            definition.ClearSortGroupFields();
            foreach (DdmSortLevel level in sorting.Levels)
            {
                if (!fieldIds.TryGetValue(level.Parameter, out ScheduleFieldId? fieldId))
                {
                    problems.Add($"{viewName}: can't sort by '{level.Parameter}': it isn't a column here.");
                    continue;
                }
                var sort = new ScheduleSortGroupField(
                    fieldId, level.Descending ? ScheduleSortOrder.Descending : ScheduleSortOrder.Ascending)
                {
                    ShowHeader = level.ShowHeader,
                    ShowFooter = level.ShowFooter,
                    ShowBlankLine = level.ShowBlankLine,
                };
                if (level.ShowFooter)
                {
                    sort.ShowFooterTitle = level.ShowFooterTitle;
                    sort.ShowFooterCount = level.ShowFooterCount;
                }
                definition.AddSortGroupField(sort);
            }
            definition.ShowGrandTotal = sorting.ShowGrandTotal;
            if (sorting.ShowGrandTotal)
            {
                definition.ShowGrandTotalTitle = sorting.ShowGrandTotalTitle;
                definition.ShowGrandTotalCount = sorting.ShowGrandTotalCount;
                if (sorting.ShowGrandTotalTitle)
                {
                    definition.GrandTotalTitle = sorting.GrandTotalTitle;
                }
            }
        }

        /// <summary>A Revit schedule's Sorting/Grouping (but Itemize), as the database holds it.</summary>
        private static DdmSorting DdmReadSorting(Document doc, ScheduleDefinition definition)
        {
            var levels = new List<DdmSortLevel>();
            for (int index = 0; index < definition.GetSortGroupFieldCount(); index++)
            {
                ScheduleSortGroupField sort = definition.GetSortGroupField(index);
                ScheduleField field = definition.GetField(sort.FieldId);
                string name = field.FieldType == ScheduleFieldType.Formula || field.FieldType == ScheduleFieldType.Percentage
                    ? field.GetName()
                    : DdmFieldName(doc, field);
                levels.Add(new DdmSortLevel(
                    name, sort.SortOrder == ScheduleSortOrder.Descending, sort.ShowHeader, sort.ShowFooter,
                    sort.ShowFooterTitle, sort.ShowFooterCount, sort.ShowBlankLine));
            }
            return new DdmSorting(
                levels.ToArray(), definition.ShowGrandTotal, definition.ShowGrandTotalTitle,
                definition.ShowGrandTotalCount, definition.GrandTotalTitle ?? "");
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
                    MainContent = $"Revit Name: {revitName}\nDatabase Name: {databaseName}",
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
            private static readonly Guid SchemaId = new Guid("b7d4e2a6-5c1f-4f83-9a2e-6d0c8e3f1a57");

            // The last sync: schedule GUID to the spec (JSON) last built or accepted. Its own schema,
            // since a schema can't gain a field; it sits on the same DataStorage element.
            private const string SyncedFieldName = "Specs";
            private static readonly Guid SyncedSchemaId = new Guid("3c9a5e71-8d2f-4b6a-a1c4-7e0f2d9b8a63");

            private readonly Document _doc;
            private readonly Dictionary<string, string> _ids = new Dictionary<string, string>();
            private readonly Dictionary<string, string> _synced = new Dictionary<string, string>();
            private readonly HashSet<string> _databaseGuids;
            private DataStorage? _storage;

            public DdmTracker(Document doc, IEnumerable<DdmSchedule> schedules)
            {
                _doc = doc;
                _databaseGuids = new HashSet<string>(schedules.Select(spec => spec.Guid));
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
                    Schema? syncedSchema = Schema.Lookup(SyncedSchemaId);
                    Entity? synced = syncedSchema == null ? null : _storage.GetEntity(syncedSchema);
                    if (synced != null && synced.IsValid())
                    {
                        foreach (KeyValuePair<string, string> pair in synced.Get<IDictionary<string, string>>(SyncedFieldName))
                        {
                            _synced[pair.Key] = pair.Value;
                        }
                    }
                }
            }

            /// <summary>The spec last synced for a database schedule, or null.</summary>
            public string? Synced(string guid) => _synced.TryGetValue(guid, out string? spec) ? spec : null;

            public IReadOnlyDictionary<string, string> AllSynced() => _synced;

            /// <summary>Remember <paramref name="spec"/> as the last sync; needs an open transaction.</summary>
            public void RecordSynced(string guid, string spec)
            {
                _synced[guid] = spec;
                Schema schema = Schema.Lookup(SyncedSchemaId) ?? BuildSyncedSchema();
                if (_storage == null || !_storage.IsValidObject)
                {
                    _storage = DataStorage.Create(_doc);
                    // The schedule record lives on the same element.
                    var ids = new Entity(Schema.Lookup(SchemaId) ?? BuildSchema());
                    ids.Set<IDictionary<string, string>>(FieldName, _ids);
                    _storage.SetEntity(ids);
                }
                var entity = new Entity(schema);
                entity.Set<IDictionary<string, string>>(SyncedFieldName, _synced);
                _storage.SetEntity(entity);
            }

            private static Schema BuildSyncedSchema()
            {
                var builder = new SchemaBuilder(SyncedSchemaId);
                builder.SetSchemaName("DdmScheduleSynced");
                builder.SetReadAccessLevel(AccessLevel.Public);
                builder.SetWriteAccessLevel(AccessLevel.Public);
                builder.AddMapField(SyncedFieldName, typeof(string), typeof(string));
                return builder.Finish();
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

            public override string ToString() => InProject ? Name + "   \u2713" : Name;
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
    }

    /// <summary>What a save in the Design Data Manager means for this project's schedules.</summary>
    public sealed class DdmSavedCheck
    {
        // Changed in the database only since the last sync: apply them.
        public List<DdmSchedule> ToApply { get; } = new List<DdmSchedule>();
        // Changed in Revit too: review them in the Design Data Manager first.
        public List<DdmSchedule> ChangedInBoth { get; } = new List<DdmSchedule>();
        // Revit already shows the database's version (accepted from Revit): just mark them synced.
        public List<DdmSchedule> AlreadyInRevit { get; } = new List<DdmSchedule>();
    }
}
