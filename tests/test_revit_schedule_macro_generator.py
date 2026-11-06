import glob
import shutil
import subprocess
from pathlib import Path

import pytest

from config.app_paths import DEMO_DATA_PATH
from ddm_tables import catalog_from_tables, read_database_csv, write_database_csv
from revit_macro_module import MacroModule, build_module
from revit_parameter_manager import Catalog
from revit_schedule_macro_generator import (
    GENERATED_HEADER,
    MACRO_FILE_NAME,
    generate_schedule_macro_source,
    install_macro,
    revit_schedule_names,
    schedule_specs,
)

# The macro module's own startup class, minus the event wiring the generated file doesn't need.
MACRO_ENTRY_POINT = """
namespace GLoveMacros
{
    [Autodesk.Revit.Attributes.Transaction(Autodesk.Revit.Attributes.TransactionMode.Manual)]
    public sealed partial class ThisApplication : Autodesk.Revit.UI.Macros.ApplicationEntryPoint
    {
        protected override string PrimaryCookie => "ThisApplication";
    }
}
"""

MACRO_PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>{framework}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <PlatformTarget>x64</PlatformTarget>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <NoWarn>MSB3277</NoWarn>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="{revit}\\RevitAPI.dll"><Private>False</Private></Reference>
    <Reference Include="{revit}\\RevitAPIUI.dll"><Private>False</Private></Reference>
  </ItemGroup>
