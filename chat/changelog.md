# Changelog

Newest first. One entry per piece of work; link commits where useful.

## 2026-11-05: Parameter Name Builder
- The master workbook's Parameter Name Editor as five terms on `Param`: `IPS_` + Parent Category
  `_` Child Category `_` Descriptor + Clarifier `_` Units (`build_param_name`). Saved in JSON
  (`name_terms`, version unchanged) and CSV; Import Excel reads them.
- One click on a Name on the Parameters tab opens the builder; **Add Parameter...** opens it to add
  a parameter. Dropdowns for Parent Category, Child Category and Units; 30 character warning.
- Recorded the terms in the working database (`excel_import.read_name_terms`, one-time): 1,242
  from the workbook, and the user confirmed the guesses for the 3 parameters it doesn't have. Names
  and GUIDs unchanged, checked by comparing the saved JSON and CSV with the old data; backups are
  `database.before-name-terms.ddm.*` in `ddm-data`.
- Renamed `IPS_SPACE_AirReq_DuctLeak _PRCNT` to `IPS_SPACE_AirReq_DuctLeak_PRCNT` (stray space),
  keeping its GUID; Import Excel corrects it too (`PARAMETER_RENAMES`). Backups are
  `database.before-ductleak-fix.ddm.*`. The `.txt`, `.rfps` and `.cs` in `ddm-data` still have the
  old name until the next Save in the GUI.

## 2026-11-05: Plan consolidated; heading test fixed
- Copied the claude.ai plan's open items into `plan.md`, checked against the code. `plan.md` is now
  the only plan.
- `test_main_tab_table_headings_wrap_after_column_resize` fixed; the app was right. Bottom padding
  has to grow for wrapped headings (at 2 px the first row sits under a 5-line heading), and the
  test's 800 px window squeezed the third of its stacked tables.

## 2026-11-05: Repo off OneDrive; database folder setting
- `config/app_paths.py`: `USER_SETTINGS_PATH` moved here; `DATA_DIR` follows the user's
  `database_folder` setting when set. The repo moved to `C:\Users\glove\gits`, the database to
  OneDrive `_PARAMETERS\ddm-data`.

## 2026-11-04: Schedule window: one-click editing, bold used values, Add All Parameters
- `OverrideTable(edit_on_click=True)` in the schedule window: one click edits any editable cell
  (a Name click also selects the column); every value cell is white.
- A family's Default Formula / Group Under are editable from a schedule (set the family's own).
- Bold marks the value the schedule uses (`_value_source`: schedule / family / parameter).
- "Add All Parameters" button under each family name (while it lacks a column); section label
  column is 150 px.

## 2026-11-04: Default terms in labels
- Parameters tab: Default Header, Default Column Width (in), Default Group Under, Default Formula,
  Instance or Type (shown and edited as Instance / Type; `parse_bool` also reads instance / type).
- Override table rows: Default Formula, Default Group Under (label column 140 px).

## 2026-11-04: Unsaved changes warning
- Close, Load and Import Excel... offer Save / Discard / Cancel when the catalog differs from the
  last load or save (a JSON snapshot of `Catalog.to_dict()`; ~20 ms on the master database).
  Closing mid-build waits for the macro build to finish.

## 2026-11-04: Families: Category 1/2, category codes, Family Name Builder
- New Families columns before Description: Category Code, Category 1, Category 1 Code,
  Category 2, Category 2 Code. Category 1/2 are Add New... lists with unique codes; Category Code
  is per Revit category (2D / 3D / blank, shared). `CODE_KINDS` / `CODED_KINDS` / `CODE_LABELS`.
- Family Name Builder (one click on a Name): terms with Use / Prefix / Suffix / order, shared
  `Catalog.family_name_format`; prefixes act as separators (none on the first term). Rename This
  Family, Rename All Families to Match (skips blank and clashing names). No family double-click.
- Excel import reads Family Category 1/2 (+ famCat1 / FamCat2 code tables) and derives each Revit
  category's code from its families' Revit View (one view: its code; mixed: blank). Applied to
  `data/database.ddm.json` (backup `database.before-family-naming.ddm.json`); 229 of 231 imported
  names match the default format (2 workbook names lack their AHU term).

## 2026-11-04: Schedule macro asks what to build
- Save writes the CSV, `.rfps` and shared parameters first, then the macro; the module build runs
  on a background thread (Tk polled with `after`), and a save made mid-build is queued.
