# Plan

Next steps, open questions and known issues. Tick items as they're done and move the details to
[changelog.md](changelog.md).

This file is the plan. The original claude.ai doc
(https://claude.ai/artifact/EVpeSRoyvJHmLp6cW37dtZ, last updated 2026-11-01) is now history: its
open items were copied below on 2026-11-05 and checked against the code.

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
- [x] Design (user, 2026-11-03): each database schedule makes three Revit schedules,
      `3D - {name}` (multi-category), `{name} - Working` (Detail Items, every column) and `{name}`
      (Detail Items, hidden columns hidden). All filter on `IPS_GROUP_Schedule_Name` = name.
      Re-running updates existing schedules.
- [x] Hidden column flag (`Schedule.hidden_field_names`), with a checkbox in the schedule
      window's column settings; saved in JSON and CSV.
- [x] Generator rewritten to read the `Catalog` (keeps column order); C# is a fixed routine plus
      a data table.
- [x] Save installs the macro in the `GLoveMacros` module (removing older generated copies; the
      broken `test_data.cs` is gone).
- [x] Macro didn't show in Macro Manager (2026-11-03): the module hadn't been rebuilt since
      July, and couldn't be. Revit 2025.5 (Oct 12 update) ships a Revit API built for .NET 10,
      so the module's `net8.0-windows` target fails with CS1705. Changed `GLoveMacros.csproj` to
      `net10.0-windows` on this machine (original kept as `.csproj.bak`). The second machine
      needs the same change once it has 2025.5.
- [ ] Run it in Revit 2025 on a real project and note what goes wrong (needs the user). Unverified
      until then: schedule tracking (Extensible Storage record, rename prompt, whether a
      workshared `DataStorage` owned by someone else blocks a run), header group row index (`GroupHeaders(0, ...)`, nested groups), whether
      `ClearFields` drops old header groups, multi-category schedulable fields for shared
      parameters, and `IPS_GROUP_Schedule_Name` being schedulable in each category.
- [x] CSV saves lose column order: no longer true. Checked 2026-11-05: reversing a demo schedule's
      columns with `set_field_names` survives a CSV save and reload.

## Beta (0.1.0, 2026-11-03)
- [x] Excel master workbook imported; standalone .exe built (`dist/DesignDataManager.exe`).
- [ ] Hand the .exe to testers; collect feedback.
- [ ] Link families to schedules and parameters (the workbook didn't record it); RF Tools
      export is empty until families have parameters.
- [x] Workbook mistakes corrected on import (`chat/workbook-fixes.md`).
- [x] Macro install/build works on any machine (user picks their module; .NET retarget).

## Next steps
- [x] Copy the open items from the claude.ai plan doc into this file.
- [x] Make the model the GUI's source of truth in `ddm_gui.py` (branch `gui-on-catalog`).
- [x] Switch `ddm_gui.py` saves to `Catalog.save` / `Catalog.load` (versioned JSON).
- [x] Linking by GUID instead of by name: no longer needed. In the catalog, families and
      schedules hold the parameter objects themselves, and names are only written out at save
      time, so a rename can't leave a stale reference.
- [ ] Remove a parameter from a family in the GUI (adding works from the schedule table).
- [x] Add parameters from the GUI (Parameter Name Builder).
- [ ] Remove parameters; add and remove families and schedules from the GUI.
- [x] Override Formula and Group Under (family and parameter level) in the override tables.

## From the claude.ai plan (medium and long term)
Already done since that plan: CSV and Excel import, shared parameter file export, main-tab search,
unsaved-changes prompts.
- [ ] Working Quickbase sync: correct auth, native upsert via `mergeFieldId`, table and field IDs
      from config, a dry-run mode, tests against a mocked HTTP layer. Still wrong in
      `quickbase_integration.py`: the token goes in a `QB-USER-TOKEN` header instead of
      `Authorization` (which is only set when there's an app token), `name` maps to reserved field
      3, and `upsert_record` reads `record.get("id")`.
- [ ] "Sync to Quickbase" sends nothing, and now maps nothing either: `sync_to_quickbase` passes
      row dicts to mappers that use `getattr`, so every value comes out empty. The doc listed this
      as partly fixed (mapping model objects); the current code is back to dicts.
- [ ] GUI: undo, inline error highlighting. (Add/delete is under Next steps.)
- [ ] Possible future development (user, 2026-11-05, not needed for now): a stored table view
      template, editable per user, that also remembers sort order and dragged column widths. Today
      the defaults are `DEFAULT_TABLE_VIEW` in `table_view.py`, and nothing carries over a restart.
- [ ] Richer validation: units and data types in formulas (Length × Length = Area), circular
      references, naming conventions such as the `IPS_` prefix.
- [ ] Recheck: demo data linking families to parameters that don't exist (`RValue`, `FinishCode`).
- [ ] Add missing parameters to families, not the project (design criterion, see
      [decisions.md](decisions.md)). On `2025.11.17_smart-workflow`, 576 parameters (818 columns) can't
      be scheduled, in all three Revit schedules; all 576 are in the shared parameter file. Needs
      families linked to their parameters first (under Beta).
- [ ] Long term: push parameters into families and audit families against the catalog from Revit
      (pyRevit or an add-in); real storage (SQLite, or Quickbase as system of record) with change
      history and multi-user editing; a web UI instead of Tkinter if other people will use it.

## Open questions
- Who uses this, and is Quickbase the system of record or a mirror? Decides storage and sync
  priority. (From the claude.ai plan, unanswered.)
- Changing a parameter's data type silently assigns a new GUID (model behaviour, since Revit
  ties a shared parameter's GUID to its type). Should the GUI warn first, like it does for a
  rename?

## Known issues
- The working database's families have no Category 1, Category 2 or their codes (0 of 231; the database
  was imported before the import read them). The Family Name Builder therefore builds a shortened
  name for 230 of 231 families, e.g. `IPS-US_Pilot Light` for `IPS-US_CTRL_Device_Pilot Light_2D`, and
  **Rename All Families to Match** would shorten them all. Fill them from the workbook first,
  without renaming, as was done for the parameter name terms.
- On the second machine, Tk sometimes fails to start inside tests ("Can't find a usable
  tk.tcl", "couldn't read file ... panedwindow.tcl: no such file" for a file that exists), so a
  different GUI test can fail on any given run. Rerunning passes. OneDrive is not the (only) cause:
  it still happened on 2026-11-05 with the repo and `.conda` in `C:\Users\glove\gits`. Not yet
  tested: security software (CrowdStrike Falcon and Defender both run here) briefly blocking file
  opens. Creating Tk 180 times in a row didn't trigger it, so it isn't rapid startup alone. Only
  seen in test runs, not in the app. `tests/conftest.py` retries Tk's startup to work around it;
  the cause is still unknown.
