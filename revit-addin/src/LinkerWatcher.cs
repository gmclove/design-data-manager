using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using DesignDataManager.Schedules;
using System;
using System.Collections.Generic;
using System.IO;

namespace DesignDataManager.Revit
{
    /// <summary>
    /// When a project opens, checks its linked elements against their primaries and, if any are out
    /// of date or a primary has no Linker ID, asks: Sync Now or Later. Nothing changes without a
    /// click. Runs as an external event, after Revit has finished opening the project.
    /// </summary>
    internal sealed class LinkerWatcher : IExternalEventHandler
    {
        private readonly ExternalEvent _event;

        public LinkerWatcher()
        {
            _event = ExternalEvent.Create(this);
        }

        public void Start(UIControlledApplication application)
        {
            application.ControlledApplication.DocumentOpened += (_, args) =>
            {
                if (!args.Document.IsFamilyDocument && !args.Document.IsLinked)
                {
                    _event.Raise();
                }
            };
        }

        public void Execute(UIApplication application)
        {
            Document? doc = application.ActiveUIDocument?.Document;
            string? path = AddinSettings.ScheduleDataPath();
            if (doc == null || doc.IsFamilyDocument || doc.IsReadOnly || path == null)
            {
                return;
            }
            DdmLinkerData data;
            try
            {
                data = DdmScheduleData.Load(path).Linker;
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is InvalidDataException)
            {
                return;  // the buttons say why; opening a project shouldn't
            }
            if (data.IsEmpty)
            {
                return;
            }
            var linker = new DdmLinker(doc, data);
            DdmLinkerPlan plan = linker.Plan(renumberDuplicates: false);
            if (!plan.HasChanges)
            {
                return;
            }

            var parts = new List<string>();
            if (plan.LinkedToUpdate > 0)
            {
                parts.Add($"{plan.LinkedToUpdate} linked element(s) show tag values that differ from their primary.");
            }
            if (plan.Assign.Count > 0)
            {
                parts.Add($"{plan.Assign.Count} primary element(s) have no Linker ID yet.");
            }
            var dialog = new TaskDialog(DdmLinker.Title)
            {
                MainInstruction = "Linked elements are out of date",
                MainContent = string.Join("\n", parts),
            };
            dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Sync Now",
                "Copy the primaries' tag values to their linked elements and give primaries without one a Linker ID.");
            dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Later",
                "Leave them; Sync Linked Elements on the Design Data tab does it any time.");
            if (dialog.Show() != TaskDialogResult.CommandLink1)
            {
                return;
            }
            try
            {
                string heading = SyncLinkedElementsCommand.Sync(doc, linker, plan, assign: true);
                DdmLinker.Report(application.ActiveUIDocument!, heading, linker.Problems(plan), plan);
            }
            catch (Autodesk.Revit.Exceptions.ApplicationException ex)
            {
                // e.g. a workshared project where someone else has the elements checked out.
                TaskDialog.Show(DdmLinker.Title, "The linked elements couldn't be updated:\n" + ex.Message);
            }
        }

        public string GetName() => DdmLinker.Title;
    }
}
