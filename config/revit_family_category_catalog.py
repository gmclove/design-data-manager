import pandas as pd


REVIT_FAMILY_CATEGORY_ROWS = [
    {"Category": "Detail Item"},
    {"Category": "Generic Annotation"},
    {"Category": "Detail Item Tag"},
    {"Category": "Air Terminals"},
    {"Category": "Duct Accessories"},
    {"Category": "Duct Fittings"},
    {"Category": "Mechanical Equipment"},
    {"Category": "Pipe Accessories"},
    {"Category": "Pipe Fittings"},
    {"Category": "Air Terminals Tags"},
    {"Category": "Duct Accessories Tags"},
    {"Category": "Duct Fittings Tags"},
    {"Category": "Generic Models Tags"},
    {"Category": "Mechanical Equipment Tags"},
    {"Category": "Pipe Accessories Tags"},
    {"Category": "Pipe Fittings Tags"},
    {"Category": "Multi-Category Tags"},
    {"Category": "Doors"},
    {"Category": "Windows"},
    {"Category": "Curtain Wall"},
    {"Category": "Casework"},
    {"Category": "Railings"},
    {"Category": "Structural Framing"},
    {"Category": "Furniture"},
    {"Category": "Openings"},
    {"Category": "Generic Models"},
]

REVIT_FAMILY_CATEGORY_TABLE = pd.DataFrame(REVIT_FAMILY_CATEGORY_ROWS)

VALID_FAMILY_CATEGORY_NAMES = set(REVIT_FAMILY_CATEGORY_TABLE["Category"].tolist())


def get_family_category_row(category):
    row = REVIT_FAMILY_CATEGORY_TABLE[
        REVIT_FAMILY_CATEGORY_TABLE["Category"] == category
    ]
    return row.iloc[0] if not row.empty else None
