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
- [x] RF Tools exports (user, 2026-11-09): `.rfps` comes from the families (one template per family,
      its own parameters); the per-schedule export is kept as `_schedules.rfps`.
- [x] Workbook mistakes corrected on import (`chat/workbook-fixes.md`).
- [x] Macro install/build works on any machine (user picks their module; .NET retarget).

## Next steps
- [x] Copy the open items from the claude.ai plan doc into this file.
- [x] Make the model the GUI's source of truth in `ddm_gui.py` (branch `gui-on-catalog`).
- [x] Switch `ddm_gui.py` saves to `Catalog.save` / `Catalog.load` (versioned JSON).
- [x] Linking by GUID instead of by name: no longer needed. In the catalog, families and
      schedules hold the parameter objects themselves, and names are only written out at save
      time, so a rename can't leave a stale reference.
- [x] Remove a parameter from a family in the GUI (Families tab, Remove Parameters From Family..., 2026-11-09).
- [x] Add parameters from the GUI (Parameter Name Builder).
- [x] Remove parameters, families and schedules from the GUI (Delete buttons on the main tabs, 2026-11-09).
- [ ] Add families from the GUI (schedules: Duplicate Schedule...).
- [x] Override Formula and Group Under (family and parameter level) in the override tables.
- [x] Team database on a new machine (user, 2026-11-20): **Database Location...** (bottom bar) sets `database_folder`
      and points the add-in at it; INSTALL.md Part 5.
- [ ] Future development (user, 2026-11-20): **multiple users with role-based access control**. For now every
      user is an admin (full edit). To settle: the roles (e.g. admin / editor / viewer, or per area: parameters,
      families, schedules, sections), where users and roles live (in the database, a separate file, or company
      sign-in via Microsoft Entra ID), and how it's enforced. A shared file on OneDrive can't stop someone saving
      over it, so real enforcement probably needs a server or database service, with the app as its client.
- [ ] Future development: **concurrent editing**. For now (user, 2026-11-20) one editor at a time, by agreement
      (INSTALL.md "One Person at a Time"). A first step: warn on Save when the file changed on disk since it was
      opened (someone else saved), offering to reload instead of overwriting; later, merging or a server.
- [ ] Future development (user, 2026-11-20): a button that draws the schedules and schedule sections as a tree,
      showing how they connect and nest: which sections each schedule uses (and its excluded columns), which
      sections include other sections, and the schedules reached through an included section. To settle: where
      the button goes (Schedule Sections tab, Schedules tab, or both), drawn in the app or exported (e.g. an HTML
      or image file), and whether clicking a node opens that schedule or section.

## Column widths from Revit (user, 2026-11-09)
- [x] `ExportScheduleWidths` macro, typical widths review.
- [ ] Parked, possible later development (user, 2026-11-10): drag a column's right edge in the Schedule Builder
      to set its width (1/16" snap, at least 1/4", columns drawn at true width). Built and tested 2026-11-09,
      then taken out; widths are typed in the Column Width row again. To bring it back:
      `git apply chat/parked/schedule-builder-drag-column-width.patch` (ddm_gui.py, its test, README).
- [ ] Needs the user, in Revit: Save (installs the macro), run ExportScheduleWidths in several projects, then
      Column Widths From Revit... and Accept. First check Revit's width for a newly added field is 1"
      (`REVIT_DEFAULT_COLUMN_WIDTH_IN` in `revit_widths.py`); if not, change it before trusting the review.
- [ ] Future development (user, 2026-11-10): remove this import/export width interface once it has done its job
      (the one-off harvest of typical widths) and two-way sync carries widths. Keep it for now. To remove:
      `ExportScheduleWidths` (shared routine and macro wrapper, `WIDTHS_EXPORT_VERSION`, `widths_folder`),
      `revit_widths.py`, `ddm_widths.py`, the Parameters tab's Column Widths From Revit... button,
      `get_revit_widths_folder`, their tests and README section. Drag to resize stays.