- Schedule window: Parameter section cells edit the parameter itself (name with GUID prompt,
  Default Header, Default Value, Formula, Group Under, Instance or Type).
- Schedule window: Default Header row in the Parameter section (the parameter's header text; gray
  when it's just the name).
- `CreateSchedulesFromDatabase` opens a Windows Forms dialog: Rebuild All Schedules or Rebuild
  Selected Schedules (searchable checklist, Select All / Clear, ✓ for schedules already in the
  project) and Override Existing Schedules With the Same Name (on by default; off leaves
  existing Revit schedules alone and lists them in the summary).
- `build_module` turns on `<UseWindowsForms>` in the module's .csproj once (removing the
  System.Windows.Forms / System.Drawing global usings so `View` etc. don't clash), with `.bak`.
  The macro uses `WinForms` / `Drawing` aliases. Compile test covers it against the Revit API.

## 2026-11-04: Search, schedule families, header groups from merged cells
- Search box on each main tab (every word must match, any column). Rows keep their position in
  the full table as their Treeview ID, so edits and windows reach the right item while filtered.
- Schedule window: Add Parameter..., Remove Parameter, Add Family..., Remove Family under the
  table. Column headers and parameter Name cells select columns; family labels select families
  (Ctrl/Shift). Pickers are searchable and multi-select; new columns go after the selected one.
  Model: `Schedule.add_columns(names, after=)` / `remove_columns(names)`.
- The schedule window's title is the schedule's name, editable (rename reopens the window).
- The All Families section is now titled Apply to All Families, and has Formula and Group Under rows too. They set each family's Family Default
  (Revit keeps them in the family, so every schedule the family is in sees it); Default Value
  still sets each family's Schedule Default Value.
- Instance or Type row (Instance/Type drop-down) under Parameter, Apply to All Families and each
  family; in a schedule it sets the family's own (family-level) setting. The `.rfps` export now
  uses each family's own Instance or Type, Default Value, Formula and Group Under (it used the
  parameter's before), and CSV link rows carry the family's overrides (they were lost before).
- ◀ Move Left / Move Right ▶ reorder the selected columns (`Schedule.move_columns`; refuses to
  split a header group). The schedule window reopens in place: same size, scroll and selection.
- Excel import: a merged caption spans its merged cells (borders inside merges had cut 103 spans
  short or let them run on); plain (not bold) text among the captions is a note, not a group.
  Applied to `data/database.ddm.json` (header groups only; 17 schedules; 698 groups); the prior
  copy is `data/database.before-header-groups.ddm.json`.

## 2026-11-03: Revit macro install and build work on any machine
- `revit_macro_module.py`: finds every Revit 2025+ application macro module under
  `%ProgramData%\Autodesk\Revit\Macros`, reads its namespace, remembers each user's choice in
  `%APPDATA%\DesignDataManager\settings.json`, and builds it. CS1705 (module's .NET older than
  Revit's API) retargets the .csproj (keeping `.csproj.bak`) and rebuilds; a missing SDK is
  explained with the download link.
- The macro is generated in the chosen module's namespace (no more hard-coded GLoveMacros). One
  module: used automatically. Several: Save asks once; **Revit Macro Settings** changes it. None:
  Messages says how to create one.
- Tested the retarget against a real .NET 8 copy of GLoveMacros (CS1705 -> net10 -> builds).

## 2026-11-03: Workbook mistakes corrected on import
- 35 corrections in `excel_import.py` (see `chat/workbook-fixes.md`): 16 stray
  `IPS_SPACE_AirReq_Recirc` columns, 10 columns naming nonexistent parameters, 3 new parameters,
  the `IPS_ROOM_Transfer` formula, the `IPS-US_CTRL` placeholder family. Export leftover columns
  (Name/NAME/Column1) are skipped quietly. Parameters defined from schedule rows get stable GUIDs.
- Formula checker: Revit lengths (`0' 0 1/16"`) are numbers; Revit's built-in `Length` is known.
- Re-imported and saved: 1245 parameters, 231 families, 5768 columns; no formula errors left.

## 2026-11-03: 0.1.0 Beta standalone .exe
- `build_exe.py` (PyInstaller, one file, windowed): bundles the master database as
  `master.ddm.json`, opened on first launch; working data goes to `data/` next to the .exe
  (`config/app_paths.py`: FROZEN, BUNDLE_DIR, STARTER_DATABASE_PATH, APP_VERSION).
- Built from a pip venv in `%LOCALAPPDATA%\ddm-build\venv` (conda's MKL numpy made a 231 MB,
  26 s-startup .exe; pip's gives 37 MB, ~10 s). The build puts the conda `Libraryin` on PATH
  so Tcl/Tk and libffi DLLs get bundled.
- Window title shows the version; first launch says where Save will keep the database.

## 2026-11-03: Excel master workbook import
- `excel_import.py` + **Import Excel...** button: Parameters sheet, Families sheet (codes from
  the abbreviations) and every schedule sheet after Backstage (columns, stacked headings, header
  groups from caption spans, "Hidden ..." columns, itemize, view template; filters blank).
- Schedules can stand alone: with chosen columns, a schedule's parameters can come from the
  catalog without families. CSV gains `schedule_column` records that keep column order (CSV
  loads no longer sort columns).
- A family with no parameters is a Warning, not an Error.
- Imported the real workbook (1242 parameters, 232 families, 130 schedules / 5757 columns,
  2279 hidden, 710 header groups, 40 report lines) into `data/database.ddm.json`; the demo-based
  database was kept as `data/database.before-import.*`. The macro for all 130 schedules builds.

## 2026-11-03: Save builds the macro module
- After installing the macro, Save runs `dotnet build` in the GLoveMacros module
  (`build_macro_module`) and lists the build's errors, warnings and a summary in Messages, so
  Macro Manager shows the new macro without opening VS Code. A failed build also pops up a
  "Macro Build Failed" error listing up to 10 of its errors.

## 2026-11-03: Schedule settings: filter, itemize, view template
- `Schedule.filter_value` (blank means the schedule's name) overrides `IPS_GROUP_Schedule_Name`
  for every family in the schedule (`resolved_family_params`) and is what the macro filters on.
- `Schedule.itemize` (default true) sets Revit's "Itemize every instance".
- `Schedule.view_template`: a Revit schedule view template name, applied to all three Revit
  schedules after they're built (the macro clears it first so it can rebuild fields).
- Schedule window: Schedule Settings box above the table. Saved in JSON and as CSV columns
  `schedule_filter`, `itemize`, `view_template` on schedule entry rows.

## 2026-11-03: Revit schedule macro working (top priority)
- Fixed the compile error that stopped every generated macro building (`SchedulableField.GetName`
  needs the document). A test now builds the macro against the installed Revit 2025 API.
- Each database schedule makes `3D - {name}` (multi-category), `{name} - Working` and `{name}`
  (Detail Items), filtered on `IPS_GROUP_Schedule_Name`; re-running updates them. Header groups
  are applied; missing parameters are reported instead of failing the schedule.
- Hidden columns: `Schedule.hidden_field_names`, a "Hidden Column" row of checkboxes under the
  column headers in the schedule window (one click toggles), also in the column settings
  dialog; saved in JSON and the CSV `hidden` column.
- Save installs `CreateSchedulesFromDatabase.cs` in the GLoveMacros module and removes older
  generated copies. Tests redirect the module folder (`tests/conftest.py`).

## 2026-11-02: Client and country dropdowns and codes
- Client and Country are dropdowns (main Families list and family window) with "Add New...",
  which asks for a name and code.
- New Client Code and Country Code columns. Codes live on the catalog (`Catalog.codes`, one per
  client/country, unique per kind); `Fam.client_code` / `country_code` look them up. Editing a code
  on one family changes it for all families with that client/country.
- Saved in JSON as `clients` / `countries` (format stays version 3; older files load with no
  codes) and in the CSV as family-row columns. Conflicting codes in a CSV are reported on load.

## 2026-11-02: Override Rules info button
- Family window, schedule window and the "where else" override prompt have an
  "ⓘ Override Rules" button that opens a read-only explanation of the override logic
  (`OVERRIDE_RULES` in `ddm_gui.py`). README has a matching "Overriding Default Values" section;
  keep the two in step.

## 2026-11-01: GUI on the catalog, override prompt (branch `gui-on-catalog`)
- Model: schedules pick their columns (`field_names`) and hold per-family value overrides that
  apply in that schedule only; `Catalog.apply_override` / `resolved_value`. Catalog format version 3 (version 2 still loads).
- `ddm_gui.py` holds a `Catalog`; its tables are views and edits go through the model. Saves are
  JSON (`data/database.ddm.json`) plus readable CSV and Revit exports; CSV and older `.ddm.pkl`
  files still load.
- New `ddm_tables.py`: catalog <-> tables, with load problems fixed or skipped and reported.
- Family and schedule detail windows list parameter values; double-click to override. The
  override dialog offers a multi-select of the connected families (from a schedule) or schedules
  (from a family) plus a checkbox to make it the parameter's default.
- Demo database fixed: nine parameters it linked were never defined, and its override values sat
  in the `caption` column so they never loaded.
- Stray labels the family window used to add to the main window are gone.
- Family and schedule windows show one override table each (user's mockup): header groups and
  column headers, Parameter block, one block per family, for Default Value, Formula and Group
  Under. Formula and Group Under are family-level only; schedules show them read-only. Family
  formula overrides are now validated and follow renames.
- Table cells are edited in place (no value pop-up). A family missing a schedule column shows an
  "Add Parameter to Family" button there.
- Schedule table All Families row sets every family's Schedule Default Value at once.
- Main Families and Parameters lists: one click edits the cell in place (Enter or clicking away
  saves, Escape cancels; dropdown columns open a dropdown); a double-click opens the family window
  (Families) or the edit pop-up (Parameters).

## 2026-11-01: Housekeeping
- GUI default save moved from the tracked fixture `data/test_data/test_data.ddm.pkl` to untracked
  `data/database.ddm.pkl`, so saving no longer rewrites test fixtures (the save also writes CSV,
  `.cs`, `.rfps` and `.txt` siblings).
- `.gitattributes` added (`* text=auto`; `.pkl` and the UTF-16 shared-parameter fixture binary).
- All tests moved into `tests/` (`ddm_gui_test.py` is now `tests/test_ddm_gui.py`); `pytest.ini`
  removed, config lives in `pyproject.toml`.
- README: correct conda env name, list the export modules, `tests/`, `data/` and `chat/`.
- `parameter_model_overview.md`: GUI section covers stored GUIDs and rename reference updates.
- Second machine's git identity set to gmclove (repo-local).

## 2026-11-01: AI notes moved to `chat/` folder
- `chat.md` split into `chat/handoff.md`, `plan.md`, `decisions.md` and this changelog, with a
  README explaining how to use them. The plan moved here because the second machine can't open
  the claude.ai plan doc.

## 2026-11-01: Second machine synced
- Local `dev` and `main` fast-forwarded to origin; `dev` and `main` identical at `c927e03`.
  112 tests pass, 1 known failure.

## 2026-11-01: Rename updates every reference (`af1b348`)
- Renaming a parameter in `ddm_gui.py` rewrites the old name in family links, schedule entries,
  schedule header groups and formulas. Header text at its default follows; custom header text is
  kept. Renaming onto a name that's already in use is blocked.

## 2026-11-01: Stored parameter GUIDs and rename prompt (`877a149`)
- `guid` column on parameters, saved with the data and read-only in the GUI. Blank GUIDs default
  to the name-based GUID exports already used.
- Shared-parameter and RF Tools exporters use the stored GUID.
- Rename asks: new GUID (default), keep current GUID, or cancel.

## 2026-11-01: `catalog-model` merged into `dev` (`5a131e9`, merged in `31e7a19`)
- Formula tokenizer and syntax checks (`formula.py`).
- `Catalog` object replaces the global registries; `FamType` no longer adds the common
  `IPS_GROUP_*` params twice.
- JSON `Catalog.save` / `load`; pickle-based state and `picklePath.py` removed.

## 2026-11-01: `foundation-cleanup` merged into `dev` (`687c571`)
- Combined the foundation cleanup (`formula.py`, `rename(keep_guid=...)`, GUID warning,
  `pyproject.toml`, `tests/test_model.py`, rename to `revit_parameter_manager.py`) with the second
  machine's rework (`ddm_gui.py` replacing `parameter_catalog_gui.py`, Revit export tools,
  `config/*_definitions.py`, schedule header groups and column widths).

## 2026-09-22: Initial parameter catalog project (`bffb7f1`)
