"""Build the Revit add-in for Revit 2025 and each later Revit installed on this machine.

    .conda\\python.exe build_addin.py [year ...]

Each build goes to dist/revit-addin/<year>, which build_exe.py bundles into the .exe so users can
install the add-in without the .NET SDK. Revit 2025 builds from a Revit API reference package
(revit_addin.API_PACKAGES); other years need that Revit installed here.
"""

import sys

from revit_addin import AddinError, build_addin, buildable_years


def main(years):
    years = years or buildable_years()
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
