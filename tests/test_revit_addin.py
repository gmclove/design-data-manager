"""The Revit add-in: the schedules file it reads, building it, and installing it per user."""

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

import ddm_gui as gui_module
import revit_addin
from config.app_paths import DEMO_DATA_PATH, PROJECT_ROOT
from ddm_tables import catalog_from_tables, read_database_csv
from revit_addin import (
    ADDIN_ASSEMBLY, ADDIN_CLASS, ADDIN_ID, AddinError, build_addin, install_addin, install_all,
    installed_revit_years, revit_api_dotnet,
)
from revit_schedule_macro_generator import generate_schedule_data
from test_ddm_gui import make_test_gui


def fake_revit(root, year, dotnet=10):
    folder = root / f"Revit {year}"
    folder.mkdir(parents=True)
    (folder / "RevitAPI.dll").write_bytes(b"MZ...\x00.NETCoreApp,Version=v%d.0\x00..." % dotnet)
    return folder


def fake_build(build_dir, year):
    folder = build_dir / str(year)
    folder.mkdir(parents=True)
    (folder / ADDIN_ASSEMBLY).write_bytes(b"dll")
    (folder / "DesignDataManager.Revit.deps.json").write_text("{}", encoding="utf-8")
    return folder


def test_revit_years_and_their_dotnet_come_from_the_installs(tmp_path):
    fake_revit(tmp_path, 2024)  # too old: no .NET (Core) API
    fake_revit(tmp_path, 2025, dotnet=10)
    fake_revit(tmp_path, 2026, dotnet=8)
    (tmp_path / "Revit 2027").mkdir()  # no API: not a real install

    assert installed_revit_years(tmp_path) == [2025, 2026]
    assert revit_api_dotnet(2025, tmp_path) == 10
    assert revit_api_dotnet(2026, tmp_path) == 8
    assert revit_api_dotnet(2030, tmp_path) is None


def test_installing_copies_the_build_and_writes_the_manifest(tmp_path):
    build_dir, appdata = tmp_path / "build", tmp_path / "appdata"
    fake_build(build_dir, 2025)

    manifest = install_addin(2025, build_dir, appdata)

    folder = appdata / "Autodesk" / "Revit" / "Addins" / "2025"
    assert manifest == folder / "DesignDataManager.addin"
    assert (folder / "DesignDataManager" / ADDIN_ASSEMBLY).read_bytes() == b"dll"
    addin = ET.parse(manifest).getroot().find("AddIn")
    assert addin.get("Type") == "Application"
    assert addin.findtext("Assembly") == "DesignDataManager\\" + ADDIN_ASSEMBLY
    assert addin.findtext("AddInId") == ADDIN_ID
    assert addin.findtext("FullClassName") == ADDIN_CLASS

    # Installing again replaces it.
    (build_dir / "2025" / ADDIN_ASSEMBLY).write_bytes(b"new dll")
    install_addin(2025, build_dir, appdata)
    assert (folder / "DesignDataManager" / ADDIN_ASSEMBLY).read_bytes() == b"new dll"


