import subprocess
from types import SimpleNamespace

import revit_macro_module
from revit_macro_module import (
    MacroModule,
    build_module,
    choose_module,
    chosen_module,
    find_macro_modules,
)

SDK_PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0-windows</TargetFramework>
  </PropertyGroup>
</Project>
"""


def make_module(macros_root, year, name, namespace=None, project=SDK_PROJECT):
    """A Revit application macro module laid out like Revit 2025's. Returns its source folder."""
    source = macros_root / str(year) / "Revit" / "AppHookup" / name / "Source" / name
    source.mkdir(parents=True)
    (source / f"{name}.csproj").write_text(project, encoding="utf-8")
    (source / "ThisApplication.cs").write_text(
        f"using Autodesk.Revit.UI;\n\nnamespace {namespace or name}\n{{\n    public partial class ThisApplication {{ }}\n}}\n",
        encoding="utf-8",
    )
    return source


def test_finds_revit_2025_and_later_application_modules(tmp_path):
    make_module(tmp_path, 2025, "GLoveMacros")
    make_module(tmp_path, 2026, "TeamMacros", namespace="Team.Macros")
    make_module(tmp_path, 2024, "OldMacros")  # SharpDevelop era: not supported
    make_module(tmp_path, 2025, "NotSdk", project="<Project ToolsVersion=\"4.0\"></Project>")

    modules = find_macro_modules(tmp_path)

    assert [module.label for module in modules] == ["Revit 2026: TeamMacros", "Revit 2025: GLoveMacros"]
    assert modules[0].namespace == "Team.Macros"
    assert modules[1].project.name == "GLoveMacros.csproj"
    assert find_macro_modules(tmp_path / "missing") == []


def test_the_chosen_module_is_remembered_per_user(tmp_path):
    make_module(tmp_path / "Macros", 2025, "A")
    make_module(tmp_path / "Macros", 2025, "B")
    modules = find_macro_modules(tmp_path / "Macros")
    settings = tmp_path / "user" / "settings.json"

    assert chosen_module(modules, settings) is None
    choose_module(modules[1], settings)
    assert chosen_module(find_macro_modules(tmp_path / "Macros"), settings).name == "B"
    # A module that's gone is no longer chosen.
    assert chosen_module(modules[:1], settings) is None


def fake_run(results, calls):
    """Stand-in for ``subprocess.run``: dotnet --list-sdks, then each build's result in turn."""
    def run(args, **_kwargs):
        calls.append(args[1:])
        if args[1] == "--list-sdks":
            return SimpleNamespace(returncode=0, stdout="8.0.427 [C:\\sdk]\n10.0.403 [C:\\sdk]\n")
        return results.pop(0)
    return run


CS1705 = (
    "CSC : error CS1705: Assembly 'RevitAPI' with identity 'RevitAPI, Version=25.5.0.0' uses "
    "'System.Runtime, Version=10.0.0.0, Culture=neutral' which has a higher version than referenced "
    "assembly 'System.Runtime' with identity 'System.Runtime, Version=8.0.0.0' [C:\\m\\A.csproj]\n"
)


def test_a_module_built_for_an_older_dotnet_is_retargeted_and_rebuilt(tmp_path, monkeypatch):
    source = make_module(tmp_path, 2025, "A")
    module = find_macro_modules(tmp_path)[0]
    calls = []
    monkeypatch.setattr(revit_macro_module.shutil, "which", lambda _name: "dotnet")
    monkeypatch.setattr(revit_macro_module.subprocess, "run", fake_run([
        SimpleNamespace(returncode=1, stdout=CS1705),
        SimpleNamespace(returncode=0, stdout="Build succeeded.\n"),
    ], calls))

    succeeded, messages = build_module(module)

    assert succeeded
    assert "<TargetFramework>net10.0-windows</TargetFramework>" in (source / "A.csproj").read_text(encoding="utf-8")
    assert "net8.0-windows" in (source / "A.csproj.bak").read_text(encoding="utf-8")
    assert messages[0].startswith("Revit's API needs .NET 10; switched the A module to it")
    assert messages[-1] == "Built the A module; its macros are ready in Revit 2025's Macro Manager."
    assert [call[0] for call in calls] == ["build", "--list-sdks", "build"]


def test_missing_sdks_and_compile_errors_are_explained(tmp_path, monkeypatch):
    make_module(tmp_path, 2025, "A")
    module = find_macro_modules(tmp_path)[0]

    monkeypatch.setattr(revit_macro_module.shutil, "which", lambda _name: None)
    succeeded, messages = build_module(module)
    assert not succeeded and "The .NET SDK isn't installed" in messages[0]

    monkeypatch.setattr(revit_macro_module.shutil, "which", lambda _name: "dotnet")
    monkeypatch.setattr(revit_macro_module.subprocess, "run", fake_run([
        SimpleNamespace(returncode=1, stdout=CS1705.replace("Version=10.0.0.0", "Version=11.0.0.0")),
    ], []))
    succeeded, messages = build_module(module)
    assert not succeeded and "needs .NET 11, but that .NET SDK isn't installed" in messages[0]

    error = "C:\\m\\A\\CreateSchedulesFromDatabase.cs(12,5): error CS1002: ; expected [C:\\m\\A.csproj]\n"
    monkeypatch.setattr(revit_macro_module.subprocess, "run", fake_run([SimpleNamespace(returncode=1, stdout=error)], []))
    succeeded, messages = build_module(module)
    assert not succeeded
    assert messages == [
        "CreateSchedulesFromDatabase.cs(12,5): error CS1002: ; expected",
        "The A module failed to build (see above); Macro Manager still has its previous build.",
    ]

    def slow(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("dotnet", 1)

    monkeypatch.setattr(revit_macro_module.subprocess, "run", slow)
    assert "took over" in build_module(module, timeout=1)[1][0]


def test_macro_module_label():
    assert MacroModule(2025, "GLoveMacros", None, "GLoveMacros").label == "Revit 2025: GLoveMacros"
