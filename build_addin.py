"""Build the Revit add-in for each Revit (2025 and later) installed on this machine.

    .conda\\python.exe build_addin.py [year ...]

Each build goes to dist/revit-addin/<year>, which build_exe.py bundles into the .exe so users can
install the add-in without the .NET SDK. Building a year needs that Revit installed here.
"""

import sys

from revit_addin import AddinError, build_addin, installed_revit_years


def main(years):
    years = years or installed_revit_years()
    if not years:
        raise SystemExit("No Revit 2025 or later is installed here, so there's nothing to build against.")
    failed = False
    for year in years:
        try:
            print(f"Built the add-in for Revit {year}: {build_addin(year)}")
        except AddinError as exc:
            failed = True
            print(exc)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main([int(arg) for arg in sys.argv[1:]]))
