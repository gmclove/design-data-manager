"""Export the parameter database in RushForth Tools Parameter Scheduler format."""

import pandas as pd

from config.revit_dtype_definitions import REVIT_DTYPE_TABLE
from config.revit_property_pallet_definitions import rf_tools_group_under
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
    if normalized in {"true", "1", "yes", "y", "instance"}:
        return True
    if normalized in {"false", "0", "no", "n", "type"}:
        return False
    raise ValueError(f"Instance or Type must be Instance or Type, got {value!r}.")


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
                "GroupUnder": rf_tools_group_under(_text(own("group_under"))),
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

    return _write_records(records)


def generate_rfps_schedules_content(
    schedule_columns,
    params_df: pd.DataFrame,
    shared_parameter_file_name: str = "shared-parameters.txt",
) -> str:
    """RFPS content with one template per schedule: ``schedule_columns`` is
    ``[(schedule name, [column names])]``. Each row takes the parameter's own settings.
    Columns that aren't parameters (combined parameters) are left out."""
    parameter_names = {_text(name) for name in params_df.get("name", [])}
    schedules = [
        (schedule_name, [name for name in columns if name in parameter_names])
        for schedule_name, columns in schedule_columns
    ]
    schedules = [(name, columns) for name, columns in schedules if _text(name) and columns]
    links = pd.DataFrame(
        [
            {"family_name": schedule_name, "parameter_name": column}
            for schedule_name, columns in schedules
            for column in columns
        ],
        columns=["family_name", "parameter_name"],
    )
    templates = pd.DataFrame({"name": [name for name, _columns in schedules]})
    return generate_rfps_content(templates, links, params_df, shared_parameter_file_name)


def _write_records(records) -> str:
    """Tab-delimited lines, each value exactly as it is: RF Tools reads quotes literally, so a
    formula like ``if(A, "NEW", "OLD")`` must not be wrapped or have its quotes doubled.
    A tab or line break inside a value would split the row, so it becomes a space."""
    def field(value):
        return " ".join(str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ").split("\t"))

    lines = ["\t".join(RFPS_COLUMNS)]
    for record in records:
        unknown = set(record) - set(RFPS_COLUMNS)
        if unknown:
            raise ValueError(f"Unknown RF Tools column(s): {', '.join(sorted(unknown))}")
        lines.append("\t".join(field(record.get(column, "")) for column in RFPS_COLUMNS))
    return "".join(line + "\r\n" for line in lines)
