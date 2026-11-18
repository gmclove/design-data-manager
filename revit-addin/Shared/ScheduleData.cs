// Shared by the Design Data Manager's Revit add-in and the schedule macro it generates; edit it
// here. The macro generator (revit_schedule_macro_generator.py) copies it into the macro.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace DesignDataManager.Schedules
{
    public sealed class DdmColumn
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

    public sealed class DdmPart
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

    public sealed class DdmHeaderGroup
    {
        public DdmHeaderGroup(string caption, string[] parameters)
        {
            Caption = caption;
            Parameters = parameters;
        }

        public string Caption { get; }
        public string[] Parameters { get; }
    }

    /// <summary>One Sort by / Then by level: Revit's ScheduleSortGroupField.</summary>
    public sealed class DdmSortLevel
    {
        public DdmSortLevel(
            string parameter, bool descending, bool showHeader, bool showFooter, bool showFooterTitle,
            bool showFooterCount, bool showBlankLine)
        {
            Parameter = parameter;
            Descending = descending;
            ShowHeader = showHeader;
            ShowFooter = showFooter;
            // Without a footer, its Title and Count don't apply: kept at Revit's default, so two
            // levels that look the same in Revit compare the same (as sort_group_field does).
            ShowFooterTitle = !showFooter || showFooterTitle;
            ShowFooterCount = !showFooter || showFooterCount;
            ShowBlankLine = showBlankLine;
        }

        public string Parameter { get; }
        public bool Descending { get; }
        public bool ShowHeader { get; }
        public bool ShowFooter { get; }
        public bool ShowFooterTitle { get; }
        public bool ShowFooterCount { get; }
        public bool ShowBlankLine { get; }
    }

    /// <summary>Revit's Sorting/Grouping tab, but Itemize: the levels and the grand totals.</summary>
    public sealed class DdmSorting
    {
        public const string DefaultGrandTotalTitle = "Grand total";

        public DdmSorting(
            DdmSortLevel[] levels, bool showGrandTotal, bool showGrandTotalTitle, bool showGrandTotalCount,
            string grandTotalTitle)
        {
            Levels = levels;
            ShowGrandTotal = showGrandTotal;
            // Settings that don't apply stay at Revit's defaults, as in Schedule._set_sorting_values.
            ShowGrandTotalTitle = !showGrandTotal || showGrandTotalTitle;
            ShowGrandTotalCount = !showGrandTotal || showGrandTotalCount;
            GrandTotalTitle = ShowGrandTotal && ShowGrandTotalTitle && grandTotalTitle.Trim().Length > 0
                ? grandTotalTitle.Trim() : DefaultGrandTotalTitle;
        }

        // Not sorted, no grand totals: Revit's defaults.
        public static readonly DdmSorting None = new DdmSorting(Array.Empty<DdmSortLevel>(), false, true, true, DefaultGrandTotalTitle);

        public DdmSortLevel[] Levels { get; }
        public bool ShowGrandTotal { get; }
        public bool ShowGrandTotalTitle { get; }
        public bool ShowGrandTotalCount { get; }
        public string GrandTotalTitle { get; }

        public bool IsNone => Levels.Length == 0 && !ShowGrandTotal;
    }

    public sealed class DdmSchedule
    {
        public DdmSchedule(
            string name, string guid, string filterValue, bool itemize, string viewTemplate,
            DdmColumn[] columns, DdmHeaderGroup[] headerGroups, DdmSorting? sorting = null)
        {
            Name = name;
            Guid = guid;
            FilterValue = filterValue;
            Itemize = itemize;
            ViewTemplate = viewTemplate;
            Columns = columns;
            HeaderGroups = headerGroups;
            Sorting = sorting ?? DdmSorting.None;
        }

        public string Name { get; }
        public string Guid { get; }
        public string FilterValue { get; }
        public bool Itemize { get; }
        public string ViewTemplate { get; }
        public DdmColumn[] Columns { get; }
        public DdmHeaderGroup[] HeaderGroups { get; }
        public DdmSorting Sorting { get; }
    }

    /// <summary>A parameter by name and shared-parameter GUID (blank when the database has none).</summary>
    public sealed class DdmLinkerParameter
    {
        public DdmLinkerParameter(string name, string guid)
        {
            Name = name;
            Guid = guid;
        }

        public string Name { get; }
        public string Guid { get; }
    }

    /// <summary>How one family takes part in linking.</summary>
    public sealed class DdmLinkerFamily
    {
        public const string PrimaryRole = "primary";
        public const string LinkedRole = "linked";

        public DdmLinkerFamily(string role, string prefix, DdmLinkerParameter[] tagParameters)
        {
            Role = role;
            Prefix = prefix;
            TagParameters = tagParameters;
        }

        // "primary": holds the design data; "linked": a tag-only copy (another diagram, the 3D model).
        public string Role { get; }
        public bool IsPrimary => Role == PrimaryRole;
        // New Linker IDs on a primary are Prefix-0001, Prefix-0002, ...
        public string Prefix { get; }
        // The tag values a linked element copies from its primary.
        public DdmLinkerParameter[] TagParameters { get; }
    }

    /// <summary>
    /// The Linker ID: one primary element per item holds the design data, and the elements showing
    /// the same item elsewhere share its Linker ID and copy its tag values.
    /// </summary>
    public sealed class DdmLinkerData
    {
        public static readonly DdmLinkerData Empty = new DdmLinkerData(
            new DdmLinkerParameter("IPS_LINKER_ID", ""), new Dictionary<string, DdmLinkerFamily>());

        public DdmLinkerData(DdmLinkerParameter parameter, Dictionary<string, DdmLinkerFamily> families)
        {
            Parameter = parameter;
            Families = families;
        }

        public DdmLinkerParameter Parameter { get; }
        // By family name.
        public Dictionary<string, DdmLinkerFamily> Families { get; }
        public bool IsEmpty => Families.Count == 0;
    }

    /// <summary>
    /// The schedules file Save writes next to the database (<c>&lt;database&gt;.schedules.json</c>),
    /// which the add-in builds from. Its shape is <c>schedule_specs</c> in
    /// revit_schedule_macro_generator.py.
    /// </summary>
    public sealed class DdmScheduleData
    {
        // The file version this reader understands; Save writes the same number.
        public const int Version = 1;

        private DdmScheduleData(string source, string savedAt, DdmSchedule[] schedules, string[] notes, DdmLinkerData linker)
        {
            Source = source;
            SavedAt = savedAt;
            Schedules = schedules;
            Notes = notes;
            Linker = linker;
        }

        // The database file it was saved from, and when.
        public string Source { get; }
        public string SavedAt { get; }
        public DdmSchedule[] Schedules { get; }
        // Database schedules left out, and why.
        public string[] Notes { get; }
        // The Linker ID families; empty in a file saved before linking existed.
        public DdmLinkerData Linker { get; }

        /// <summary>Read the file's text; throws <see cref="InvalidDataException"/> if it isn't one.</summary>
        public static DdmScheduleData Parse(string json)
        {
            try
            {
                using JsonDocument document = JsonDocument.Parse(json);
                JsonElement root = document.RootElement;
                int version = root.GetProperty("version").GetInt32();
                if (version != Version)
                {
                    throw new InvalidDataException(
                        $"The schedules file is version {version}; this add-in reads version {Version}. Update the add-in or the Design Data Manager so they match.");
                }
                DdmSchedule[] schedules = root.GetProperty("schedules").EnumerateArray().Select(ReadSchedule).ToArray();
                string[] notes = root.GetProperty("notes").EnumerateArray().Select(note => note.GetString() ?? "").ToArray();
                DdmLinkerData linker = root.TryGetProperty("linker", out JsonElement linkerNode) && linkerNode.ValueKind == JsonValueKind.Object
                    ? ReadLinker(linkerNode)
                    : DdmLinkerData.Empty;
                return new DdmScheduleData(Text(root, "source"), Text(root, "saved_at"), schedules, notes, linker);
            }
            catch (Exception ex) when (ex is JsonException || ex is KeyNotFoundException || ex is InvalidOperationException)
            {
                throw new InvalidDataException("This isn't a Design Data Manager schedules file: " + ex.Message, ex);
            }
        }

        public static DdmScheduleData Load(string path) => Parse(File.ReadAllText(path));

        /// <summary>
        /// A schedule as JSON in schedule_specs' shape: what the project remembers as last synced,
        /// and what the three-way comparison in revit_sync.py reads back. The same spec always gives
        /// the same text, so two specs can be compared as text.
        /// </summary>
        public static string SpecJson(DdmSchedule spec)
        {
            object basics = SpecBasics(spec);
            if (spec.Sorting.IsNone)
            {
                // Without sorting, the same text as before sorting was added, so the last sync of
                // an unsorted schedule still matches.
                return JsonSerializer.Serialize(basics);
            }
            System.Text.Json.Nodes.JsonObject node = JsonSerializer.SerializeToNode(basics)!.AsObject();
            node["sorting"] = JsonSerializer.SerializeToNode(SortingJson(spec.Sorting));
            return node.ToJsonString();
        }

        /// <summary>Sorting in schedule_specs' shape (Schedule.sorting_dict in the database).</summary>
        public static object SortingJson(DdmSorting sorting) => new
        {
            sort_group_fields = sorting.Levels.Select(level => new
            {
                parameter = level.Parameter,
                descending = level.Descending,
                show_header = level.ShowHeader,
                show_footer = level.ShowFooter,
                show_footer_title = level.ShowFooterTitle,
                show_footer_count = level.ShowFooterCount,
                show_blank_line = level.ShowBlankLine,
            }),
            show_grand_total = sorting.ShowGrandTotal,
            show_grand_total_title = sorting.ShowGrandTotalTitle,
            show_grand_total_count = sorting.ShowGrandTotalCount,
            grand_total_title = sorting.GrandTotalTitle,
        };

        private static object SpecBasics(DdmSchedule spec) => new
        {
            name = spec.Name,
            guid = spec.Guid,
            filter_value = spec.FilterValue,
            itemize = spec.Itemize,
            view_template = spec.ViewTemplate,
            columns = spec.Columns.Select(column => new
            {
                parameter = column.Parameter,
                header = column.Header,
                width_feet = column.WidthFeet,
                hidden = column.Hidden,
                parts = column.Parts.Select(part => new
                {
                    parameter = part.Parameter,
                    prefix = part.Prefix,
                    suffix = part.Suffix,
                    separator = part.Separator,
                }),
            }),
            header_groups = spec.HeaderGroups.Select(group => new { caption = group.Caption, parameters = group.Parameters }),
        };

        /// <summary>A schedule from <see cref="SpecJson"/>'s text.</summary>
        public static DdmSchedule ParseSpec(string json)
        {
            using JsonDocument document = JsonDocument.Parse(json);
            return ReadSchedule(document.RootElement);
        }

        private static string Text(JsonElement element, string name) =>
            element.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";

        private static DdmLinkerData ReadLinker(JsonElement linker)
        {
            var families = new Dictionary<string, DdmLinkerFamily>();
            foreach (JsonProperty family in linker.GetProperty("families").EnumerateObject())
            {
                DdmLinkerParameter[] tags = family.Value.GetProperty("tag_parameters").EnumerateArray()
                    .Select(tag => new DdmLinkerParameter(Text(tag, "name"), Text(tag, "guid")))
                    .ToArray();
                families[family.Name] = new DdmLinkerFamily(Text(family.Value, "role"), Text(family.Value, "prefix"), tags);
            }
            return new DdmLinkerData(new DdmLinkerParameter(Text(linker, "parameter"), Text(linker, "guid")), families);
        }

        private static DdmSchedule ReadSchedule(JsonElement spec)
        {
            DdmColumn[] columns = spec.GetProperty("columns").EnumerateArray().Select(column => new DdmColumn(
                Text(column, "parameter"),
                Text(column, "header"),
                column.GetProperty("width_feet").GetDouble(),
                column.GetProperty("hidden").GetBoolean(),
                column.TryGetProperty("parts", out JsonElement parts)
                    ? parts.EnumerateArray().Select(part => new DdmPart(
                        Text(part, "parameter"), Text(part, "prefix"), Text(part, "suffix"), Text(part, "separator"))).ToArray()
                    : null)).ToArray();
            DdmHeaderGroup[] groups = spec.GetProperty("header_groups").EnumerateArray().Select(group => new DdmHeaderGroup(
                Text(group, "caption"),
                group.GetProperty("parameters").EnumerateArray().Select(name => name.GetString() ?? "").ToArray())).ToArray();
            return new DdmSchedule(
                Text(spec, "name"), Text(spec, "guid"), Text(spec, "filter_value"),
                spec.GetProperty("itemize").GetBoolean(), Text(spec, "view_template"), columns, groups,
                spec.TryGetProperty("sorting", out JsonElement sorting) && sorting.ValueKind == JsonValueKind.Object
                    ? ReadSorting(sorting) : null);
        }

        private static bool Flag(JsonElement element, string name, bool fallback) =>
            element.TryGetProperty(name, out JsonElement value) && (value.ValueKind == JsonValueKind.True || value.ValueKind == JsonValueKind.False)
                ? value.GetBoolean() : fallback;

        // Older files and unsorted schedules have no "sorting": not sorted.
        private static DdmSorting ReadSorting(JsonElement sorting)
        {
            DdmSortLevel[] levels = sorting.TryGetProperty("sort_group_fields", out JsonElement fields) && fields.ValueKind == JsonValueKind.Array
                ? fields.EnumerateArray().Select(level => new DdmSortLevel(
                    Text(level, "parameter"), Flag(level, "descending", false), Flag(level, "show_header", false),
                    Flag(level, "show_footer", false), Flag(level, "show_footer_title", true),
                    Flag(level, "show_footer_count", true), Flag(level, "show_blank_line", false))).ToArray()
                : Array.Empty<DdmSortLevel>();
            return new DdmSorting(
                levels, Flag(sorting, "show_grand_total", false), Flag(sorting, "show_grand_total_title", true),
                Flag(sorting, "show_grand_total_count", true), Text(sorting, "grand_total_title"));
        }
    }
}
