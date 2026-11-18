using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using WinForms = System.Windows.Forms;

namespace DesignDataManager.Revit
{
    /// <summary>
    /// The Design Data Manager's per-user settings file, %APPDATA%\DesignDataManager\settings.json,
    /// shared with the app. The app records there where it saved the schedules file
    /// (<c>schedule_data_path</c>) and how to start itself (<c>app_command</c>).
    /// </summary>
    internal static class AddinSettings
    {
        private const string ScheduleDataKey = "schedule_data_path";
        private const string DatabaseFolderKey = "database_folder";
        private const string AppCommandKey = "app_command";
        private const string DefaultScheduleDataName = "database.schedules.json";

        public static string SettingsPath => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "DesignDataManager", "settings.json");

        private static JsonObject Read()
        {
            try
            {
                return JsonNode.Parse(File.ReadAllText(SettingsPath)) as JsonObject ?? new JsonObject();
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is JsonException)
            {
                return new JsonObject();
            }
        }

        private static string? Text(JsonObject settings, string key)
        {
            try
            {
                string? value = settings[key]?.GetValue<string>();
                return string.IsNullOrWhiteSpace(value) ? null : value;
            }
            catch (InvalidOperationException)
            {
                return null;
            }
        }

        /// <summary>
        /// The schedules file to build from: the one the app saved last, else database.schedules.json in
        /// the database folder, else one the user picks (remembered). Null if the user cancels.
        /// </summary>
        public static string? FindScheduleData(IntPtr owner)
        {
            JsonObject settings = Read();
            var candidates = new List<string?> { Text(settings, ScheduleDataKey) };
            string? folder = Text(settings, DatabaseFolderKey);
            if (folder != null)
            {
                candidates.Add(Path.Combine(folder, DefaultScheduleDataName));
            }
            string? found = candidates.FirstOrDefault(path => path != null && File.Exists(path));
            if (found != null)
            {
                return found;
            }

            using var dialog = new WinForms.OpenFileDialog
            {
                Title = "Design Data Manager Schedules File",
                Filter = "Schedules file (*.schedules.json)|*.schedules.json|All files (*.*)|*.*",
                InitialDirectory = folder ?? "",
            };
            if (dialog.ShowDialog(new Owner(owner)) != WinForms.DialogResult.OK)
            {
                return null;
            }
            settings[ScheduleDataKey] = dialog.FileName;
            Write(settings);
            return dialog.FileName;
        }

        /// <summary>The schedules file the app saves, without asking; null if there isn't one yet.</summary>
        public static string? ScheduleDataPath()
        {
            JsonObject settings = Read();
            var candidates = new List<string?> { Text(settings, ScheduleDataKey) };
            string? folder = Text(settings, DatabaseFolderKey);
            if (folder != null)
            {
                candidates.Add(Path.Combine(folder, DefaultScheduleDataName));
            }
            return candidates.FirstOrDefault(path => path != null && File.Exists(path));
        }

        /// <summary>Where to send this project's schedules for the app's Review Revit Changes; null if unknown.</summary>
        public static string? RevitSyncPath()
        {
            JsonObject settings = Read();
            string? path = Text(settings, "revit_sync_path");
            if (path != null)
            {
                return path;
            }
            string? folder = Text(settings, DatabaseFolderKey);
            return folder == null ? null : Path.Combine(folder, "database.revit-sync.json");
        }

        /// <summary>Whether the app is running now (it records its process ID when it starts).</summary>
        public static bool AppIsRunning()
        {
            try
            {
                int? id = Read()["app_pid"]?.GetValue<int>();
                if (id == null)
                {
                    return false;
                }
                using System.Diagnostics.Process process = System.Diagnostics.Process.GetProcessById(id.Value);
                string name = process.ProcessName.ToLowerInvariant();
                return !process.HasExited && (name.StartsWith("python") || name.StartsWith("designdatamanager"));
            }
            catch (Exception ex) when (ex is ArgumentException || ex is InvalidOperationException || ex is FormatException)
            {
                return false;
            }
        }

        /// <summary>How to start the app, as the program and its arguments; null if it hasn't run yet.</summary>
        public static string[]? AppCommand()
        {
            try
            {
                return Read()[AppCommandKey]?.AsArray().Select(part => part?.GetValue<string>() ?? "").ToArray();
            }
            catch (InvalidOperationException)
            {
                return null;
            }
        }

        private static void Write(JsonObject settings)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
                File.WriteAllText(SettingsPath, settings.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
            {
                // Not remembered; the user is asked again next time.
            }
        }

        private sealed class Owner : WinForms.IWin32Window
        {
            public Owner(IntPtr handle)
            {
                Handle = handle;
            }

            public IntPtr Handle { get; }
        }
    }
}
