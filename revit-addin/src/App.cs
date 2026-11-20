using Autodesk.Revit.UI;
using System.Reflection;

namespace DesignDataManager.Revit
{
    /// <summary>
    /// The add-in: a Design Data tab on Revit's ribbon. Build Schedules builds the database's
    /// schedules in the open project; Design Data Manager opens the desktop app.
    /// </summary>
    public sealed class App : IExternalApplication
    {
        public const string TabName = "Design Data";

        // The Linker panel and its check on open: on for dev, off for releases (main) until it's tried
        // in Revit. The app's switch is FEATURES["linker"] in config/app_paths.py. (Not const: the
        // build treats the unreachable code a const would make as an error.)
        private static readonly bool LinkerEnabled = true;

        // Notices saves in the app and offers them to the open project.
        private SyncWatcher? _sync;
        // Offers to sync linked elements when a project opens.
        private LinkerWatcher? _linker;

        public Result OnStartup(UIControlledApplication application)
        {
            try
            {
                application.CreateRibbonTab(TabName);
            }
            catch (Autodesk.Revit.Exceptions.ArgumentException)
            {
                // The tab is already there.
            }
            RibbonPanel panel = application.CreateRibbonPanel(TabName, "Schedules");
            string assembly = Assembly.GetExecutingAssembly().Location;
            panel.AddItem(new PushButtonData(
                "DdmBuildSchedules", "Build\nSchedules", assembly, typeof(BuildSchedulesCommand).FullName)
            {
                Image = RibbonIcons.Schedule(16),
                LargeImage = RibbonIcons.Schedule(32),
                ToolTip = "Create or update this project's schedules from the Design Data Manager database.",
                LongDescription = "Each database schedule makes three Revit schedules: \"3D - name\" (all model "
                    + "categories), \"name - Working\" (every column) and \"name\" (hidden columns hidden). "
                    + "It reads the schedules file the Design Data Manager writes when you Save.",
            });
            panel.AddItem(new PushButtonData(
                "DdmOpenApp", "Design Data\nManager", assembly, typeof(OpenAppCommand).FullName)
            {
                Image = RibbonIcons.Database(16),
                LargeImage = RibbonIcons.Database(32),
                ToolTip = "Open the Design Data Manager on Review Revit Changes: the schedule changes made in this project since the last sync.",
            });
            _sync = new SyncWatcher();
            _sync.Start(application);
            if (LinkerEnabled)
            {
                AddLinker(application, assembly);
            }
            return Result.Succeeded;
        }

        private void AddLinker(UIControlledApplication application, string assembly)
        {
            // Linker ID: link each item's primary (the 2D detail item with the design data) to the
            // elements showing it elsewhere, which share its tag values.
            RibbonPanel linker = application.CreateRibbonPanel(TabName, "Linker");
            linker.AddItem(new PushButtonData(
                "DdmAssignLinkerIds", "Assign\nIDs", assembly, typeof(AssignLinkerIdsCommand).FullName)
            {
                Image = RibbonIcons.LinkerId(16),
                LargeImage = RibbonIcons.LinkerId(32),
                ToolTip = "Give each primary element without a Linker ID the next one for its type, e.g. AHU-0001.",
                LongDescription = "A primary is the 2D detail item that holds an item's design data. Its Linker ID "
                    + "never changes, so elements showing the same item elsewhere stay linked to it. Also finds "
                    + "primaries sharing an ID (usually a copy-paste) and offers to renumber the newer ones.",
            });
            linker.AddItem(new PushButtonData(
                "DdmLinkElements", "Link\nElements", assembly, typeof(LinkElementsCommand).FullName)
            {
                Image = RibbonIcons.Link(16),
                LargeImage = RibbonIcons.Link(32),
                ToolTip = "Pick a primary, then the elements showing the same item elsewhere; they get its Linker ID and tag values.",
                LongDescription = "Use it for a new or recreated element: a 3D model element or a tag-only copy on "
                    + "another diagram. You can also select the primary and the elements first.",
            });
            linker.AddItem(new PushButtonData(
                "DdmSyncLinked", "Sync Linked\nElements", assembly, typeof(SyncLinkedElementsCommand).FullName)
            {
                Image = RibbonIcons.SyncLinked(16),
                LargeImage = RibbonIcons.SyncLinked(32),
                ToolTip = "Copy each primary's tag values to the elements linked to it.",
                LongDescription = "The tag values are the parameters in sections marked Linker Tag Set in the "
                    + "Design Data Manager. Also lists linked elements whose primary can't be found.",
            });
            _linker = new LinkerWatcher();
            _linker.Start(application);
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            _sync?.Dispose();
            System.GC.KeepAlive(_linker);  // its external event lives as long as the add-in
            return Result.Succeeded;
        }
    }
}
