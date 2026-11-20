import urllib.error

import pytest

import app_update
import ddm_gui as gui_module
from app_update import (
    UpdateError, available_update, install_update, is_newer, latest_release, parse_version, remove_old_version,
)
from revit_addin import ADDIN_ASSEMBLY, install_addin, installed_addin_years, refresh_installed
from test_ddm_gui import make_test_gui
from test_revit_addin import fake_build

EXE = b"MZ" + b"\0" * 1_100_000


def release_json(tag="v0.2.0", assets=("DesignDataManager.exe",), body="New: updates."):
    return {
        "tag_name": tag, "body": body, "html_url": "https://example/releases/tag/" + tag,
        "assets": [{"name": name, "browser_download_url": "https://example/" + name} for name in assets],
    }


def test_versions_compare_by_number():
    assert parse_version("0.1.0 Beta") == (0, 1, 0)
    assert parse_version("v0.2") == (0, 2, 0)
    assert parse_version("Beta") is None
    assert is_newer("0.2.0", "0.1.0 Beta")
    assert is_newer("0.10.0", "0.9.0")  # numbers, not text
    assert not is_newer("0.1.0", "0.1.0 Beta")
    assert not is_newer("", "0.1.0")


def test_the_latest_release_needs_the_exe_attached():
    release = latest_release(get_json=lambda url, timeout: release_json())
    assert release == {"version": "0.2.0", "notes": "New: updates.", "exe_url": "https://example/DesignDataManager.exe",
                       "page": "https://example/releases/tag/v0.2.0"}
    assert latest_release(get_json=lambda url, timeout: release_json(assets=("notes.txt",))) is None
    assert available_update("0.2.0", get_json=lambda url, timeout: release_json()) is None
    assert available_update("0.1.0 Beta", get_json=lambda url, timeout: release_json())["version"] == "0.2.0"

    def offline(url, timeout):
        raise OSError("no network")

    with pytest.raises(UpdateError, match="Couldn't reach GitHub"):
        latest_release(get_json=offline)

    def no_releases_yet(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    assert latest_release(get_json=no_releases_yet) is None


def test_installing_swaps_the_exe_and_keeps_the_old_one_until_next_start(tmp_path):
    exe = tmp_path / "DesignDataManager.exe"
    exe.write_bytes(b"MZ old")

    install_update({"exe_url": "x"}, exe, download=lambda url, target, timeout: target.write_bytes(EXE))

    assert exe.read_bytes() == EXE
    assert (tmp_path / "DesignDataManager.exe.old").read_bytes() == b"MZ old"
    assert not (tmp_path / "DesignDataManager.exe.download").exists()
    remove_old_version(exe)
    assert not (tmp_path / "DesignDataManager.exe.old").exists()


def test_a_bad_download_leaves_the_program_alone(tmp_path):
    exe = tmp_path / "DesignDataManager.exe"
    exe.write_bytes(b"MZ old")

    with pytest.raises(UpdateError, match="isn't the Design Data Manager program"):
        install_update({"exe_url": "x"}, exe, download=lambda url, target, timeout: target.write_bytes(b"<html>"))

    def broken(url, target, timeout):
        raise OSError("connection reset")

    with pytest.raises(UpdateError, match="couldn't be downloaded"):
        install_update({"exe_url": "x"}, exe, download=broken)
    assert exe.read_bytes() == b"MZ old"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["DesignDataManager.exe"]


def test_refresh_reinstalls_only_where_the_addin_is_installed(tmp_path):
    build_dir, appdata = tmp_path / "build", tmp_path / "appdata"
    fake_build(build_dir, 2025)
    fake_build(build_dir, 2026)
    install_addin(2025, build_dir, appdata)
    (build_dir / "2025" / ADDIN_ASSEMBLY).write_bytes(b"new dll")

    assert installed_addin_years(appdata) == [2025]
    assert refresh_installed(build_dir, appdata) == ([2025], [])
    folder = appdata / "Autodesk" / "Revit" / "Addins"
    assert (folder / "2025" / "DesignDataManager" / ADDIN_ASSEMBLY).read_bytes() == b"new dll"
    assert not (folder / "2026").exists()  # never installed there, so left alone


def test_the_update_offer(monkeypatch):
    gui = make_test_gui()
    shown, asked = [], []
    monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda title, message, **_kw: shown.append((title, message)))
    monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda title, message, **_kw: shown.append((title, message)))
    monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda title, message, **_kw: asked.append(message) or False)
    release = latest_release(get_json=lambda url, timeout: release_json())

    # At startup, nothing is said unless there's an update.
    assert gui._offer_update(None, None, quiet=True) is False
    assert gui._offer_update(None, "Couldn't reach GitHub", quiet=True) is False
    assert shown == []
    assert gui._offer_update(None, None) is False
    assert shown[-1] == ("Check for Updates", f"You have the latest version ({gui_module.APP_VERSION}).")

    # Running from source: told to git pull.
    monkeypatch.setattr(gui_module, "FROZEN", False)
    assert gui._offer_update(release, None) is False
    assert "git pull" in shown[-1][1]

    # The .exe: asked, with the release notes; No leaves it alone.
    monkeypatch.setattr(gui_module, "FROZEN", True)
    assert gui._offer_update(release, None) is False
    assert "Version 0.2.0 is available" in asked[-1] and "New: updates." in asked[-1]


def test_the_addin_is_refreshed_once_per_version(monkeypatch):
    gui = make_test_gui()
    calls = []
    monkeypatch.setattr(gui_module, "refresh_installed", lambda: calls.append(1) or ([2025], []))

    assert gui.refresh_revit_addin() == [2025]
    assert gui._addin_setting("addin_app_version") == gui_module.APP_VERSION
    assert gui.refresh_revit_addin() == []  # already done for this version
    assert calls == [1]


def test_a_refresh_blocked_by_revit_says_so_and_tries_again_next_time(monkeypatch):
    gui = make_test_gui()
    warned = []
    monkeypatch.setattr(gui_module.messagebox, "showwarning", lambda title, message, **_kw: warned.append(message))
    monkeypatch.setattr(gui_module, "refresh_installed", lambda: ([], ["Revit 2025 is using the add-in..."]))

    gui.refresh_revit_addin()
    assert "Revit 2025 is using the add-in" in warned[0] and "Install Revit Add-in" in warned[0]
    assert gui._addin_setting("addin_app_version") is None
