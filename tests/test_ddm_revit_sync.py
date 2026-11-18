"""The Review Revit Changes window (ddm_revit_sync.py)."""

import json
import tkinter as tk
from tkinter import ttk

import ddm_gui as gui_module
from config import app_paths
from ddm_gui import DDMGUI
from revit_schedule_macro_generator import schedule_specs
from test_ddm_gui import descendants, find_button
def test_review_revit_changes_shows_values_side_by_side_and_accepts_only_the_checked_ones(tmp_path, monkeypatch):
    infos = []
    monkeypatch.setattr(gui_module.messagebox, "showinfo", lambda *args, **kwargs: infos.append(args))
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DDMGUI(root)
        gui.checkpoint_path = tmp_path / "database.ddm.json"
        gui._mark_saved()
        # Nothing sent yet.
        assert gui.open_revit_changes() is None
        assert "Nothing has been sent" in infos[-1][1]

        schedule = gui.catalog.schedules[0]
        spec = next(spec for spec in schedule_specs(gui.catalog)[0] if spec["guid"] == schedule.guid)
        columns = [
            {"parameter": item["parameter"], "heading": item["header"], "width_feet": item["width_feet"], "hidden": item["hidden"]}
            for item in spec["columns"]
        ]
        sent = {
            "guid": schedule.guid, "role": "Finished", "name": spec["name"], "itemize": spec["itemize"],
            "columns": columns, "unavailable": [],
        }
        path = app_paths.get_revit_sync_path(gui.checkpoint_path)
        data = {"version": 1, "project": "Test", "sent_at": "now", "schedules": [sent], "unlinked": ["Other"]}
        path.write_text(json.dumps(data), encoding="utf-8")
        # Sent exactly as the database has it, other than the unlinked schedule: nothing to accept.
        window = gui.open_revit_changes()
        assert window.checks == []
        assert list(window.information.values()) == [["Other"]]
        assert str(find_button(window, "Select All").cget("state")) == "disabled"
        window.destroy()

        columns[0]["heading"] = "From Revit"
        sent["itemize"] = not spec["itemize"]
        path.write_text(json.dumps(data), encoding="utf-8")
        window = gui.open_revit_changes()
        root.update()
        checks = {difference.kind: var for difference, var in window.checks}
        assert set(checks) == {"heading", "itemize"}
        # The values show side by side.
        shown = [widget.cget("text") for widget in descendants(window) if isinstance(widget, tk.Label)]
        assert {"Database Value", "Revit Value", "From Revit", spec["columns"][0]["header"]} <= set(shown)

        # Nothing is selected to start with, so there's nothing to accept.
        accept = next(
            widget for widget in descendants(window)
            if isinstance(widget, ttk.Button) and widget.cget("text").startswith("Accept Selected")
        )
        assert accept.cget("text") == "Accept Selected (0)"
        assert str(accept.cget("state")) == "disabled"
        find_button(window, "Select All").invoke()
        assert accept.cget("text") == "Accept Selected (2)"
        assert all(var.get() for var in checks.values())
        find_button(window, "Deselect All").invoke()
        assert accept.cget("text") == "Accept Selected (0)"
        assert not any(var.get() for var in checks.values())

        checks["heading"].set(True)
        assert accept.cget("text") == "Accept Selected (1)"
        accept.invoke()

        assert schedule.header_text_overrides[columns[0]["parameter"]] == "From Revit"
        assert schedule.itemize == spec["itemize"]
        assert gui.has_unsaved_changes()
    finally:
        root.destroy()



def test_revit_asking_for_a_review_opens_it_once_per_snapshot(tmp_path, monkeypatch):
    from test_ddm_gui import make_test_gui

    gui = make_test_gui()
    gui.checkpoint_path = tmp_path / "database.ddm.json"
    opened = []
    monkeypatch.setattr(gui, "open_revit_changes", lambda: opened.append(True))
    path = app_paths.get_revit_sync_path(gui.checkpoint_path)

    def send(sent_at, review=True):
        data = {"version": 1, "project": "P", "sent_at": sent_at, "review": review, "schedules": [], "unlinked": []}
        path.write_text(json.dumps(data), encoding="utf-8")
        gui._revit_snapshot_seen = None  # as if the file changed

    assert gui.check_revit_review_request() is False  # nothing sent yet
    send("2026-11-10 09:00:00")
    assert gui.check_revit_review_request() is True
    send("2026-11-10 09:00:00")
    assert gui.check_revit_review_request() is False  # already reviewed, even after a restart
    send("2026-11-10 09:05:00", review=False)
    assert gui.check_revit_review_request() is False  # a plain send doesn't open the review
    send("2026-11-10 09:10:00")
    assert gui.check_revit_review_request() is True
    assert len(opened) == 2
