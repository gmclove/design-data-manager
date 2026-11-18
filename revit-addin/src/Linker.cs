using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Selection;
using DesignDataManager.Schedules;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace DesignDataManager.Revit
{
    /// <summary>
    /// The Linker ID in a project. Each item's primary (its main 2D detail item) holds the design
    /// data; its linked elements (the item on other diagrams, the 3D model element) share the
    /// primary's Linker ID and copy its tag values. The rules are in DdmLinkerPlan; this reads the
    /// elements and applies a plan. It only fills in parameters families already have.
    /// </summary>
    internal sealed class DdmLinker
    {
        public const string Title = "Linker ID";

        private readonly DdmLinkerData _data;
        private readonly Document _doc;
        // The elements read, by element ID value.
        private readonly Dictionary<long, FamilyInstance> _instances = new Dictionary<long, FamilyInstance>();

        public DdmLinker(Document doc, DdmLinkerData data)
        {
            _doc = doc;
            _data = data;
        }

        // Families that have the Linker ID parameter but aren't linker families in the database.
        public SortedSet<string> UnknownFamilies { get; } = new SortedSet<string>();

        /// <summary>Every element of a linker family, with its Linker ID and tag values.</summary>
        public List<DdmLinkerElement> Read()
        {
            _instances.Clear();
            UnknownFamilies.Clear();
            var checkedFamilies = new HashSet<string>();
            var elements = new List<DdmLinkerElement>();
            foreach (FamilyInstance instance in new FilteredElementCollector(_doc).OfClass(typeof(FamilyInstance)).Cast<FamilyInstance>())
            {
                string family = instance.Symbol?.FamilyName ?? "";
                if (!_data.Families.TryGetValue(family, out DdmLinkerFamily? info))
                {
                    if (checkedFamilies.Add(family) && Find(instance, _data.Parameter) != null)
                    {
                        UnknownFamilies.Add(family);
                    }
                    continue;
                }
                _instances[instance.Id.Value] = instance;
                var values = new Dictionary<string, string>();
                foreach (DdmLinkerParameter tag in info.TagParameters)
                {
                    Parameter? parameter = Find(instance, tag);
                    if (parameter != null && parameter.StorageType != StorageType.None)
                    {
                        values[tag.Name] = Comparable(parameter);
                    }
                }
                elements.Add(new DdmLinkerElement(instance.Id.Value, family, Find(instance, _data.Parameter)?.AsString() ?? "", values));
            }
            return elements;
        }

        public DdmLinkerPlan Plan(bool renumberDuplicates) => DdmLinkerPlan.Make(_data, Read(), renumberDuplicates);

        public DdmLinkerFamily? FamilyOf(Element element) =>
            element is FamilyInstance instance && _data.Families.TryGetValue(instance.Symbol?.FamilyName ?? "", out DdmLinkerFamily? info)
                ? info
                : null;

        public string LinkerIdOf(Element element) => Find(element, _data.Parameter)?.AsString()?.Trim() ?? "";

        /// <summary>
        /// Set the plan's Linker IDs and copy its values (``only``: just to these elements); inside an
        /// open transaction. Returns the parameters skipped (read-only, or a different kind of value).
        /// </summary>
        public int Apply(DdmLinkerPlan plan, ISet<long>? only = null)
        {
            int skipped = 0;
            foreach (KeyValuePair<long, string> assign in plan.Assign)
            {
                if (!SetLinkerId(_instances[assign.Key], assign.Value))
                {
                    skipped++;
                }
            }
            foreach (DdmLinkerCopy copy in plan.Copies)
            {
                if (only != null && !only.Contains(copy.Target))
                {
                    continue;
                }
                DdmLinkerParameter tag = _data.Families[_instances[copy.Target].Symbol.FamilyName].TagParameters.First(t => t.Name == copy.Parameter);
                Parameter? source = Find(_instances[copy.Source], tag);
                Parameter? target = Find(_instances[copy.Target], tag);
                if (source == null || target == null || !CopyValue(source, target))
                {
                    skipped++;
                }
            }
            return skipped;
        }

        public bool SetLinkerId(Element element, string linkerId)
        {
            Parameter? parameter = Find(element, _data.Parameter);
            return parameter != null && !parameter.IsReadOnly && parameter.StorageType == StorageType.String && parameter.Set(linkerId);
        }

        /// <summary>Its next Linker ID, counting every Linker ID in the project.</summary>
        public string NextId(string prefix) =>
            DdmLinkerPlan.NextId(prefix, Read().Select(element => element.LinkerId));

        private static Parameter? Find(Element element, DdmLinkerParameter wanted)
        {
            if (Guid.TryParse(wanted.Guid, out Guid guid))
            {
                Parameter? shared = element.get_Parameter(guid);
                if (shared != null)
                {
                    return shared;
                }
            }
            return element.LookupParameter(wanted.Name);
        }

        private static string Comparable(Parameter parameter) => parameter.StorageType switch
        {
            StorageType.String => parameter.AsString() ?? "",
            StorageType.Integer => parameter.AsInteger().ToString(CultureInfo.InvariantCulture),
            StorageType.Double => parameter.AsDouble().ToString("R", CultureInfo.InvariantCulture),
            StorageType.ElementId => parameter.AsElementId().Value.ToString(CultureInfo.InvariantCulture),
            _ => "",
        };

        private static bool CopyValue(Parameter source, Parameter target)
        {
            if (target.IsReadOnly || source.StorageType != target.StorageType)
            {
                return false;
            }
            return source.StorageType switch
            {
                StorageType.String => target.Set(source.AsString() ?? ""),
                StorageType.Integer => target.Set(source.AsInteger()),
                StorageType.Double => target.Set(source.AsDouble()),
                StorageType.ElementId => target.Set(source.AsElementId()),
                _ => false,
            };
        }

        /// <summary>Elements with problems: duplicate primaries (all but the oldest) and orphans.</summary>
        public static List<ElementId> ProblemElements(DdmLinkerPlan plan) =>
            plan.Duplicates.Values.SelectMany(ids => ids.Skip(1)).Concat(plan.Orphans)
                .Select(id => new ElementId(id)).ToList();

        /// <summary>The problems as lines for a dialog; empty when there are none.</summary>
        public List<string> Problems(DdmLinkerPlan plan)
        {
            var lines = new List<string>();
            if (plan.Duplicates.Count > 0)
            {
                lines.Add($"{plan.Duplicates.Count} Linker ID(s) are on more than one primary (often a copy-paste): "
                    + ShortList(plan.Duplicates.Keys) + ". Assign IDs offers to renumber the newer ones.");
            }
            if (plan.Orphans.Count > 0)
            {
                lines.Add($"{plan.Orphans.Count} linked element(s) have a blank Linker ID, or one no primary has. "
                    + "Use Link Elements to link them.");
            }
            if (UnknownFamilies.Count > 0)
            {
                lines.Add($"These families have the Linker ID parameter but aren't linker families in the database: "
                    + ShortList(UnknownFamilies) + ".");
            }
            return lines;
        }

        private static string ShortList(IEnumerable<string> names)
        {
            const int shown = 8;
            List<string> list = names.ToList();
            string text = string.Join(", ", list.Take(shown));
            return list.Count > shown ? text + $" and {list.Count - shown} more" : text;
        }

        /// <summary>Show a result, offering to select the problem elements when there are any.</summary>
        public static void Report(UIDocument uiDoc, string heading, IEnumerable<string> lines, DdmLinkerPlan problems)
        {
            List<ElementId> select = ProblemElements(problems);
            var dialog = new TaskDialog(Title)
            {
                MainInstruction = heading,
                MainContent = string.Join("\n\n", lines),
                CommonButtons = TaskDialogCommonButtons.Close,
            };
            if (select.Count > 0)
            {
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Select Problem Elements",
                    $"Select the {select.Count} duplicate or unlinked element(s).");
            }
            if (dialog.Show() == TaskDialogResult.CommandLink1)
            {
                uiDoc.Selection.SetElementIds(select);
            }
        }

        /// <summary>The database's linker data for a command; null (after saying why) if there is none.</summary>
        public static DdmLinkerData? LoadData(UIApplication application)
        {
            string? path = AddinSettings.FindScheduleData(application.MainWindowHandle);
            if (path == null)
            {
                return null;
            }
            DdmLinkerData data;
            try
            {
                data = DdmScheduleData.Load(path).Linker;
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is InvalidDataException)
            {
                TaskDialog.Show(Title, $"Couldn't read the schedules file:\n{path}\n\n{ex.Message}");
                return null;
            }
            if (data.IsEmpty)
            {
                TaskDialog.Show(Title, "The database has no linker families yet: no family has the "
                    + $"{data.Parameter.Name} parameter. Add it to the families and Save in the Design Data Manager.");
                return null;
            }
            return data;
        }

        /// <summary>The open project, or null (after saying why) when there isn't one to change.</summary>
        public static Document? ProjectOf(UIApplication application)
        {
            Document? doc = application.ActiveUIDocument?.Document;
            if (doc == null || doc.IsFamilyDocument)
            {
                TaskDialog.Show(Title, "Open a project first.");
                return null;
            }
            return doc;
        }
    }

    /// <summary>Assign IDs: give each primary without a Linker ID the next one for its prefix.</summary>
    [Transaction(TransactionMode.Manual)]
    public sealed class AssignLinkerIdsCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIApplication application = commandData.Application;
            Document? doc = DdmLinker.ProjectOf(application);
            DdmLinkerData? data = doc == null ? null : DdmLinker.LoadData(application);
            if (doc == null || data == null)
            {
                return Result.Cancelled;
            }
            var linker = new DdmLinker(doc, data);
            DdmLinkerPlan plan = linker.Plan(renumberDuplicates: false);
            bool renumber = false;
            if (plan.Duplicates.Count > 0)
            {
                var ask = new TaskDialog(DdmLinker.Title)
                {
                    MainInstruction = $"{plan.Duplicates.Count} Linker ID(s) are on more than one primary",
                    MainContent = "Usually a primary was copied and pasted. The oldest element keeps the ID, "
                        + "and its linked elements stay with it.",
                    CommonButtons = TaskDialogCommonButtons.Cancel,
                };
                ask.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Renumber the Newer Ones", "Give each copy its own new Linker ID.");
                ask.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Leave Them", "Only give IDs to primaries without one.");
                TaskDialogResult answer = ask.Show();
                if (answer == TaskDialogResult.Cancel)
                {
                    return Result.Cancelled;
                }
                renumber = answer == TaskDialogResult.CommandLink1;
                if (renumber)
                {
                    plan = linker.Plan(renumberDuplicates: true);
                }
            }
            if (plan.Assign.Count == 0)
            {
                DdmLinker.Report(application.ActiveUIDocument!, "Every primary already has its own Linker ID", linker.Problems(plan), plan);
                return Result.Succeeded;
            }
            int skipped;
            using (var transaction = new Transaction(doc, "Assign Linker IDs"))
            {
                transaction.Start();
                skipped = linker.Apply(plan.AssignOnly());
                transaction.Commit();
            }
            var lines = new List<string> { string.Join(", ", plan.Assign.Values.OrderBy(id => id, StringComparer.OrdinalIgnoreCase).Take(12))
                + (plan.Assign.Count > 12 ? " ..." : "") };
            if (skipped > 0)
            {
                lines.Add($"{skipped} couldn't be set: the Linker ID parameter is read-only or isn't Text in that family.");
            }
            DdmLinkerPlan after = linker.Plan(renumberDuplicates: false);
            lines.AddRange(linker.Problems(after));
            DdmLinker.Report(application.ActiveUIDocument!, $"Assigned {plan.Assign.Count - skipped} Linker ID(s)", lines, after);
            return Result.Succeeded;
        }
    }

    /// <summary>
    /// Link Elements: pick a primary, then the elements showing the same item elsewhere (a new or
    /// recreated 3D element, a copy on another diagram). They get its Linker ID and tag values.
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    public sealed class LinkElementsCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIApplication application = commandData.Application;
            Document? doc = DdmLinker.ProjectOf(application);
            DdmLinkerData? data = doc == null ? null : DdmLinker.LoadData(application);
            if (doc == null || data == null)
            {
                return Result.Cancelled;
            }
            UIDocument uiDoc = application.ActiveUIDocument!;
            var linker = new DdmLinker(doc, data);

            // A preselection: one primary and the elements to link.
            List<Element> picked = uiDoc.Selection.GetElementIds().Select(id => doc.GetElement(id)).Where(e => e != null).ToList();
            List<Element> primaries = picked.Where(e => linker.FamilyOf(e)?.IsPrimary == true).ToList();
            List<Element> targets = picked.Where(e => linker.FamilyOf(e) is { IsPrimary: false }).ToList();
            if (primaries.Count > 1)
            {
                TaskDialog.Show(DdmLinker.Title, "Select one primary (the element holding the design data) and the elements to link to it.");
                return Result.Cancelled;
            }
            try
            {
                if (primaries.Count == 0)
                {
                    Reference reference = uiDoc.Selection.PickObject(ObjectType.Element,
                        new LinkerPick(linker, primary: true), "Pick the primary: the 2D item that holds the design data");
                    primaries.Add(doc.GetElement(reference));
                }
                if (targets.Count == 0)
                {
                    IList<Reference> references = uiDoc.Selection.PickObjects(ObjectType.Element,
                        new LinkerPick(linker, primary: false), "Pick the elements to link to it, then Finish");
                    targets.AddRange(references.Select(reference => doc.GetElement(reference)));
                }
            }
            catch (Autodesk.Revit.Exceptions.OperationCanceledException)
            {
                return Result.Cancelled;
            }
            if (targets.Count == 0)
            {
                return Result.Cancelled;
            }

            Element primary = primaries[0];
            string linkerId = linker.LinkerIdOf(primary);
            int skipped;
            using (var transaction = new Transaction(doc, "Link Elements"))
            {
                transaction.Start();
                if (linkerId.Length == 0)
                {
                    linkerId = linker.NextId(linker.FamilyOf(primary)!.Prefix);
                    if (!linker.SetLinkerId(primary, linkerId))
                    {
                        transaction.RollBack();
                        TaskDialog.Show(DdmLinker.Title, "The primary's Linker ID parameter can't be set (read-only, or not Text in its family).");
                        return Result.Failed;
                    }
                }
                int notSet = targets.Count(target => !linker.SetLinkerId(target, linkerId));
                DdmLinkerPlan plan = linker.Plan(renumberDuplicates: false);
                skipped = notSet + linker.Apply(plan.CopiesOnly(),
                    new HashSet<long>(targets.Select(target => target.Id.Value)));
                transaction.Commit();
            }
            var lines = new List<string>();
            if (skipped > 0)
            {
                lines.Add($"{skipped} value(s) couldn't be set: read-only, or a different kind of value in that family.");
            }
            DdmLinkerPlan after = linker.Plan(renumberDuplicates: false);
            if (after.Duplicates.ContainsKey(linkerId))
            {
                lines.Add($"{linkerId} is on more than one primary, so its tag values weren't copied. Run Assign IDs to fix it.");
            }
            DdmLinker.Report(uiDoc, $"Linked {targets.Count} element(s) to {linkerId}", lines, new DdmLinkerPlan());
            return Result.Succeeded;
        }

        private sealed class LinkerPick : ISelectionFilter
        {
            private readonly DdmLinker _linker;
            private readonly bool _primary;

            public LinkerPick(DdmLinker linker, bool primary)
            {
                _linker = linker;
                _primary = primary;
            }

            public bool AllowElement(Element element) => _linker.FamilyOf(element) is DdmLinkerFamily info && info.IsPrimary == _primary;

            public bool AllowReference(Reference reference, XYZ position) => false;
        }
    }

    /// <summary>Sync Linked Elements: copy each primary's tag values to the elements linked to it.</summary>
    [Transaction(TransactionMode.Manual)]
    public sealed class SyncLinkedElementsCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIApplication application = commandData.Application;
            Document? doc = DdmLinker.ProjectOf(application);
            DdmLinkerData? data = doc == null ? null : DdmLinker.LoadData(application);
            if (doc == null || data == null)
            {
                return Result.Cancelled;
            }
            var linker = new DdmLinker(doc, data);
            DdmLinkerPlan plan = linker.Plan(renumberDuplicates: false);
            DdmLinker.Report(application.ActiveUIDocument!, Sync(doc, linker, plan, assign: false), linker.Problems(plan), plan);
            return Result.Succeeded;
        }

        /// <summary>Apply ``plan``'s copies (and its Linker IDs with ``assign``); the result as a heading.</summary>
        internal static string Sync(Document doc, DdmLinker linker, DdmLinkerPlan plan, bool assign)
        {
            DdmLinkerPlan apply = assign ? plan : plan.CopiesOnly();
            if (!apply.HasChanges)
            {
                return "Linked elements are up to date";
            }
            int skipped;
            using (var transaction = new Transaction(doc, "Sync Linked Elements"))
            {
                transaction.Start();
                skipped = linker.Apply(apply);
                transaction.Commit();
            }
            string heading = $"Updated {plan.LinkedToUpdate} linked element(s)";
            if (assign && plan.Assign.Count > 0)
            {
                heading += $" and assigned {plan.Assign.Count} Linker ID(s)";
            }
            return skipped > 0 ? heading + $"; {skipped} value(s) were read-only or a different kind of value" : heading;
        }
    }
}
