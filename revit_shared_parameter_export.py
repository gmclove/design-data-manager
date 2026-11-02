"""Generate a Revit shared-parameter file from the parameter database."""

import csv
import io
import uuid

import pandas as pd

from config.revit_dtype_definitions import REVIT_DTYPE_TABLE


SHARED_PARAMETER_COLUMNS = [
    "GUID",
    "NAME",
    "DATATYPE",
    "DATACATEGORY",
    "GROUP",
    "VISIBLE",
    "DESCRIPTION",
    "USERMODIFIABLE",
    "HIDEWHENNOVALUE",
]

_GUID_NAMESPACE = uuid.UUID("3a7af2e6-3e41-4e49-9775-d3ef946f6bc4")
_DATA_TYPE_EXPORT_NAMES = dict(
    zip(REVIT_DTYPE_TABLE["Data Types"], REVIT_DTYPE_TABLE["Export Name"])
)


def _text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def parameter_guid(name, guid=None):
    """Return the parameter's stored GUID, or the stable GUID derived from its name."""
    return _text(guid) or str(uuid.uuid5(_GUID_NAMESPACE, name))


def generate_shared_parameter_content(params_df: pd.DataFrame) -> str:
    """Return a Revit-format shared-parameter file with stable parameter GUIDs."""
    parameters = []
    seen_names = set()

    for _, parameter in params_df.iterrows():
        name = _text(parameter.get("name"))
        if not name:
            continue
        if name in seen_names:
            raise ValueError(f"Duplicate shared parameter name '{name}'.")
        seen_names.add(name)

        dtype_name = _text(parameter.get("dtype"))
        data_type = _DATA_TYPE_EXPORT_NAMES.get(dtype_name)
        if data_type is None:
            raise ValueError(
                f"Parameter '{name}' has unsupported Revit data type '{dtype_name}'."
            )

        parameters.append(
            [
                parameter_guid(name, parameter.get("guid")),
                name,
                data_type,
                "",
                "1",
                "1",
                "",
                "1",
                "0",
            ]
        )

    output = io.StringIO(newline="")
    writer = csv.writer(
        output,
        delimiter="\t",
        lineterminator="\r\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerows(
        [
            ["# This is a Revit shared parameter file.", "", "", "", "", "", "", "", ""],
            ["# Do not edit manually.", "", "", "", "", "", "", "", ""],
            ["*META", "VERSION", "MINVERSION", "", "", "", "", "", ""],
            ["META", "2", "1", "", "", "", "", "", ""],
            ["*GROUP", "ID", "NAME", "", "", "", "", "", ""],
            ["GROUP", "1", "IPS", "", "", "", "", "", ""],
            ["*PARAM", *SHARED_PARAMETER_COLUMNS],
        ]
    )
    writer.writerows([["PARAM", *parameter] for parameter in parameters])
    return output.getvalue()
