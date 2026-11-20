"""Build and install the Revit add-in (``revit-addin/``).

The add-in is built once per Revit year, 2025 and later, against that Revit's own API, into
``dist/revit-addin/<year>`` (bundled into the .exe). Installing copies a year's build into the
user's own add-ins folder, ``%APPDATA%\\Autodesk\\Revit\\Addins\\<year>``, with a manifest that
Revit reads at startup. No admin rights are needed.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from config.app_paths import ADDIN_BUILD_DIR, PROJECT_ROOT

ADDIN_PROJECT = PROJECT_ROOT / "revit-addin" / "DesignDataManager.Revit.csproj"
ADDIN_FOLDER_NAME = "DesignDataManager"
ADDIN_ASSEMBLY = "DesignDataManager.Revit.dll"
ADDIN_MANIFEST = "DesignDataManager.addin"
# Revit tells add-ins apart by this; keep it the same in every version.
ADDIN_ID = "6f1d9c62-3b8e-4a57-9d0e-2c4b7a1e5f38"
ADDIN_CLASS = "DesignDataManager.Revit.App"
FIRST_YEAR = 2025  # the first Revit with a .NET (Core) API
REVIT_ROOT = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Autodesk"
# Revit years built from a Revit API reference package (Nice3point.Revit.Api, Autodesk's reference
# DLLs) instead of the installed Revit: (package version, .NET major version). Building for the
# year's first .NET makes one build load on every update of it (Revit 2025.5 moved to .NET 10,
# which still runs .NET 8 add-ins), and it builds without that Revit installed.
API_PACKAGES = {2025: ("2025.4.60", 8)}

MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!-- Installed by the Design Data Manager. Reinstall from its Install Revit Add-in button. -->
<RevitAddIns>
  <AddIn Type="Application">
    <Name>Design Data Manager</Name>
    <Assembly>{assembly}</Assembly>
    <AddInId>{addin_id}</AddInId>
    <FullClassName>{full_class}</FullClassName>
    <VendorId>IPS</VendorId>
    <VendorDescription>IPS: Design Data Manager</VendorDescription>
  </AddIn>
</RevitAddIns>
"""


class AddinError(Exception):
    """Building or installing the add-in failed; the message says what to do."""


def installed_revit_years(root=REVIT_ROOT):
    """The Revit years installed here that can run the add-in, oldest first."""
    years = []
    for folder in Path(root).glob("Revit 20[0-9][0-9]"):
        year = int(folder.name.split()[-1])
        if year >= FIRST_YEAR and (folder / "RevitAPI.dll").is_file():
            years.append(year)
    return sorted(years)


def buildable_years(root=REVIT_ROOT):
    """The Revit years the add-in can be built for here: those with an API package, plus installed ones."""
    return sorted(set(API_PACKAGES) | set(installed_revit_years(root)))


def revit_api_dotnet(year, root=REVIT_ROOT):
    """The .NET major version Revit ``year``'s API was built for (8, or 10 since Revit 2025.5),
    read from RevitAPI.dll's target framework; ``None`` if it can't be read."""
    try:
        data = (Path(root) / f"Revit {year}" / "RevitAPI.dll").read_bytes()
    except OSError:
        return None
    match = re.search(rb"\.NETCoreApp,Version=v(\d+)\.", data)
    return int(match.group(1)) if match else None


def built_years(build_dir=ADDIN_BUILD_DIR):
    """The Revit years with a build of the add-in in ``build_dir``."""
    build_dir = Path(build_dir)
    if not build_dir.is_dir():
        return []
    return sorted(int(folder.name) for folder in build_dir.iterdir()
                  if folder.name.isdigit() and (folder / ADDIN_ASSEMBLY).is_file())


