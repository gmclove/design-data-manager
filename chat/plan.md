# Plan

Next steps, open questions and known issues. Tick items as they're done and move the details to
[changelog.md](changelog.md).

The original living plan is a claude.ai doc: https://claude.ai/artifact/EVpeSRoyvJHmLp6cW37dtZ.
Its checklist hasn't been copied here yet (the second machine can't open it). Next session on the
first machine: copy its open items into this file, then treat this file as the plan.

## Top priority: a working Revit schedule macro (user, 2026-11-02)
Goal: Save in the GUI, run `CreateSchedulesFromDatabase` in Revit, and get the schedules the
database describes. The macro lives in the Revit 2025 application module `GLoveMacros`
(`C:\ProgramData\Autodesk\Revit\Macros\2025\Revit\AppHookup\GLoveMacros\Source\GLoveMacros`,
.NET 8, nullable on). The GUI writes it as `<database>.cs` next to the save.
- [x] Fix the compile error: `SchedulableField.GetName` needs the document. Every generated
      macro failed to build before this.
- [x] Test that builds the demo macro against the installed Revit API (`tests/
      test_revit_schedule_macro_generator.py`, marked `slow`, skipped without Revit 2025+ and the
      .NET SDK). Revit 2025.5's API needs a .NET 10 SDK to build outside Revit; the test uses the
      newest SDK installed.
- [ ] Run it in Revit 2025 on a real project and note what goes wrong (needs the user).
- [ ] Get the macro into the module without copying by hand (the module folder holds an old,
      broken `test_data.cs` from 2026-10-21 that must be replaced or removed).
- [ ] Restrict each schedule to its own families. Today a schedule lists every element of its
      category.
- [ ] Multi-category schedules (today a schedule whose families span categories is skipped).
- [ ] Header groups (`ViewSchedule.GroupHeaders`); today they're ignored.
- [ ] Re-running when a schedule already exists: today it's skipped; update it instead?
- [ ] Find categories by `BuiltInCategory`, not display name, so non-English Revit works.
- [ ] Generate from the `Catalog` (schedule `field_names` order) instead of the GUI's tables.

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
