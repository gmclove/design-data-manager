import pandas as pd

from revit_schedule_macro_generator import generate_schedule_macro_source


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
    assert 'candidate.GetName(), "DDM_Airflow"' in source
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