def build_addin(year, build_dir=ADDIN_BUILD_DIR, root=REVIT_ROOT, timeout=600):
    """Build the add-in against Revit ``year`` into ``build_dir/<year>``. Returns the folder;
    raises ``AddinError`` with the compiler's errors if it fails."""
    if shutil.which("dotnet") is None:
        raise AddinError("The .NET SDK isn't installed; get it from https://dotnet.microsoft.com/download.")
    if year in API_PACKAGES:
        package, dotnet = API_PACKAGES[year]
        api = [f"-p:RevitApiPackage={package}"]
    else:
        package, dotnet = None, revit_api_dotnet(year, root)
        if dotnet is None:
            raise AddinError(f"Couldn't read which .NET Revit {year}'s API needs.")
        api = [f"-p:RevitPath={Path(root) / f'Revit {year}'}"]
    output = Path(build_dir) / str(year)
    if output.exists():
        shutil.rmtree(output)
    result = subprocess.run(
        ["dotnet", "build", str(ADDIN_PROJECT), "-c", "Release", "-nologo",
         f"-p:RevitYear={year}", *api, f"-p:DotNetVersion={dotnet}",
         # Each year in its own intermediate folder, so builds for different .NET versions don't mix.
         f"-p:BaseIntermediateOutputPath=obj\\{year}\\", "-o", str(output)],
        capture_output=True, text=True, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        errors = sorted({line.strip() for line in result.stdout.splitlines() if ": error " in line})
        raise AddinError(f"The add-in failed to build for Revit {year}:\n" + "\n".join(errors or [result.stdout[-2000:]]))
    (output / "addin-build.json").write_text(json.dumps({"revit_year": year, "dotnet": dotnet, "api_package": package}), encoding="utf-8")
    return output


def addins_folder(year, appdata=None):
    """Revit ``year``'s add-ins folder for this user."""
    appdata = Path(appdata or os.environ.get("APPDATA", Path.home()))
    return appdata / "Autodesk" / "Revit" / "Addins" / str(year)


def manifest_text():
    return MANIFEST_TEMPLATE.format(
        assembly=f"{ADDIN_FOLDER_NAME}\\{ADDIN_ASSEMBLY}", addin_id=ADDIN_ID, full_class=ADDIN_CLASS,
    )


def install_addin(year, build_dir=ADDIN_BUILD_DIR, appdata=None):
    """Install the add-in for Revit ``year`` for this user. Returns the manifest's path; raises
    ``AddinError`` when there's no build for that year or Revit has the add-in open."""
    source = Path(build_dir) / str(year)
    if not (source / ADDIN_ASSEMBLY).is_file():
        raise AddinError(f"There's no build of the add-in for Revit {year}.")
    folder = addins_folder(year, appdata)
    target = folder / ADDIN_FOLDER_NAME
    try:
        target.mkdir(parents=True, exist_ok=True)
        for path in source.iterdir():
            if path.is_file():
                shutil.copy2(path, target / path.name)
        manifest = folder / ADDIN_MANIFEST
        manifest.write_text(manifest_text(), encoding="utf-8")
    except PermissionError as exc:
        raise AddinError(
            f"Revit {year} is using the add-in, so it can't be replaced. Close Revit {year}, then install again.\n\n"
            "Already closed? Revit can keep running after its window closes. Open Task Manager "
            "(Ctrl+Shift+Esc), end each Revit entry, then install again (or restart the computer)."
        ) from exc
    except OSError as exc:
        raise AddinError(f"The add-in couldn't be installed for Revit {year}: {exc}") from exc
    return manifest


def installed_addin_years(appdata=None):
    """The Revit years this user has the add-in installed for (its manifest is there)."""
    base = addins_folder(FIRST_YEAR, appdata).parent
    if not base.is_dir():
        return []
    return sorted(int(folder.name) for folder in base.iterdir()
                  if folder.name.isdigit() and (folder / ADDIN_MANIFEST).is_file())


def refresh_installed(build_dir=ADDIN_BUILD_DIR, appdata=None):
    """After the app is updated: reinstall the add-in where the user already has it, from this copy's
    builds. Returns ``(refreshed years, problems)``; a problem is usually Revit having it open."""
    built = set(built_years(build_dir))
    refreshed, problems = [], []
    for year in installed_addin_years(appdata):
        if year not in built:
            continue
        try:
            install_addin(year, build_dir, appdata)
        except AddinError as exc:
            problems.append(str(exc))
            continue
        refreshed.append(year)
    return refreshed, problems


def install_all(build_dir=ADDIN_BUILD_DIR, appdata=None, root=REVIT_ROOT):
    """Install the add-in for every Revit year here that has a build. Returns ``(installed, messages)``."""
    years = installed_revit_years(root)
    built = set(built_years(build_dir))
    installed, messages = [], []
    if not years:
        return [], [f"No Revit {FIRST_YEAR} or later is installed, so there's nothing to add the add-in to."]
    for year in years:
        if year not in built:
            messages.append(f"Revit {year}: this copy of the Design Data Manager has no add-in built for it.")
            continue
        try:
            manifest = install_addin(year, build_dir, appdata)
        except AddinError as exc:
            messages.append(str(exc))
            continue
        installed.append(year)
        messages.append(f"Revit {year}: installed ({manifest}). Start Revit {year} to see the Design Data tab.")
    return installed, messages
