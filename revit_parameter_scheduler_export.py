"""Export the parameter database in RushForth Tools Parameter Scheduler format."""

import csv
import io

import pandas as pd

from config.revit_dtype_definitions import REVIT_DTYPE_TABLE
from revit_shared_parameter_export import parameter_guid


RFPS_COLUMNS = [
    "TemplateName",
    "GUID",
    "Name",
    "DataType",
    "GroupNumber",
    "GroupName",
    "Visible",
    "InstanceOrType",
    "GroupUnder",
    "Source",
    "ParamToReplace",
    "MapToElecConnector",
    "Value",
    "Formula",
    "SortOrder",
    "ToolTip",
    "UserModifiable",
]

_DATA_TYPE_EXPORT_NAMES = dict(
    zip(REVIT_DTYPE_TABLE["Data Types"], REVIT_DTYPE_TABLE["Export Name"])
)


def _text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _is_instance(value):
    normalized = _text(value).lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Instance Param must be true or false, got {value!r}.")


def generate_rfps_content(
    families_df: pd.DataFrame,
    family_param_links_df: pd.DataFrame,
    params_df: pd.DataFrame,
    shared_parameter_file_name: str = "shared-parameters.txt",
) -> str:
    """Return RFPS tab-delimited content in the sample file's column order."""
    families = {
        _text(row.get("name")): row
        for _, row in families_df.iterrows()
        if _text(row.get("name"))
    }
    parameters = {
        _text(row.get("name")): row
        for _, row in params_df.iterrows()
        if _text(row.get("name"))
    }
    records = []
    seen_links = set()

    for _, link in family_param_links_df.iterrows():
        family_name = _text(link.get("family_name"))
        parameter_name = _text(link.get("parameter_name"))
        if not family_name or not parameter_name:
            continue

        pair = (family_name, parameter_name)
        if pair in seen_links:
            continue
        seen_links.add(pair)

        family = families.get(family_name)
        if family is None:
            raise ValueError(
                f"Parameter link references unknown family '{family_name}'."
            )
        parameter = parameters.get(parameter_name)
        if parameter is None:
            raise ValueError(
                f"Parameter link references unknown parameter '{parameter_name}'."
            )

        def own(column):
            """The family's own setting for this parameter, else the parameter's."""
            value = link.get(column)
            return parameter.get(column) if _text(value) == "" else value

        dtype_name = _text(parameter.get("dtype"))
        data_type = _DATA_TYPE_EXPORT_NAMES.get(dtype_name)
        if data_type is None:
            raise ValueError(
                f"Parameter '{parameter_name}' has unsupported Revit data type '{dtype_name}'."
            )

        records.append(
            {
                "TemplateName": family_name,
                "GUID": parameter_guid(parameter_name, parameter.get("guid")),
                "Name": parameter_name,
                "DataType": data_type,
                "GroupNumber": "1",
                "GroupName": "IPS",
                "Visible": "1",
                "InstanceOrType": (
                    "Instance"
                    if _is_instance(own("instance_param") if _text(own("instance_param")) else True)
                    else "Type"
                ),
                "GroupUnder": _text(own("group_under")),
                "Source": f"./{shared_parameter_file_name}",
                "ParamToReplace": "",
                "MapToElecConnector": "0",
                "Value": _text(own("default_value")),
                "Formula": _text(own("formula")),
                "SortOrder": "",
                "ToolTip": "",
                "UserModifiable": "1",
            }
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=RFPS_COLUMNS,
        delimiter="\t",
        lineterminator="\r\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()
