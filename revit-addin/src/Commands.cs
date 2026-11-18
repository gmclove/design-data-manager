using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using DesignDataManager.Schedules;
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;

namespace DesignDataManager.Revit
{
    /// <summary>Build Schedules: create or update the database's schedules in the open project.</summary>
    [Transaction(TransactionMode.Manual)]
    public sealed class BuildSchedulesCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIApplication application = commandData.Application;
            string? path = AddinSettings.FindScheduleData(application.MainWindowHandle);
            if (path == null)
            {
                return Result.Cancelled;
            }
            DdmScheduleData data;
            try
            {
                data = DdmScheduleData.Load(path);
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is InvalidDataException)
            {
                TaskDialog.Show("Build Schedules", $"Couldn't read the schedules file:\n{path}\n\n{ex.Message}");
                return Result.Failed;
            }
            new DdmScheduleRoutine(data.Schedules, data.Notes)
                .CreateSchedules(application.ActiveUIDocument?.Document, application.MainWindowHandle);
            return Result.Succeeded;
        }
    }

    /// <summary>
    /// Design Data Manager: send this project's schedules to the app and open it on Review Revit
    /// Changes. If the app is already open, it notices the snapshot and opens the review itself.
    /// </summary>
    [Transaction(TransactionMode.ReadOnly)]
    public sealed class OpenAppCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIApplication application = commandData.Application;
            Document? doc = application.ActiveUIDocument?.Document;
            string? syncPath = AddinSettings.RevitSyncPath();
            if (doc != null && !doc.IsFamilyDocument && syncPath != null)
            {
                string? dataPath = AddinSettings.FindScheduleData(application.MainWindowHandle);
                if (dataPath != null)
                {
                    try
                    {
                        DdmScheduleData data = DdmScheduleData.Load(dataPath);
                        new DdmScheduleRoutine(data.Schedules, data.Notes).SendSchedules(doc, syncPath, quiet: true, review: true);
                    }
                    catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is InvalidDataException)
                    {
                        TaskDialog.Show("Design Data Manager", $"Couldn't read the schedules file, so nothing was sent for review:\n{ex.Message}");
                    }
                }
            }
            if (AddinSettings.AppIsRunning())
            {
                return Result.Succeeded;  // it picks up the snapshot within a couple of seconds
            }

            string[]? command = AddinSettings.AppCommand();
            if (command == null || command.Length == 0 || !File.Exists(command[0]))
            {
                TaskDialog.Show("Design Data Manager",
                    "Revit doesn't know where the Design Data Manager is yet. Open it once yourself; after that, this button opens it.");
                return Result.Cancelled;
            }
            var start = new ProcessStartInfo(command[0]) { UseShellExecute = false };
            foreach (string argument in command.Skip(1))
            {
                start.ArgumentList.Add(argument);
            }
            try
            {
                Process.Start(start);
            }
            catch (Win32Exception ex)
            {
                TaskDialog.Show("Design Data Manager", $"Couldn't start {command[0]}:\n{ex.Message}");
                return Result.Failed;
            }
            return Result.Succeeded;
        }
    }
}
