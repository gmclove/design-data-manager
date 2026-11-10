"""Typical column widths from the macro's ExportScheduleWidths files."""

import json

import pytest

from revit_parameter_manager import Catalog
from revit_widths import apply_typical_widths, load_width_exports, snap_width, typical_widths


def column(parameter, inches, guid=None, hidden=False):
    return {"parameter": parameter, "guid": guid, "heading": parameter.upper(),
            "width_feet": inches / 12, "hidden": hidden}


def export(project, *schedules):
    return {"version": 1, "project": project, "schedules": [
        {"name": name, "category": "Mechanical Equipment", "columns": columns} for name, columns in schedules
    ]}


@pytest.fixture
def catalog():
    catalog = Catalog()
    catalog.add_param("Tag", "Text")
    catalog.add_param("Airflow", "Number", grid_column_width=1.0)
    catalog.add_family("F", ["Tag", "Airflow"])
    return catalog


def test_snap_width_rounds_to_a_sixteenth():
    assert snap_width(0.7) == 0.6875
    assert snap_width(1.03) == 1.0
    assert snap_width(1.04) == 1.0625


def test_the_most_common_adjusted_width_wins_and_defaults_and_hidden_columns_dont_count(catalog):
    exports = [(None, export(
        "Project A",
        ("Fans", [column("Airflow", 0.75), column("Tag", 1.0)]),
        ("Pumps", [column("Airflow", 0.75), column("Tag", 0.5, hidden=True)]),
    )), (None, export(
        "Project B",
        ("AHUs", [column("Airflow", 1.25), column("Airflow", 1.0), column("Not In Database", 2.0)]),
    ))]

    rows = {row["parameter"]: row for row in typical_widths(catalog, exports)}

    airflow = rows["Airflow"]
    assert airflow["typical"] == 0.75
    assert (airflow["agree"], airflow["adjusted_uses"], airflow["total_uses"]) == (2, 3, 4)
    assert airflow["spread"] == [(0.75, 2), (1.25, 1)]
    assert airflow["projects"] == ["Project A", "Project B"]
    # Tag is only at Revit's default width or hidden: nothing to go on.
    assert rows["Tag"]["typical"] is None
    assert "Not In Database" not in rows


def test_a_tie_goes_to_the_wider_width(catalog):
    exports = [(None, export("P", ("S", [column("Airflow", 0.75), column("Airflow", 1.5)])))]
    assert typical_widths(catalog, exports)[0]["typical"] == 1.5


def test_columns_match_by_guid_so_renamed_parameters_still_count(catalog):
    guid = catalog.get_param("Airflow").guid
    catalog.rename_param("Airflow", "Supply_Airflow", keep_guid=True)
    exports = [(None, export("P", ("S", [column("Airflow", 0.875, guid=guid)])))]

    rows = typical_widths(catalog, exports)

    assert [(row["parameter"], row["typical"]) for row in rows] == [("Supply_Airflow", 0.875)]


def test_applying_a_width_clears_only_the_overrides_it_makes_redundant(catalog):
    first = catalog.add_schedule("First", ["F"])
    second = catalog.add_schedule("Second", ["F"])
    third = catalog.add_schedule("Third", ["F"])
    first.grid_column_width_overrides["Airflow"] = 0.75
    second.grid_column_width_overrides["Airflow"] = 2.0

    summary = apply_typical_widths(catalog, {"Airflow": 0.75})

    assert catalog.get_param("Airflow").grid_column_width == 0.75
    assert "Airflow" not in first.grid_column_width_overrides
    assert second.grid_column_width_overrides["Airflow"] == 2.0
    assert summary == {"parameters": ["Airflow"], "overrides_cleared": 1, "schedules_changed": ["Third"]}


def test_exports_are_read_from_the_folder_and_bad_files_reported(tmp_path):
    (tmp_path / "A.widths.json").write_text(json.dumps(export("A")), encoding="utf-8")
    (tmp_path / "B.widths.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    exports, problems = load_width_exports(tmp_path)

    assert [data["project"] for _path, data in exports] == ["A"]
    assert [path.name for path, _error in problems] == ["B.widths.json"]
