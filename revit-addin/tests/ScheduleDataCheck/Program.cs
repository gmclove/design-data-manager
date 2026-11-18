using DesignDataManager.Schedules;
using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;

// Prints the schedules file at args[0] as JSON in schedule_specs' shape, as the add-in read it.
// With args[1], a JSON list of elements ({"id", "family", "linker_id", "values"}), it also prints
// the Linker plan for them (DdmLinkerPlan, without Revit), with and without renumbering duplicates.
try
{
    DdmScheduleData data = DdmScheduleData.Load(args[0]);
    var read = new
    {
        source = data.Source,
        saved_at = data.SavedAt,
        notes = data.Notes,
        schedules = data.Schedules.Select(schedule => new
        {
            name = schedule.Name,
            guid = schedule.Guid,
            filter_value = schedule.FilterValue,
            itemize = schedule.Itemize,
            view_template = schedule.ViewTemplate,
            columns = schedule.Columns.Select(column => new
            {
                parameter = column.Parameter,
                header = column.Header,
                width_feet = column.WidthFeet.ToString("R", CultureInfo.InvariantCulture),
                hidden = column.Hidden,
                parts = column.Parts.Select(part => new
                {
                    parameter = part.Parameter,
                    prefix = part.Prefix,
                    suffix = part.Suffix,
                    separator = part.Separator,
                }),
            }),
            header_groups = schedule.HeaderGroups.Select(group => new { caption = group.Caption, parameters = group.Parameters }),
        }),
        // How a project remembers each schedule as last synced, read back as JSON.
        synced = data.Schedules.Select(schedule => System.Text.Json.Nodes.JsonNode.Parse(DdmScheduleData.SpecJson(schedule))),
        // And the text survives a round trip, so two specs can be compared as text.
        round_trip = data.Schedules.All(schedule =>
            DdmScheduleData.SpecJson(DdmScheduleData.ParseSpec(DdmScheduleData.SpecJson(schedule))) == DdmScheduleData.SpecJson(schedule)),
        linker = new
        {
            parameter = data.Linker.Parameter.Name,
            guid = data.Linker.Parameter.Guid,
            families = data.Linker.Families.ToDictionary(family => family.Key, family => new
            {
                role = family.Value.Role,
                prefix = family.Value.Prefix,
                tag_parameters = family.Value.TagParameters.Select(tag => new { name = tag.Name, guid = tag.Guid }),
            }),
        },
        linker_plans = args.Length > 1 ? LinkerPlans(data.Linker, args[1]) : null,
    };
    Console.OutputEncoding = System.Text.Encoding.UTF8;
    Console.WriteLine(JsonSerializer.Serialize(read));
    return 0;
}
catch (InvalidDataException ex)
{
    Console.WriteLine("INVALID: " + ex.Message);
    return 1;
}

static object LinkerPlans(DdmLinkerData linker, string path)
{
    using JsonDocument document = JsonDocument.Parse(File.ReadAllText(path));
    DdmLinkerElement[] elements = document.RootElement.EnumerateArray().Select(element => new DdmLinkerElement(
        element.GetProperty("id").GetInt64(),
        element.GetProperty("family").GetString() ?? "",
        element.GetProperty("linker_id").GetString() ?? "",
        element.GetProperty("values").EnumerateObject().ToDictionary(value => value.Name, value => value.Value.GetString() ?? ""))).ToArray();
    object Describe(DdmLinkerPlan plan) => new
    {
        assign = plan.Assign.ToDictionary(assign => assign.Key.ToString(CultureInfo.InvariantCulture), assign => assign.Value),
        copies = plan.Copies.Select(copy => new[] { copy.Source.ToString(CultureInfo.InvariantCulture), copy.Target.ToString(CultureInfo.InvariantCulture), copy.Parameter }),
        duplicates = plan.Duplicates.ToDictionary(duplicate => duplicate.Key, duplicate => duplicate.Value),
        orphans = plan.Orphans,
        linked_to_update = plan.LinkedToUpdate,
    };
    return new
    {
        keep = Describe(DdmLinkerPlan.Make(linker, elements, renumberDuplicates: false)),
        renumber = Describe(DdmLinkerPlan.Make(linker, elements, renumberDuplicates: true)),
        next_ids = new[]
        {
            DdmLinkerPlan.NextId("AHU", new[] { "AHU-0009", "ahu-0011", "AHU-X", "PUMP-0050" }),
            DdmLinkerPlan.NextId("PUMP", new[] { "PUMP-9999" }),
            DdmLinkerPlan.NextId("", Array.Empty<string>()),
        },
    };
}