</Project>
"""


def newest_revit_install():
    """The newest installed Revit with a .NET (Core) API, 2025 or later, or ``None``."""
    installs = sorted(glob.glob(r"C:\Program Files\Autodesk\Revit 20[2-9][0-9]\RevitAPI.dll"))
    installs = [path for path in installs if int(Path(path).parent.name.split()[-1]) >= 2025]
    return Path(installs[-1]).parent if installs else None


def make_catalog():
    """One schedule, two families, with a header override, a width override and a hidden column."""
    catalog = Catalog()
    catalog.add_param("DDM_Airflow", "Text", header_text="Airflow", grid_column_width=18)
    catalog.add_param("DDM_Capacity", "Text", grid_column_width=15)
    catalog.add_param("DDM_Notes", "Text")
    catalog.add_family("AHU", ["DDM_Airflow", "DDM_Capacity", "DDM_Notes"], category="Mechanical Equipment")
    catalog.add_family("Door", ["DDM_Airflow"], category="Doors")
    schedule = catalog.add_schedule(
        "Mechanical Schedule", ["AHU", "Door"], field_names=["DDM_Airflow", "DDM_Capacity", "DDM_Notes"],
    )
    schedule.override_param("DDM_Airflow", header_text="Design Airflow", grid_column_width=24)
    schedule.set_field_hidden("DDM_Notes", True)
    schedule.add_header_group("Performance", ["DDM_Airflow", "DDM_Capacity"])
    return catalog


def test_each_schedule_becomes_three_revit_schedules():
    assert revit_schedule_names("Mechanical Schedule") == [
        "3D - Mechanical Schedule", "Mechanical Schedule - Working", "Mechanical Schedule",
    ]
    source = generate_schedule_macro_source(make_catalog())

    assert "public void CreateSchedulesFromDatabase()" in source
    assert 'DdmModelPrefix = "3D - "' in source
    assert 'DdmWorkingSuffix = " - Working"' in source
    assert 'DdmFilterParameter = "IPS_GROUP_Schedule_Name"' in source
    # Multi-category for the model; Detail Items for the working and finished schedules.
    assert "ElementId.InvalidElementId, spec, true" in source
    assert "BuiltInCategory.OST_DetailComponents" in source
    assert "DdmWorkingSuffix, detailItems, spec, false" in source


def test_columns_carry_headers_widths_in_feet_and_hidden_flags():
    specs, notes = schedule_specs(make_catalog())

    assert notes == []
    assert specs[0]["columns"] == [
        {"parameter": "DDM_Airflow", "header": "Design Airflow", "width_feet": 2.0, "hidden": False},
        {"parameter": "DDM_Capacity", "header": "DDM_Capacity", "width_feet": 1.25, "hidden": False},
        {"parameter": "DDM_Notes", "header": "DDM_Notes", "width_feet": 1 / 12, "hidden": True},
    ]
    assert specs[0]["header_groups"] == [{"caption": "Performance", "parameters": ["DDM_Airflow", "DDM_Capacity"]}]

    source = generate_schedule_macro_source(make_catalog())
    assert 'new DdmColumn("DDM_Airflow", "Design Airflow", 2, false),' in source
    assert 'new DdmColumn("DDM_Notes", "DDM_Notes", 0.0833333333333, true),' in source
    assert 'new DdmHeaderGroup("Performance", new[] { "DDM_Airflow", "DDM_Capacity" }),' in source


def test_the_macro_asks_what_to_build_and_whether_to_override():
    source = generate_schedule_macro_source(make_catalog())
    assert "DdmChoice? choice = DdmAskWhatToBuild(doc, tracker, MainWindowHandle);" in source
    assert '"Rebuild All Schedules ({names.Count})"' in source
    assert '"Rebuild Selected Schedules:"' in source
    assert '"Override Existing Schedules", Checked = true' in source
    assert "DdmSchedules.Where(spec => choice.Names.Contains(spec.Name))" in source
    # With override off, a schedule that already exists is left as it is.
    assert "if (existing != null && !overrideExisting)" in source
    # Windows Forms comes in under an alias, so its names can't clash with Revit's.
    assert "using WinForms = System.Windows.Forms;" in source
    assert "\nusing System.Windows.Forms;" not in source


def test_a_schedules_guid_survives_a_rename_and_saving():
    catalog = make_catalog()
    schedule = catalog.get_schedule("Mechanical Schedule")
    guid = schedule.guid
    schedule.name = "Renamed Schedule"
    assert schedule.guid == guid
    assert schedule_specs(catalog)[0][0]["guid"] == guid
    assert catalog.to_dict()["schedules"][0]["guid"] == guid
    assert Catalog.from_dict(catalog.to_dict()).schedules[0].guid == guid


def test_a_schedules_guid_survives_csv(tmp_path):
    catalog = make_catalog()
    guid = catalog.schedules[0].guid
    path = tmp_path / "database.csv"
    write_database_csv(catalog, path)
    tables, header_groups = read_database_csv(path)
    loaded, _issues = catalog_from_tables(header_groups=header_groups, **tables)
    assert loaded.schedules[0].guid == guid


def test_schedules_in_a_catalog_have_different_guids():
    catalog = make_catalog()
    copy = catalog.add_schedule("Other", guid=catalog.schedules[0].guid)
    assert copy.guid != catalog.schedules[0].guid
    assert catalog.add_schedule("Third").guid != copy.guid


def test_the_macro_tracks_schedules_and_asks_when_a_name_has_changed():
    catalog = make_catalog()
    source = generate_schedule_macro_source(catalog)
    assert f'new DdmSchedule("Mechanical Schedule", "{catalog.schedules[0].guid}", ' in source
    assert "/*TRACKING_SCHEMA*/" not in source
    assert "ViewSchedule? existing = tracker.Find(key);" in source
    assert "tracker.Record(key, schedule);" in source
    for option in ("Use Database Name", "Keep Revit Name", "Leave Unchanged", "Create New Schedule"):
        assert f'"{option}"' in source
    assert '"Do the Same for the Rest"' in source
    # Asked after the override check, so turning override off never prompts.
    assert source.index("if (existing != null && !overrideExisting)") < source.index("namePrompt.Ask(")


def test_the_macro_goes_in_the_modules_namespace():
    assert "namespace RevitMacros\n" in generate_schedule_macro_source(make_catalog())
    assert "namespace Team.Macros\n" in generate_schedule_macro_source(make_catalog(), namespace="Team.Macros")


def test_schedule_settings_reach_the_macro():
    catalog = make_catalog()
    specs, _notes = schedule_specs(catalog)
    assert (specs[0]["filter_value"], specs[0]["itemize"], specs[0]["view_template"]) == (
        "Mechanical Schedule", True, "")
    assert f'new DdmSchedule("Mechanical Schedule", "{catalog.schedules[0].guid}", "Mechanical Schedule", true, "",' in (
        generate_schedule_macro_source(catalog))

    schedule = catalog.schedules[0]
    schedule.filter_value = "MECH"
    schedule.itemize = False
    schedule.view_template = "IPS Schedules"
    source = generate_schedule_macro_source(catalog)
    assert f'new DdmSchedule("Mechanical Schedule", "{schedule.guid}", "MECH", false, "IPS Schedules",' in source
    assert "definition.IsItemized = spec.Itemize;" in source
    assert "ScheduleFilterType.Equal, spec.FilterValue" in source
    assert "schedule.ViewTemplateId = template.Id;" in source


def test_header_groups_go_innermost_first():
    catalog = make_catalog()
    schedule = catalog.schedules[0]
    schedule.set_field_hidden("DDM_Notes", False)
    schedule.add_header_group("Everything", ["DDM_Airflow", "DDM_Capacity", "DDM_Notes"])
    schedule.header_groups.reverse()

    specs, _notes = schedule_specs(catalog)
    assert [group["caption"] for group in specs[0]["header_groups"]] == ["Performance", "Everything"]


def test_schedules_revit_cant_name_or_that_clash_are_left_out_with_a_note():
    catalog = make_catalog()
    catalog.add_schedule("Bad: Name", ["AHU"], field_names=["DDM_Airflow"])
    catalog.add_schedule("3D - Mechanical Schedule", ["AHU"], field_names=["DDM_Airflow"])
    catalog.add_schedule("Empty", ["AHU"], field_names=[])

    specs, notes = schedule_specs(catalog)

    assert [spec["name"] for spec in specs] == ["Mechanical Schedule"]
    assert notes == [
        "Bad: Name: Revit view names can't contain :; skipped.",
        "3D - Mechanical Schedule: its Revit schedule names clash with schedule 'Mechanical Schedule'; skipped.",
        "Empty: no columns; skipped.",
    ]
    assert '"Empty: no columns; skipped.",' in generate_schedule_macro_source(catalog)


def test_install_replaces_older_generated_macros_and_leaves_other_files(tmp_path):
    (tmp_path / "ThisApplication.cs").write_text("using Autodesk.Revit.DB;\n", encoding="utf-8")
    (tmp_path / "test_data.cs").write_text("// Generated by Revit Parameter Manager. Add this file\n", encoding="utf-8")
    (tmp_path / "Other.cs").write_text(GENERATED_HEADER + " from old.ddm.json\n", encoding="utf-8")

    path, removed = install_macro("// new macro\n", tmp_path)

    assert path == tmp_path / MACRO_FILE_NAME
    assert path.read_text(encoding="utf-8") == "// new macro\n"
    assert sorted(p.name for p in removed) == ["Other.cs", "test_data.cs"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [MACRO_FILE_NAME, "ThisApplication.cs"]
    assert install_macro("x", tmp_path / "missing") == (None, [])


def newest_dotnet_framework():
    """``netN.0-windows`` for the newest installed .NET SDK, or ``None``."""
    if shutil.which("dotnet") is None:
        return None
    result = subprocess.run(["dotnet", "--list-sdks"], capture_output=True, text=True)
    majors = [int(line.split(".")[0]) for line in result.stdout.splitlines() if line[:1].isdigit()]
    return f"net{max(majors)}.0-windows" if majors else None


@pytest.mark.slow
def test_demo_macro_compiles_against_the_revit_api(tmp_path):
    """Build the demo database's macro the way the Revit macro module would, with warnings as errors."""
    revit = newest_revit_install()
    framework = newest_dotnet_framework()
    if revit is None or framework is None:
        pytest.skip("needs Revit 2025+ and the .NET SDK installed")

    tables, header_groups = read_database_csv(DEMO_DATA_PATH)
    demo, _issues = catalog_from_tables(header_groups=header_groups, **tables)
    # Cover every kind of data: a hidden column, a header group and a quote in a header.
    schedule = next(schedule for schedule in demo.schedules if len(schedule.params) >= 2)
    names = [param.name for param in schedule.params]
    schedule.set_field_hidden(names[-1], True)
    schedule.add_header_group('Group "A"', names[:2])
    schedule.filter_value = "FILTER"
    schedule.itemize = False
    schedule.view_template = "IPS Schedules"
    source = generate_schedule_macro_source(demo, namespace="GLoveMacros")
    (tmp_path / "Generated.cs").write_text(source, encoding="utf-8")
    (tmp_path / "ThisApplication.cs").write_text(MACRO_ENTRY_POINT, encoding="utf-8")
    (tmp_path / "Macro.csproj").write_text(MACRO_PROJECT.format(framework=framework, revit=revit), encoding="utf-8")
    module = MacroModule(2025, "Macro", tmp_path, "GLoveMacros")

    succeeded, messages = build_module(module)
    assert succeeded, "\n".join(messages)
    # The build turned on Windows Forms (for the macro's dialog) the way it would in a user's module.
    assert messages == [
        "Turned on Windows Forms in the Macro module, for the schedule macro's dialog "
        "(the original project file is Macro.csproj.bak).",
        "Built the Macro module; its macros are ready in Revit 2025's Macro Manager.",
    ]

    # A broken macro fails, and the messages name the file and line without the folder.
    (tmp_path / "Generated.cs").write_text(source.replace("tx.Commit();", "tx.Commit()"), encoding="utf-8")
    succeeded, messages = build_module(module)
    assert not succeeded
    assert messages[0].startswith("Generated.cs(") and ": error CS" in messages[0]
    assert messages[-1].startswith("The Macro module failed to build")
