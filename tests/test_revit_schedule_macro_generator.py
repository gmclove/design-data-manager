import glob
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from config.app_paths import DEMO_DATA_PATH
from ddm_tables import catalog_from_tables, entries_table, families_table, params_table, read_database_csv
from revit_schedule_macro_generator import generate_schedule_macro_source

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


def make_database():
    family_groups = pd.DataFrame(
        [
            {
                "family_name": "AHU",
                "group_name": "Mechanical Schedule",
                "parameter_name": "DDM_Airflow",
                "header_text_override": "Design Airflow",
                "grid_column_width_override": "24.0",
            },
            {
                "family_name": "AHU",
                "group_name": "Mechanical Schedule",
                "parameter_name": "DDM_Capacity",
                "header_text_override": "",
                "grid_column_width_override": "",
            },
        ]
    )
    families = pd.DataFrame([{"name": "AHU", "category": "Mechanical Equipment"}])
    parameters = pd.DataFrame(
        [
            {"name": "DDM_Airflow", "header_text": "Airflow", "grid_column_width": 18},
            {"name": "DDM_Capacity", "header_text": "", "grid_column_width": 15},
        ]
    )
    return family_groups, families, parameters


def test_generated_macro_includes_schedule_category_fields_and_overrides():
    source = generate_schedule_macro_source(*make_database())

    assert "public void CreateSchedulesFromDatabase()" in source
    assert 'candidate.Name, "Mechanical Equipment"' in source
    assert 'candidate.GetName(doc), "DDM_Airflow"' in source
    assert 'scheduleField0.ColumnHeading = "Design Airflow";' in source
    assert "scheduleField0.GridColumnWidth = 2;" in source
    assert 'scheduleField1.ColumnHeading = "DDM_Capacity";' in source
    assert "scheduleField1.GridColumnWidth = 1.25;" in source
    assert "scheduleField0.HorizontalAlignment = ScheduleHorizontalAlignment.Center;" in source
    assert "scheduleField1.HorizontalAlignment = ScheduleHorizontalAlignment.Center;" in source
    assert "definition.AddField(schedulableField0)" in source
    assert "definition.AddField(schedulableField1)" in source
    assert "scheduleField1.GridColumnWidth = 1.25;" in source


def test_one_inch_default_width_is_converted_to_one_twelfth_foot():
    family_groups, families, parameters = make_database()
    family_groups = family_groups.iloc[[0]].copy()
    family_groups.loc[family_groups.index[0], "grid_column_width_override"] = ""
    parameters.loc[parameters["name"] == "DDM_Airflow", "grid_column_width"] = 1.0

    source = generate_schedule_macro_source(family_groups, families, parameters)

    assert "scheduleField0.GridColumnWidth = 0.0833333333333;" in source


def test_generator_reports_schedules_spanning_multiple_categories():
    family_groups, families, parameters = make_database()
    families.loc[len(families)] = {"name": "Door", "category": "Doors"}
    family_groups.loc[len(family_groups)] = {
        "family_name": "Door",
        "group_name": "Mechanical Schedule",
        "parameter_name": "DDM_Airflow",
    }

    source = generate_schedule_macro_source(family_groups, families, parameters)

    assert '"Mechanical Schedule (families span multiple Revit categories)"' in source


def test_generator_reports_invalid_column_width():
    family_groups, families, parameters = make_database()
    family_groups.loc[0, "grid_column_width_override"] = "wide"

    source = generate_schedule_macro_source(family_groups, families, parameters)

    assert "column width for" in source
    assert "is not a number" in source


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
    catalog, _issues = catalog_from_tables(header_groups=header_groups, **tables)
    source = generate_schedule_macro_source(entries_table(catalog), families_table(catalog), params_table(catalog))
    (tmp_path / "Generated.cs").write_text(source, encoding="utf-8")
    (tmp_path / "ThisApplication.cs").write_text(MACRO_ENTRY_POINT, encoding="utf-8")
    (tmp_path / "Macro.csproj").write_text(MACRO_PROJECT.format(framework=framework, revit=revit), encoding="utf-8")

    result = subprocess.run(
        ["dotnet", "build", "-nologo", "-v", "q", str(tmp_path / "Macro.csproj")],
        capture_output=True, text=True, timeout=300,
    )
    errors = [line for line in result.stdout.splitlines() if ": error " in line]
    assert result.returncode == 0, "\n".join(errors) or result.stdout[-3000:]