## Revit add-in (user, 2026-11-09), branch `revit-addin` off `dev`
A compiled C# add-in with a Design Data ribbon tab, plus the existing desktop app (which the ribbon opens).
First scope: Build Schedules, reading `<database>.schedules.json` that Save writes from `schedule_specs`, so users
no longer need a macro module, the .NET SDK or the Macro Manager. Revit 2025+, one DLL per year, installed per
user from the app (Install Revit Add-in...). Same Extensible Storage tracking schema as the macro, so it updates
the schedules the macro made. The macro stays until the user verifies the add-in in Revit.
- [x] Save writes `<database>.schedules.json` (`generate_schedule_data`) and records its path in settings.json.
- [x] `revit-addin/` project: ribbon, Build Schedules command, the routine (now shared with the macro), JSON reader.
- [x] `build_addin.py` (per installed Revit year; .NET version read from RevitAPI.dll), bundled in the `.exe`.
- [x] `revit_addin.py` install to `%APPDATA%\Autodesk\Revit\Addins\<year>`, and the GUI button.
- [ ] Needs the user, in Revit: install, Build Schedules on a project the macro built and on a new one.
- [ ] Then retire the macro; later move ExportScheduleWidths and Send into the add-in.
- [x] Coworker installs (user, 2026-11-20: coworkers use Revit 2025): 2025 builds from the `Nice3point.Revit.Api`
      2025.4.60 reference package for .NET 8, so it loads on every 2025 update (this PC's 2025.5 runs .NET 10).
- [x] **Release 0.2.0 Beta to main** (2026-11-20, user asked before their Revit retest): `main` = `dev` + one
      commit (4f70a19) setting `APP_VERSION` 0.2.0 Beta and the Linker switches off; pushed. `.exe` built with
      the **demo** database as its master (user: the release is public, so no company data in it; coworkers
      use Database Location...). Smoke-tested with a throwaway APPDATA: starts, title 0.2.0 Beta.
- [ ] User: publish GitHub release `v0.2.0` with `dist\DesignDataManager.exe` (README "Releasing an update"),
      and retest the "not a schedulable field" fix in Revit (it's in 0.2.0, untested).
- [ ] Keep `dev`'s Linker switches on: never merge `main` back into `dev` without checking them.

### Linker ID (user, 2026-11-13; built 2026-11-17)
- [x] Linker Tag Set on sections, roles and prefixes in the database, Linker Role column, `"linker"` in the
      schedules file, Assign IDs / Link Elements / Sync Linked Elements and the check on open in the add-in.
- [ ] User, in the app: tick Linker Tag Set on Equipment Tag, make a Space Tag section, add `IPS_LINKER_ID` to the
      linker families that lack it (the five `IPS-US_EQUIP_PFD Distribution - ..._2D` families don't list it,
      though their schedules have the column), set those five to Linked, and check the Linker Role column.
- [ ] User, in Revit: reinstall the add-in; Assign IDs, Link Elements on a copy and the 3D element, change a tag
      and Sync, copy-paste a primary then Assign IDs, reopen with a stale copy.
- [ ] Open: should data schedules filter to primaries only (so 3D elements and diagram copies never show in
      them)? Today the Detail Items schedules filter on `IPS_GROUP_Schedule_Name` only.
- [ ] Future development (user, 2026-11-17): link to primaries in **other models**. A linked element's
      primary isn't always in the same model: distribution diagram boxes can stand for equipment drawn in
      another model. For now their tag values are entered by hand. Later: read the primary's tag values
      from a Revit link (`RevitLinkInstance.GetLinkDocument()`, matched on `IPS_LINKER_ID`) and copy them
      as for a primary in the same model. To settle then:
      - **Telling them apart:** how to know an element's primary is in another model. Today Sync lists it as
        unlinked (no primary found); the check on open ignores those, so it doesn't nag.
      - **Unloaded links:** what to do when the link isn't loaded.
      - **Unique IDs across models:** IDs are numbered per project today, so two models can both have
        `AHU-0001`. This may need a model prefix, or numbering across models.

### Why the add-in: two-way sync (user, 2026-11-10)
Opening the app from Revit should go straight to reviewing and accepting the schedule changes made in Revit;
saving in the app should bring its changes into the open Revit project. Then the same for a folder of families.

**Phase A: two-way schedule sync** (first; verify in Revit before Phase B)
- [x] A1. Bring in the `revit-schedule-sync` work (`revit_sync.py`, the Review Revit Changes window); Send moves
      into the shared routine (`SendSchedules`), the macro keeps a thin wrapper.
- [x] A2. Remember the last sync per schedule in the project (the tracking record gets a `Synced` map: schedule
      GUID to the spec last applied or accepted). The review becomes three-way: Revit changed, Database changed,
      Both changed (choose). Schedules with no last sync fall back to a plain comparison.
- [x] A3. Opening from Revit starts the review: the ribbon's Design Data Manager button sends a snapshot of the
      project and opens (or wakes) the app on Review Revit Changes.
- [x] A4. Saving in the app reaches Revit: the add-in watches `schedules.json`; on a save, Revit asks
      "Database saved: N schedules changed" with Apply / Review / Later. Schedules the database now matches
      move their last sync up silently.
- [ ] A5. Needs the user, in Revit: width changed in Revit shows in the review; header changed in the app is
      offered on save; both sides changed asks to choose.

**Phase B: the family folder** (after A)
- [ ] B1. A Family Folder setting; families match `.rfa` files by file name; Families tab shows each file and lists
      gaps both ways.
- [ ] B2. Read families into the database: the add-in opens each `.rfa` in the background, reads its parameters
      (GUID, Instance or Type, Group Under, formula, values) and the app reviews them as links to accept.
- [ ] B3. Push the database into families: add missing shared parameters (from the shared parameter file Save
      writes), set formulas, values, Group Under and Instance or Type, save. Option, off by default: delete
      parameters not in the database. Parameters go into families, never the project.
- [ ] B4. Future development: reload changed families into projects properly, with an option to delete old
      parameters (Revit keeps parameters a family no longer has, by default) (user). Also remember the last
      sync per family, as for schedules.

## From the claude.ai plan (medium and long term)
Already done since that plan: CSV and Excel import, shared parameter file export, main-tab search,
unsaved-changes prompts.
- [ ] GUI: undo, inline error highlighting. (Add/delete is under Next steps.)
- [ ] Possible future development (user, 2026-11-05, not needed for now): a stored table view
      template, editable per user, that also remembers sort order and dragged column widths. Today
      the defaults are `DEFAULT_TABLE_VIEW` in `table_view.py`, and nothing carries over a restart.
- [ ] Richer validation: units and data types in formulas (Length × Length = Area), naming conventions
      such as the `IPS_` prefix. Circular references are done (2026-11-09).
- [ ] Low priority, possible future development (user, 2026-11-10): make the Schedule Builder match Revit's
      scale and header line breaks. Today they don't:
      - Scale: the Builder draws 72 px per inch (`OverrideTable.pixels_per_inch`), a fixed screen scale not
        tied to Revit's printed inches or screen DPI. Columns have a 110 px minimum, so columns narrower than
        about 1.5" show too wide.
      - Font: headers use the table view's heading font (Segoe UI 11 bold) and cells Segoe UI 9, screen fonts.
        Revit uses the schedule's header, body and title text types (font such as Arial, height such as
        3/32", width factor), set by the view template; the database doesn't know them.
      - Wrapping: the Builder wraps a header by word at the column width less 14 px in its font; Revit wraps at
        the width less its cell margins in the header text type, so breaks can differ at the same width.
      Possible approach: read each schedule's text types from a project through the add-in
      (`ViewSchedule.HeaderTextTypeId`, `BodyTextTypeId`, `TitleTextTypeId`: `TEXT_FONT`, `TEXT_SIZE`,
      `TEXT_WIDTH_SCALE`) and keep them in the database per view template (e.g. `IPS_Schedule_Standard`);
      draw headers and cells in that font at Revit's size (pixel size = text height × `pixels_per_inch` ÷ the
      font's cap-height ratio, width factor applied), with Revit's cell margins and minimum width; wrap like
      Revit. Check against schedule images exported from Revit (`ImageExport` or PDF) and an automated test
      of computed breaks against headers measured in Revit. Risk: Tk's and Revit's font metrics differ, so the
      realistic goal is the same breaks in the common cases, not an exact match; the font may also be missing
      where the app runs.
- [x] Recheck: demo data linking families to parameters that don't exist (`RValue`, `FinishCode`).
      Checked 2026-11-09: both are defined as parameters in `data/test_data/demo_data.ddm.csv`.
- [ ] Add missing parameters to families, not the project (design criterion, see
      [decisions.md](decisions.md)). On `2025.11.17_smart-workflow`, 576 parameters (818 columns) can't
      be scheduled, in all three Revit schedules; all 576 are in the shared parameter file. Needs
      families linked to their parameters first (under Beta).
- [ ] Add missing parameters to families, first step, waiting on the user's review:
      `schedule-family-map.xlsx` in the database folder (2026-11-06), a first-pass map of schedules to
      2D and 3D families. High-confidence rows linked 2026-11-09 (102 links); Medium (34), Low (34) and
      None (35) rows still wait on the user's review.
- [ ] Schedule sections (2026-11-06), in `dev`. In the live database since 2026-11-09 (31 sections, mostly
      unapplied; the 18 `_AHU Section (...)` schedules are sections now and deleted as schedules). Needs the
      user, in Revit: apply `Pump` to the Pump schedule, Save, run the macro, and check columns, captions and
      hidden columns. The live database is format 4: older apps, including the released `.exe`, refuse it. `Basis Of Design` is applied to all 92 schedules with
      Manufacturer and Model (user, 2026-11-09: align them all, captions included).
- [ ] Combined parameters (2026-11-09), on branch `schedule-sections`. Needs the user, in Revit: run the macro on a schedule with TAG and check its values, especially where a
      term is empty (does Revit still print the `-`?). TAG's width is the default 1 in; widen it if needed.
- [ ] Possible standardization (user, 2026-11-09, left for now): air temperature word order. `IPS_ER_*`
      puts the airstream first (`IPS_ER_Sumr_EA_EAT_DB_F`); `IPS_EnthER_*` puts entering/leaving first
      (`IPS_EnthER_Sumr_EAT_EA_DB_F`, 16 parameters, only in a section). `ER` and `EnthER` are different
      equipment, so only the order would change. Keep GUIDs when renaming (user's choice for renames).
- [ ] Future development: prefixed sections, as roles (user, 2026-11-06), so one definition covers several
      sets of the same columns on a schedule. Design from the user's reference code, where a heat pump has an
      indoor and an outdoor fan coil: a section includes another under a role, such as `Fan` as `SA`. `Electric Motor` only covers `IPS_EQUIP_Elec_*`, but 7 schedules have 2
      or more motor or electrical sets, under 15 other prefixes: `IPS_FAN_SA_*`, `IPS_FAN_EA_*`, `IPS_FAN_RA_*`,
      `IPS_PUMP_FeedWater_*`, `IPS_PUMP_SurgeTank_*`, `IPS_PUMP_Circ_*`, `IPS_PUMP_Oil_*`,
      `IPS_EQUIP_Compress_*`, the coils. Coil blocks would benefit too (`IPS_COIL_Clg_*`, `IPS_COIL_Htg_*`;
      `WATER-SIDE` has 12 uses in 11 variants). First check the names line up: they don't always, e.g.
      `IPS_FAN_SA_HP` but `IPS_PUMP_FeedWater_HP_Each`. Until then these stay ordinary columns.
      Start with fans. Name endings shared with the largest set in each group: fans fit well (`EA` 17 of 18,
      `RA` 17 of 17, against `SA`); coils partly (`Clg` 21 of 39 against `Htg`); pumps poorly (`SurgeTank` 3 of 8
      against `Oil`). Name mismatches such as `IPS_COIL_HtgElec_Current_A` against `_FLA_A` need a decision.
      A water-side section (GPM, EWT, LWT, delta T) needs roles first, since those columns sit under
      `IPS_COIL_Htg_*` and `IPS_COIL_Clg_*`.
- [ ] Later for sections: picking schedules from family links; schedule templates made of
      sections, which may not need a new feature, since a section with no caption that includes others (`Fan
      Coil Unit`: fan and coil) already works as one; a rule for Revit changes inside a section when `revit-schedule-sync` merges (a removed column
      becomes excluded; a header or order change stays local).
- [ ] Long term: push parameters into families and audit families against the catalog from Revit
      (pyRevit or an add-in); real storage (SQLite, or Quickbase as system of record) with change
      history and multi-user editing; a web UI instead of Tkinter if other people will use it.

## Lowest priority (user, 2026-11-09)
Quickbase is last on the list: develop it only after everything above.
- [ ] Working Quickbase sync: correct auth, native upsert via `mergeFieldId`, table and field IDs
      from config, a dry-run mode, tests against a mocked HTTP layer. Still wrong in
      `quickbase_integration.py`: the token goes in a `QB-USER-TOKEN` header instead of
      `Authorization` (which is only set when there's an app token), `name` maps to reserved field
      3, and `upsert_record` reads `record.get("id")`.
- [ ] "Sync to Quickbase" sends nothing, and now maps nothing either: `sync_to_quickbase` passes
      row dicts to mappers that use `getattr`, so every value comes out empty. The doc listed this
      as partly fixed (mapping model objects); the current code is back to dicts.

## Open questions
- Who uses this, and is Quickbase the system of record or a mirror? Decides storage and sync
  priority. (From the claude.ai plan, unanswered.)

## Known issues
- Families' Category 1 and 2 were filled from the workbook on 2026-11-09. The Family Name Builder now gives
  229 of 231 current names. **Rename All Families to Match** would rename the other two,
  `IPS-US_EQUIP_BoD-Office_3D` and `IPS-US_EQUIP_BoD-Warehouse_3D`, adding the `AHU` of their Category 2;
  decide whether the names or the categories are right before using it. 47 families have no Category 2,
  and 2 no Category 1,
  in the workbook either.
- On the second machine, Tk sometimes fails to start inside tests ("Can't find a usable
  tk.tcl", "couldn't read file ... panedwindow.tcl: no such file" for a file that exists), so a
  different GUI test can fail on any given run. Rerunning passes. OneDrive is not the (only) cause:
  it still happened on 2026-11-05 with the repo and `.conda` in `C:\Users\glove\gits`. Not yet
  tested: security software (CrowdStrike Falcon and Defender both run here) briefly blocking file
  opens. Creating Tk 180 times in a row didn't trigger it, so it isn't rapid startup alone. Only
  seen in test runs, not in the app. `tests/conftest.py` retries Tk's startup to work around it;
  the cause is still unknown.
