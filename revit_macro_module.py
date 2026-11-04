"""Find a user's Revit macro modules, remember which one gets the schedule macro, and build it.

Revit 2025 and later keep each application macro module as a .NET project under
``%ProgramData%\\Autodesk\\Revit\\Macros\\<year>\\Revit\\AppHookup\\<module>\\Source\\<module>``,
built into the module's ``Addin`` folder. Macro Manager lists the public methods of
that build, so a new macro file shows only once the module is rebuilt. Earlier Revit
versions use a different (SharpDevelop) project and aren't supported.

Each user picks their module once; the choice is kept in their settings file.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MACROS_ROOT = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Autodesk" / "Revit" / "Macros"
USER_SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "DesignDataManager" / "settings.json"
DOTNET_DOWNLOAD_URL = "https://dotnet.microsoft.com/download"
_SETTING = "revit_macro_module"


@dataclass(frozen=True)
class MacroModule:
    year: int
    name: str
    source_dir: Path
    namespace: str

    @property
    def label(self):
        return f"Revit {self.year}: {self.name}"

    @property
    def project(self):
        return self.source_dir / f"{self.name}.csproj"


def find_macro_modules(root=MACROS_ROOT):
    """Every Revit 2025+ application macro module under ``root``, newest Revit first."""
    modules = []
    root = Path(root)
    if not root.is_dir():
        return modules
    for year_dir in root.iterdir():
        if not (year_dir.name.isdigit() and int(year_dir.name) >= 2025):
            continue
        hookup = year_dir / "Revit" / "AppHookup"
        if not hookup.is_dir():
            continue
        for module_dir in sorted(hookup.iterdir(), key=lambda path: path.name.lower()):
            source_dir = module_dir / "Source" / module_dir.name
            project = source_dir / f"{module_dir.name}.csproj"
            if not project.is_file() or "Microsoft.NET.Sdk" not in project.read_text(encoding="utf-8-sig", errors="replace"):
                continue
            modules.append(MacroModule(int(year_dir.name), module_dir.name, source_dir, _namespace(source_dir, module_dir.name)))
    return sorted(modules, key=lambda module: (-module.year, module.name.lower()))


def _namespace(source_dir, default):
    """The namespace of the module's ``ThisApplication`` class (its own name unless renamed)."""
    entry = source_dir / "ThisApplication.cs"
    if entry.is_file():
        match = re.search(r"^\s*namespace\s+([\w.]+)", entry.read_text(encoding="utf-8-sig", errors="replace"), re.M)
        if match:
            return match.group(1)
    return default


def load_settings(path=USER_SETTINGS_PATH):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings, path=USER_SETTINGS_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def chosen_module(modules, settings_path=USER_SETTINGS_PATH):
    """The module the user picked, if it still exists."""
    chosen = load_settings(settings_path).get(_SETTING)
    return next((module for module in modules if str(module.source_dir) == chosen), None)


def choose_module(module, settings_path=USER_SETTINGS_PATH):
    settings = load_settings(settings_path)
    settings[_SETTING] = str(module.source_dir)
    save_settings(settings, settings_path)


# --- building -----------------------------------------------------------------

def _dotnet_build(source_dir, timeout):
    return subprocess.run(
        [shutil.which("dotnet"), "build", "-nologo", "-v", "q"],
        cwd=source_dir, capture_output=True, text=True, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _compiler_lines(output):
    """Errors and warnings as ``file(line,col): message``, without folders or duplicates."""
    lines = []
    for line in output.splitlines():
        if ": error " not in line and ": warning " not in line:
            continue
        line = re.sub(r"\s*\[[^\]]*\.csproj\]\s*$", "", line.strip())
        line = re.sub(r"^[^(]*[\\/]", "", line)
        if line not in lines:
            lines.append(line)
    return lines


def _installed_sdk_majors():
    result = subprocess.run(
        [shutil.which("dotnet"), "--list-sdks"], capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return sorted({int(line.split(".")[0]) for line in result.stdout.splitlines() if line[:1].isdigit()})


def _retarget(project, major):
    """Point the project at ``net<major>.0-windows``, keeping the original as ``.csproj.bak``."""
    text = project.read_text(encoding="utf-8-sig")
    new_text, count = re.subn(
        r"<TargetFramework>[^<]*</TargetFramework>", f"<TargetFramework>net{major}.0-windows</TargetFramework>", text
    )
    if not count or new_text == text:
        return False
    backup = project.with_name(project.name + ".bak")
    if not backup.exists():
        shutil.copy2(project, backup)
    project.write_text(new_text, encoding="utf-8")
    return True


def build_module(module, timeout=300):
    """Build ``module`` so Macro Manager lists its macros. Returns ``(succeeded, messages)``.

    A Revit update can ship an API for a newer .NET than the module targets (error
    CS1705); the module is then retargeted to that .NET, with a backup, and rebuilt.
    """
    if shutil.which("dotnet") is None:
        return False, [
            f"The .NET SDK isn't installed, so the {module.name} module wasn't built. "
            f"Install it from {DOTNET_DOWNLOAD_URL}, or build the module in Revit's Macro Manager."
        ]
    messages = []
    try:
        result = _dotnet_build(module.source_dir, timeout)
        needed = re.search(r"CS1705.*?System\.Runtime, Version=(\d+)\.", result.stdout)
        if result.returncode != 0 and needed:
            major = int(needed.group(1))
            if major not in _installed_sdk_majors():
                return False, [
                    f"Revit's API needs .NET {major}, but that .NET SDK isn't installed, so the "
                    f"{module.name} module can't build. Install the .NET {major} SDK from {DOTNET_DOWNLOAD_URL}."
                ]
            if _retarget(module.project, major):
                messages.append(
                    f"Revit's API needs .NET {major}; switched the {module.name} module to it "
                    f"(the previous project file is {module.project.name}.bak)."
                )
                result = _dotnet_build(module.source_dir, timeout)
    except subprocess.TimeoutExpired:
        return False, [f"Building the {module.name} module took over {timeout} seconds and was stopped."]
    except OSError as exc:
        return False, [f"The {module.name} module couldn't be built: {exc}"]

    messages.extend(_compiler_lines(result.stdout))
    if result.returncode == 0:
        messages.append(f"Built the {module.name} module; its macros are ready in Revit {module.year}'s Macro Manager.")
    else:
        messages.append(
            f"The {module.name} module failed to build (see above); Macro Manager still has its previous build."
        )
    return result.returncode == 0, messages
