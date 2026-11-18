// The Linker ID's rules, without Revit, so they can be checked on their own
// (revit-addin/tests/ScheduleDataCheck). The add-in reads the elements and applies the plan.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;

namespace DesignDataManager.Schedules
{
    /// <summary>One element of a linker family, as read from the project.</summary>
    public sealed class DdmLinkerElement
    {
        public DdmLinkerElement(long id, string family, string linkerId, Dictionary<string, string> values)
        {
            Id = id;
            Family = family;
            LinkerId = (linkerId ?? "").Trim();
            Values = values;
        }

        // The Revit element ID: only to tell elements apart in one session, never stored.
        public long Id { get; }
        public string Family { get; }
        public string LinkerId { get; }
        // Its tag values by parameter name, as comparable text; a missing parameter isn't listed.
        public Dictionary<string, string> Values { get; }
    }

    /// <summary>Copy one tag value from a primary to a linked element.</summary>
    public sealed class DdmLinkerCopy
    {
        public DdmLinkerCopy(long source, long target, string parameter)
        {
            Source = source;
            Target = target;
            Parameter = parameter;
        }

        public long Source { get; }
        public long Target { get; }
        public string Parameter { get; }
    }

    /// <summary>
    /// What linking would change in a project, worked out without changing anything: new Linker IDs
    /// for primaries without one, tag values that linked elements should copy, and the problems.
    /// </summary>
    public sealed class DdmLinkerPlan
    {
        // Linker IDs to set: element ID -> new Linker ID.
        public Dictionary<long, string> Assign { get; } = new Dictionary<long, string>();
        public List<DdmLinkerCopy> Copies { get; } = new List<DdmLinkerCopy>();
        // Linker ID -> the primaries sharing it, oldest (lowest element ID) first.
        public Dictionary<string, long[]> Duplicates { get; } = new Dictionary<string, long[]>();
        // Linked elements whose Linker ID no primary has (blank included).
        public List<long> Orphans { get; } = new List<long>();

        // Linked elements that copy at least one value.
        public int LinkedToUpdate => Copies.Select(copy => copy.Target).Distinct().Count();
        public bool HasChanges => Assign.Count > 0 || Copies.Count > 0;

        /// <summary>
        /// The plan for ``elements``. Primaries without a Linker ID get the next one for their
        /// prefix. With ``renumberDuplicates``, primaries sharing an ID keep it on the oldest and the
        /// others get new ones; otherwise they're only listed in Duplicates (and copy nothing).
        /// </summary>
        public static DdmLinkerPlan Make(DdmLinkerData data, IEnumerable<DdmLinkerElement> elements, bool renumberDuplicates)
        {
            var plan = new DdmLinkerPlan();
            List<DdmLinkerElement> all = elements.Where(element => data.Families.ContainsKey(element.Family)).ToList();
            List<DdmLinkerElement> primaries = all.Where(element => data.Families[element.Family].IsPrimary)
                .OrderBy(element => element.Id).ToList();
            var used = new HashSet<string>(all.Select(element => element.LinkerId).Where(id => id.Length > 0),
                StringComparer.OrdinalIgnoreCase);

            // Each Linker ID's primary: the oldest with it.
            var primaryFor = new Dictionary<string, DdmLinkerElement>(StringComparer.OrdinalIgnoreCase);
            foreach (IGrouping<string, DdmLinkerElement> group in primaries.Where(element => element.LinkerId.Length > 0)
                         .GroupBy(element => element.LinkerId, StringComparer.OrdinalIgnoreCase))
            {
                DdmLinkerElement[] sharing = group.ToArray();
                primaryFor[group.Key] = sharing[0];
                if (sharing.Length < 2)
                {
                    continue;
                }
                if (renumberDuplicates)
                {
                    foreach (DdmLinkerElement extra in sharing.Skip(1))
                    {
                        plan.Assign[extra.Id] = Take(NextId(data.Families[extra.Family].Prefix, used), used);
                    }
                }
                else
                {
                    plan.Duplicates[group.Key] = sharing.Select(element => element.Id).ToArray();
                }
            }
            foreach (DdmLinkerElement primary in primaries.Where(element => element.LinkerId.Length == 0))
            {
                plan.Assign[primary.Id] = Take(NextId(data.Families[primary.Family].Prefix, used), used);
            }

            foreach (DdmLinkerElement linked in all.Where(element => !data.Families[element.Family].IsPrimary).OrderBy(element => element.Id))
            {
                if (linked.LinkerId.Length == 0 || !primaryFor.TryGetValue(linked.LinkerId, out DdmLinkerElement? primary))
                {
                    plan.Orphans.Add(linked.Id);
                    continue;
                }
                if (plan.Duplicates.ContainsKey(linked.LinkerId))
                {
                    continue;  // which primary it follows is the user's call
                }
                foreach (DdmLinkerParameter tag in data.Families[linked.Family].TagParameters)
                {
                    if (primary.Values.TryGetValue(tag.Name, out string? value)
                        && linked.Values.TryGetValue(tag.Name, out string? current)
                        && value != current)
                    {
                        plan.Copies.Add(new DdmLinkerCopy(primary.Id, linked.Id, tag.Name));
                    }
                }
            }
            return plan;
        }

        /// <summary>
        /// The next Linker ID for ``prefix``: one more than the highest ``prefix-N`` in ``used``,
        /// at least 4 digits (AHU-0001, ..., AHU-9999, AHU-10000).
        /// </summary>
        public static string NextId(string prefix, IEnumerable<string> used)
        {
            prefix = string.IsNullOrWhiteSpace(prefix) ? "ITEM" : prefix.Trim();
            var pattern = new Regex("^" + Regex.Escape(prefix) + @"-(\d+)$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            long highest = 0;
            foreach (string id in used)
            {
                Match match = pattern.Match(id ?? "");
                if (match.Success && long.TryParse(match.Groups[1].Value, NumberStyles.None, CultureInfo.InvariantCulture, out long number))
                {
                    highest = Math.Max(highest, number);
                }
            }
            return prefix + "-" + (highest + 1).ToString("0000", CultureInfo.InvariantCulture);
        }

        /// <summary>Just its Linker IDs.</summary>
        public DdmLinkerPlan AssignOnly()
        {
            var plan = new DdmLinkerPlan();
            foreach (KeyValuePair<long, string> assign in Assign)
            {
                plan.Assign[assign.Key] = assign.Value;
            }
            return plan;
        }

        /// <summary>Just its copies.</summary>
        public DdmLinkerPlan CopiesOnly()
        {
            var plan = new DdmLinkerPlan();
            plan.Copies.AddRange(Copies);
            return plan;
        }

        private static string Take(string id, HashSet<string> used)
        {
            used.Add(id);
            return id;
        }
    }
}