def test_installing_says_to_close_revit_when_it_has_the_addin_open(tmp_path, monkeypatch):
    fake_build(tmp_path / "build", 2025)

    def locked(*_args, **_kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr(revit_addin.shutil, "copy2", locked)
    with pytest.raises(AddinError, match="Close Revit 2025, then install again"):
        install_addin(2025, tmp_path / "build", tmp_path / "appdata")
    with pytest.raises(AddinError, match="no build of the add-in for Revit 2026"):
        install_addin(2026, tmp_path / "build", tmp_path / "appdata")


def test_install_all_covers_each_revit_here_with_a_build(tmp_path):
    root, build_dir, appdata = tmp_path / "revit", tmp_path / "build", tmp_path / "appdata"
    fake_revit(root, 2025)
    fake_revit(root, 2026)
    fake_build(build_dir, 2025)

    installed, messages = install_all(build_dir, appdata, root)

    assert installed == [2025]
    assert messages[0].startswith("Revit 2025: installed")
    assert messages[1] == "Revit 2026: this copy of the Design Data Manager has no add-in built for it."
    assert install_all(build_dir, appdata, tmp_path / "none")[1] == [
        "No Revit 2025 or later is installed, so there's nothing to add the add-in to."]


def test_save_writes_the_schedules_file_and_tells_the_addin_where_it_is(tmp_path):
    gui = make_test_gui()
    database = tmp_path / "db.ddm.json"

    assert gui._save_to(database)

    data = json.loads((tmp_path / "db.schedules.json").read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["source"] == "db.ddm.json"
    assert [spec["name"] for spec in data["schedules"]] == [
        spec["name"] for spec in generate_schedule_data(gui.catalog)["schedules"]]
    settings = json.loads(gui_module.USER_SETTINGS_PATH.read_text(encoding="utf-8"))
    assert settings["schedule_data_path"] == str((tmp_path / "db.schedules.json").resolve())


def test_the_install_button_reports_each_revit(monkeypatch):
    gui = make_test_gui()
    shown = []
    monkeypatch.setattr(gui_module, "install_all", lambda: ([2025], ["Revit 2025: installed (x)."]))
    monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda title, message, **_kw: shown.append((title, message)))

    assert gui.install_revit_addin() == [2025]
    assert shown == [("Install Revit Add-in", "Revit 2025: installed (x).")]


@pytest.mark.slow
def test_the_addin_builds_and_reads_the_schedules_file_save_writes(tmp_path):
    """Build the add-in against the newest Revit here, and read a real schedules file with its own
    reader (run without Revit), so the C# and schedule_specs agree."""
    years = installed_revit_years()
    if not years or shutil.which("dotnet") is None:
        pytest.skip("needs Revit 2025+ and the .NET SDK installed")

    output = build_addin(years[-1], tmp_path / "build")
    assert (output / ADDIN_ASSEMBLY).is_file()

    tables, header_groups = read_database_csv(DEMO_DATA_PATH)
    demo, _issues = catalog_from_tables(header_groups=header_groups, **tables)
    names = [param.name for param in demo.schedules[0].params]
    demo.add_combined_param("TAG", [names[0], {"parameter": names[1], "prefix": '"-', "separator": "/"}])
    demo.schedules[0].add_columns(["TAG"])
    demo.schedules[0].add_header_group('Group "A"', names[:2])
    demo.schedules[0].set_sorting(
        [{"parameter": names[0], "descending": True, "show_footer": True, "show_footer_count": False},
         {"parameter": names[1], "show_header": True, "show_blank_line": True}],
        show_grand_total=True, show_grand_total_count=False, grand_total_title='Total "All"',
    )
    data = generate_schedule_data(demo, "demo.ddm.json", saved_at="2026-11-09 12:00")
    schedules_file = tmp_path / "demo.schedules.json"
    schedules_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    check = PROJECT_ROOT / "revit-addin" / "tests" / "ScheduleDataCheck"
    result = subprocess.run(
        ["dotnet", "run", "--project", str(check), "--", str(schedules_file)],
        capture_output=True, text=True, encoding="utf-8", timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    read = json.loads(result.stdout.strip().splitlines()[-1])

    # The last-sync JSON the add-in stores reads back as schedule_specs' specs (for the three-way review).
    assert read.pop("round_trip") is True
    assert read.pop("linker") == json.loads(json.dumps(data["linker"]))
    assert read.pop("linker_plans") is None  # no elements file given
    assert read.pop("synced") == json.loads(json.dumps(data["schedules"]))
    assert "sorting" in data["schedules"][0]  # so the synced check above covers reading it
    expected = json.loads(json.dumps({key: data[key] for key in ("source", "saved_at", "notes", "schedules")}))
    for spec in expected["schedules"]:
        spec.pop("sorting", None)  # the check prints the plain fields; sorting is in synced
        for column in spec["columns"]:
            column["width_feet"] = float(column["width_feet"])
    for spec in read["schedules"]:
        for column in spec["columns"]:
            column["width_feet"] = float(column["width_feet"])
    assert read == expected


def test_the_addin_reads_the_linker_data_and_plans_linking(tmp_path, linker_catalog):
    """The add-in's own reader and Linker rules (Shared/LinkerPlan.cs, run without Revit) on a
    project with a copy-pasted primary, a primary without an ID, a stale copy and an unlinked one."""
    if shutil.which("dotnet") is None:
        pytest.skip("needs the .NET SDK installed")
    data = generate_schedule_data(linker_catalog, "linker.ddm.json", saved_at="2026-11-17 09:00")
    schedules_file = tmp_path / "linker.schedules.json"
    schedules_file.write_text(json.dumps(data), encoding="utf-8")
    elements = [
        {"id": 1, "family": "AHU 2D", "linker_id": "AHU-0003", "values": {"Seq": "1", "TAG": "AHU-1"}},
        {"id": 2, "family": "AHU 2D", "linker_id": " AHU-0003 ", "values": {"Seq": "1", "TAG": "AHU-1"}},  # pasted
        {"id": 3, "family": "AHU 2D", "linker_id": "", "values": {"Seq": "2", "TAG": "AHU-2"}},
        {"id": 4, "family": "AHU 3D", "linker_id": "AHU-0003", "values": {"Seq": "1", "TAG": "old"}},
        {"id": 5, "family": "AHU 3D", "linker_id": "", "values": {"Seq": "", "TAG": ""}},
        {"id": 6, "family": "Space 2D", "linker_id": "", "values": {"Space Name": "Lab"}},
        {"id": 7, "family": "Not In The Database", "linker_id": "X-0001", "values": {}},
    ]
    elements_file = tmp_path / "elements.json"
    elements_file.write_text(json.dumps(elements), encoding="utf-8")

    check = PROJECT_ROOT / "revit-addin" / "tests" / "ScheduleDataCheck"
    result = subprocess.run(
        ["dotnet", "run", "--project", str(check), "--", str(schedules_file), str(elements_file)],
        capture_output=True, text=True, encoding="utf-8", timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    read = json.loads(result.stdout.strip().splitlines()[-1])

    assert read["linker"] == json.loads(json.dumps(data["linker"]))
    plans = read["linker_plans"]
    # Left as they are, the duplicate blocks copying to its linked element; blanks get the next IDs.
    assert plans["keep"] == {
        "assign": {"3": "AHU-0004", "6": "SPACE-0001"},
        "copies": [],
        "duplicates": {"AHU-0003": [1, 2]},
        "orphans": [5],
        "linked_to_update": 0,
    }
    # Renumbered, the oldest keeps AHU-0003, and its 3D element copies the new tag.
    assert plans["renumber"] == {
        "assign": {"2": "AHU-0004", "3": "AHU-0005", "6": "SPACE-0001"},
        "copies": [["1", "4", "TAG"]],
        "duplicates": {},
        "orphans": [5],
        "linked_to_update": 1,
    }
    assert plans["next_ids"] == ["AHU-0012", "PUMP-10000", "ITEM-0001"]
