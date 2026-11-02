# Plan

Next steps, open questions and known issues. Tick items as they're done and move the details to
[changelog.md](changelog.md).

The original living plan is a claude.ai doc: https://claude.ai/artifact/EVpeSRoyvJHmLp6cW37dtZ.
Its checklist hasn't been copied here yet (the second machine can't open it). Next session on the
first machine: copy its open items into this file, then treat this file as the plan.

## Next steps
- [ ] Copy the open items from the claude.ai plan doc into this file.
- [x] Make the model the GUI's source of truth in `ddm_gui.py` (branch `gui-on-catalog`).
- [x] Switch `ddm_gui.py` saves to `Catalog.save` / `Catalog.load` (versioned JSON).
- [x] Linking by GUID instead of by name: no longer needed. In the catalog, families and
      schedules hold the parameter objects themselves, and names are only written out at save
      time, so a rename can't leave a stale reference.
- [ ] Remove a parameter from a family in the GUI (adding works from the schedule table).
- [ ] Add and remove parameters, families and schedules from the GUI (today the GUI only edits
      what a loaded file contains), and pick a schedule's families and columns.
- [x] Override Formula and Group Under (family and parameter level) in the override tables.

## Open questions
- Changing a parameter's data type silently assigns a new GUID (model behaviour, since Revit
  ties a shared parameter's GUID to its type). Should the GUI warn first, like it does for a
  rename?

## Known issues
- `tests/test_ddm_gui.py::test_main_tab_table_headings_wrap_after_column_resize` fails (heading
  padding assertion). Pre-existing on `dev`.
- On the second machine, Tk sometimes fails to start inside tests ("Can't find a usable
  tk.tcl", "couldn't read file ... auto.tcl: no such file" for a file that exists), so a
  different GUI test can fail on any given run. Rerunning passes. Suspected cause: the `.conda`
  environment sits inside the OneDrive folder, and OneDrive sync makes reads fail now and then.
  Worth trying an environment outside OneDrive.
