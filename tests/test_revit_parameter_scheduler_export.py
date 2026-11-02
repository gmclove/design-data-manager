import csv
import io

import pandas as pd

from config.app_paths import TEST_DATABASE_CSV_PATH
from revit_parameter_scheduler_export import RFPS_COLUMNS, generate_rfps_content


def test_rfps_output_matches_sample_columns_and_maps_database_values():
    families = pd.DataFrame(
        [{"name": "AHU", "category": "Mechanical Equipment"}]
    )
    links = pd.DataFrame(
        [
            {"family_name": "AHU", "parameter_name": "DDM_Airflow"},
            {"family_name": "AHU", "parameter_name": "DDM_Airflow"},
        ]
    )
    parameters = pd.DataFrame(
        [
            {
                "name": "DDM_Airflow",
                "dtype": "Number",
                "group_under": "Mechanical Flow",
                "instance_param": True,
                "formula": "",
                "default_value": -999,
            }
        ]
    )

    content = generate_rfps_content(families, links, parameters)
    rows = list(csv.DictReader(io.StringIO(content), delimiter="\t"))

    assert content.splitlines()[0].split("\t") == RFPS_COLUMNS
    assert len(rows) == 1
    assert rows[0]["TemplateName"] == "AHU"
    assert rows[0]["Name"] == "DDM_Airflow"
    assert rows[0]["DataType"] == "NUMBER"
    assert rows[0]["GroupNumber"] == "1"
    assert rows[0]["GroupName"] == "IPS"
    assert rows[0]["InstanceOrType"] == "Instance"
    assert rows[0]["GroupUnder"] == "Mechanical Flow"
    assert rows[0]["Source"] == "./shared-parameters.txt"
    assert rows[0]["Value"] == "-999"


def test_rfps_guid_is_stable_across_exports_and_shared_by_linked_families():
    families = pd.DataFrame(
        [
            {"name": "AHU", "category": "Mechanical Equipment"},
            {"name": "Fan", "category": "Mechanical Equipment"},
        ]
    )
    links = pd.DataFrame(
        [
            {"family_name": "AHU", "parameter_name": "DDM_Airflow"},
            {"family_name": "Fan", "parameter_name": "DDM_Airflow"},
        ]
    )
    parameters = pd.DataFrame(
        [{"name": "DDM_Airflow", "dtype": "Number", "instance_param": False}]
    )

    first = generate_rfps_content(families, links, parameters)
    second = generate_rfps_content(families, links, parameters)
    rows = list(csv.DictReader(io.StringIO(first), delimiter="\t"))

    assert first == second
    assert rows[0]["GUID"] == rows[1]["GUID"]
    assert rows[0]["InstanceOrType"] == "Type"


def test_rfps_source_can_reference_database_shared_parameter_file():
    families = pd.DataFrame([{"name": "AHU", "category": "Mechanical Equipment"}])
    links = pd.DataFrame([{"family_name": "AHU", "parameter_name": "DDM_Airflow"}])
    parameters = pd.DataFrame([{"name": "DDM_Airflow", "dtype": "Number"}])

    content = generate_rfps_content(
        families,
        links,
        parameters,
        shared_parameter_file_name="test_data.txt",
    )
    rows = list(csv.DictReader(io.StringIO(content), delimiter="\t"))

    assert rows[0]["Source"] == "./test_data.txt"


def test_rfps_export_rejects_unknown_parameters():
    families = pd.DataFrame([{"name": "AHU", "category": "Mechanical Equipment"}])
    links = pd.DataFrame([{"family_name": "AHU", "parameter_name": "Missing"}])

    try:
        generate_rfps_content(families, links, pd.DataFrame(columns=["name", "dtype"]))
    except ValueError as exc:
        assert "unknown parameter 'Missing'" in str(exc)
    else:
        raise AssertionError("Expected an error for an unresolved parameter link.")


def test_default_database_rfps_includes_glass_area_and_other_linked_parameters():
    database = pd.read_csv(TEST_DATABASE_CSV_PATH, dtype=str, keep_default_na=False)
    parameters = database.loc[database["record_type"] == "parameter"].copy()
    families = database.loc[database["record_type"] == "family"].copy()
    links = database.loc[database["record_type"] == "link"].copy()

    content = generate_rfps_content(families, links, parameters)
    rows = list(csv.DictReader(io.StringIO(content), delimiter="\t"))
    glass_area = next(row for row in rows if row["Name"] == "GlassArea")

    assert glass_area["DataType"] == "AREA"
    assert glass_area["TemplateName"] == "Family_C"
