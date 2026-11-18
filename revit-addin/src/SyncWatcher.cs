using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Events;
using DesignDataManager.Schedules;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace DesignDataManager.Revit
{
    /// <summary>
    /// Brings a save in the Design Data Manager into the open project. The app's Save rewrites the
    /// schedules file; this notices, and on Revit's own thread (an external event) sorts the
    /// project's schedules against their last sync and asks: Apply, Review or Later. Nothing in the
    /// model changes without a click. Later asks again when a project is next opened or activated.
    /// </summary>
    internal sealed class SyncWatcher : IExternalEventHandler, IDisposable
    {
        private const string Title = "Design Data Sync";
        // OneDrive and editors write a file in bursts; wait for the last write.
        private const int SettleMilliseconds = 1500;

        private readonly ExternalEvent _event;
        private FileSystemWatcher? _dataWatcher;
        private FileSystemWatcher? _settingsWatcher;
        private System.Threading.Timer? _settle;
        private string? _watchedPath;
        // A save hasn't been dealt with yet (not checked, or the user chose Later).
        private volatile bool _pending;

        public SyncWatcher()
        {
            _event = ExternalEvent.Create(this);
        }

        public void Start(UIControlledApplication application)
        {
            Retarget();
            // The app records where it saves in settings.json; follow it if that changes.
            string settingsFolder = Path.GetDirectoryName(AddinSettings.SettingsPath)!;
            if (Directory.Exists(settingsFolder))
            {
                _settingsWatcher = new FileSystemWatcher(settingsFolder, Path.GetFileName(AddinSettings.SettingsPath))
                {
                    NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.FileName,
                    EnableRaisingEvents = true,
                };
                _settingsWatcher.Changed += (_, _) => Retarget();
                _settingsWatcher.Created += (_, _) => Retarget();
            }
            application.ControlledApplication.DocumentOpened += (_, _) =>
            {
                if (_pending)
                {
                    _event.Raise();
                }
            };
            application.ViewActivated += OnViewActivated;
        }

        private void OnViewActivated(object? sender, ViewActivatedEventArgs e)
        {
            if (_pending && e.PreviousActiveView?.Document?.PathName != e.CurrentActiveView?.Document?.PathName)
            {
                _event.Raise();
            }
        }

        private void Retarget()
        {
            string? path = AddinSettings.ScheduleDataPath();
            if (path == null || path == _watchedPath)
            {
                return;
            }
            string? folder = Path.GetDirectoryName(path);
            if (folder == null || !Directory.Exists(folder))
            {
                return;
            }
            _dataWatcher?.Dispose();
            _watchedPath = path;
            _dataWatcher = new FileSystemWatcher(folder, Path.GetFileName(path))
            {
                NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.FileName | NotifyFilters.Size,
                EnableRaisingEvents = true,
            };
            _dataWatcher.Changed += (_, _) => Saved();
            _dataWatcher.Created += (_, _) => Saved();
            _dataWatcher.Renamed += (_, _) => Saved();
        }

        private void Saved()
        {
            _pending = true;
            _settle?.Dispose();
            _settle = new System.Threading.Timer(_ => _event.Raise(), null, SettleMilliseconds, System.Threading.Timeout.Infinite);
        }

        public void Execute(UIApplication application)
        {
            Document? doc = application.ActiveUIDocument?.Document;
            if (!_pending || doc == null || doc.IsFamilyDocument || doc.IsReadOnly)
            {
                return;  // stays pending for the next project activated
            }
            string? path = AddinSettings.ScheduleDataPath();
            if (path == null)
            {
                _pending = false;
                return;
            }
            DdmScheduleData data;
            try
            {
                data = DdmScheduleData.Load(path);
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is InvalidDataException)
            {
                return;  // mid-write or unreadable; the next write raises again
            }

            var routine = new DdmScheduleRoutine(data.Schedules, data.Notes);
            DdmSavedCheck check;
            try
            {
                check = routine.CheckSaved(doc);
                if (check.AlreadyInRevit.Count > 0)
                {
                    routine.MarkSynced(doc, check.AlreadyInRevit);
                }
            }
            catch (Autodesk.Revit.Exceptions.ApplicationException ex)
            {
                // e.g. a workshared project where someone else has the sync record checked out.
                TaskDialog.Show(Title, "The database was saved, but this project's schedules couldn't be checked:\n" + ex.Message);
                _pending = false;
                return;
            }
            _pending = false;
            if (check.ToApply.Count == 0 && check.ChangedInBoth.Count == 0)
            {
                return;
            }

            var dialog = new TaskDialog(Title)
            {
                MainInstruction = check.ToApply.Count > 0
                    ? $"Database saved: {check.ToApply.Count} schedule(s) changed"
                    : "Database saved",
                MainContent = Describe(check),
                CommonButtons = check.ToApply.Count > 0 ? TaskDialogCommonButtons.None : TaskDialogCommonButtons.Ok,
            };
            if (check.ToApply.Count > 0)
            {
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Apply", "Update these schedules in this project now.");
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Review", "Choose which schedules to update.");
                dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink3, "Later", "Ask again when a project is next opened or switched to.");
            }
            TaskDialogResult result = dialog.Show();
            switch (result)
            {
                case TaskDialogResult.CommandLink1:
                    TaskDialog.Show(Title, routine.ApplySaved(doc, check.ToApply));
                    break;
                case TaskDialogResult.CommandLink2:
                    routine.CreateSchedules(doc, application.MainWindowHandle, check.ToApply.Select(spec => spec.Name));
                    break;
                case TaskDialogResult.CommandLink3:
                    _pending = true;
                    break;
            }
        }

        private static string Describe(DdmSavedCheck check)
        {
            var parts = new List<string>();
            if (check.ToApply.Count > 0)
            {
                parts.Add("Changed in the Design Data Manager:\n" + ShortList(check.ToApply));
            }
            if (check.ChangedInBoth.Count > 0)
            {
                parts.Add("Also changed in Revit since the last sync, so they're left as they are. Review them first: "
                    + "Design Data Manager on the Design Data tab.\n" + ShortList(check.ChangedInBoth));
            }
            return string.Join("\n\n", parts);
        }

        private static string ShortList(List<DdmSchedule> specs)
        {
            const int shown = 12;
            string list = string.Join("\n", specs.Take(shown).Select(spec => "  " + spec.Name));
            return specs.Count > shown ? list + $"\n  ...and {specs.Count - shown} more" : list;
        }

        public string GetName() => Title;

        public void Dispose()
        {
            _settle?.Dispose();
            _dataWatcher?.Dispose();
            _settingsWatcher?.Dispose();
        }
    }
}
