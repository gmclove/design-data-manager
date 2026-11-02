import csv
import io
import uuid

import pandas as pd
import pytest

from config.app_paths import TEST_DATABASE_CSV_PATH
from revit_shared_parameter_export import (
    SHARED_PARAMETER_COLUMNS,
    generate_shared_parameter_content,
)


def test_shared_parameter_content_matches_revit_file_format():
    parameters = pd.DataFrame(
        [
            {"name": "GlassArea", "dtype": "Area"},
            {"name": "DDM_Airflow", "dtype": "Number"},
        ]
    )

    content = generate_shared_parameter_content(parameters)
    rows = list(csv.reader(io.StringIO(content), delimiter="\t"))

    assert rows[:6] == [
        ["# This is a Revit shared parameter file.", "", "", "", "", "", "", "", ""],
        ["# Do not edit manually.", "", "", "", "", "", "", "", ""],
        ["*META", "VERSION", "MINVERSION", "", "", "", "", "", ""],
        ["META", "2", "1", "", "", "", "", "", ""],
        ["*GROUP", "ID", "NAME", "", "", "", "", "", ""],
        ["GROUP", "1", "IPS", "", "", "", "", "", ""],
    ]
    assert rows[6] == ["*PARAM", *SHARED_PARAMETER_COLUMNS]
    assert rows[7][0] == "PARAM"
    assert rows[7][1] == str(uuid.uuid5(uuid.UUID("3a7af2e6-3e41-4e49-9775-d3ef946f6bc4"), "GlassArea"))
    assert rows[7][2:5] == ["GlassArea", "AREA", ""]
    assert rows[7][5:] == ["1", "1", "", "1", "0"]
    assert rows[8][2:5] == ["DDM_Airflow", "NUMBER", ""]


def test_shared_parameter_guids_are_stable_across_exports():
    parameters = pd.DataFrame([{"name": "DDM_Airflow", "dtype": "Number"}])

    first = generate_shared_parameter_content(parameters)
    second = generate_shared_parameter_content(parameters)

    assert first == second


def test_shared_parameter_export_rejects_duplicate_names_and_unknown_types():
    duplicate_parameters = pd.DataFrame(
        [
            {"name": "Same", "dtype": "Number"},
            {"name": "Same", "dtype": "Text"},
        ]
    )
    with pytest.raises(ValueError, match="Duplicate shared parameter name"):
        generate_shared_parameter_content(duplicate_parameters)

    with pytest.raises(ValueError, match="unsupported Revit data type"):
        generate_shared_parameter_content(pd.DataFrame([{"name": "Unknown", "dtype": "NotAType"}]))


def test_default_database_parameters_all_export_to_shared_parameter_file():
    database = pd.read_csv(TEST_DATABASE_CSV_PATH, dtype=str, keep_default_na=False)
    parameters = database.loc[database["record_type"] == "parameter"]

    content = generate_shared_parameter_content(parameters)
    rows = list(csv.reader(io.StringIO(content), delimiter="\t"))
    exported_names = [row[2] for row in rows[7:] if row and row[0] == "PARAM"]

    assert len(exported_names) == len(parameters)
    assert set(exported_names) == set(parameters["name"])
    assert "GlassArea" in exported_names
