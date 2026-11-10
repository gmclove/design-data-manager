# Changelog

Newest first. One entry per piece of work; link commits where useful.

## 2026-11-09: Column widths from Revit, drag to resize
- `ExportScheduleWidths` in the generated macro: writes every non-DDM schedule's column widths (with shared
  parameter GUIDs) to `revit-widths/<project>.widths.json` next to the database. Builds against Revit 2025.
- `revit_widths.py`: reads the exports, finds each parameter's typical width, applies chosen ones.
- Parameters tab, Column Widths From Revit...: review with Accept checkboxes (`ddm_widths.py`).
- Schedule Builder: drag a column's right edge to set its width (1/16" snap); columns drawn at true width.
- The Sections tab is now Schedule Sections (user).

## 2026-11-09: Delete buttons, formula loops, data type warning, family categories
- Delete Parameters..., Delete Families..., Remove Parameters From Family... and Delete Schedules... on the
  main tabs, each asking first with what it affects (see README, Deleting).
- Formula loops: the Formula Builder refuses a formula that makes a loop, and family validation flags
  one (`find_formula_loop` in `revit_parameter_manager.py`). The live database has none.
- Changing a parameter's data type asks first, since it assigns a new GUID.
- Live database (user, 2026-11-09):
  - `HUM` on the steam humidifier's `IPS_TAG_EquipID_Abbrev` is now the family's Default Value, not a
    formula; the family also gets `IPS_TAG_EquipID_Seq_ALPH`, which its tag suffix formula uses and the
    other 9 families with that suffix have. No schedule is in error now.
  - `Basis Of Design` applied to all 92 schedules with Manufacturer and Model. No columns moved; 13 title
    or `HOUSING` captions no longer span the two columns, and 2 schedules lost separate `MANUF.`/`MODEL`
    captions to the section's.
  - Category 1 and 2 filled for every family from the master workbook (413 values, 54 codes including the
    Revit categories' 2D/3D), without renaming. The Family Name Builder now gives 229 of 231 current names;
    the other two, `IPS-US_EQUIP_BoD-Office_3D` and `IPS-US_EQUIP_BoD-Warehouse_3D`, lack the `AHU` of their
    Category 2.
  - Linked the High-confidence rows of `schedule-family-map.xlsx` (user): 102 new schedule-family links, 10
    already there; 51 of 113 schedules now have families. Skipped the 14 `_AHU Section (...)` rows (sections
    now, not schedules). No columns or statuses changed. Medium, Low and None rows wait on the user's review.
  - Families tab: a read-only Schedules column lists the schedules each family is on.
  - Every `database.before-*` backup in `ddm-data` (24 files, 2026-11-03 to 11-09) deleted at the user's
    request; the backups named in this changelog no longer exist (OneDrive's recycle bin may still have them).

## 2026-11-09: Live database parameter cleanup
- Deleted unused duplicates `IPS_EQUIP_Air_Capacity_Max_CFM` / `_Min_CFM` (kept `CapacityMax`/`CapacityMin`).
- Merged `IPS_COIL_Htg_MaxPD_FT_WC`/`_IN_WC` into `IPS_COIL_Htg_PDMax_*` (Text; headers as the cooling
  coil's); schedules and sections keep their column places.
- Renamed, GUIDs kept: `*_Load_SidePD_*`/`*_LoadSidePD_*` -> `*_LoadSide_PD_*`, `IPS_COIL_Htg_SourceSidePD_FT_WC`
  -> `_SourceSide_PD_`, `IPS_HX_EA_PD_Max_IN_WC` -> `IPS_HX_EA_PDMax_IN_WC`, `IPS_FILTER_PD_DirtyMax_IN_WC`
  -> `IPS_FILTER_PDDirtyMax_IN_WC`. Name Builder terms set to match.
- Backups in `ddm-data`: `database.before-capacity-dedupe`, `.before-dedupe-merge`, `.before-pd-renames`.

## 2026-11-09: Schedule Builder tools and RF Tools exports
- Ungroup Selected Headers in the Schedule Builder; the header group buttons sit above the table
  in the Schedule Builder and section windows, and both windows open wide enough for every button.
- Schedule Builder, family and section tables: the label columns and header rows are frozen while scrolling.
- Scrolling and copy/paste (user, 2026-11-09): one app-wide mouse-wheel handler scrolls the canvas
  under the pointer (grids, checkbox lists; Shift for sideways); Ctrl+C/Ctrl+V and a right-click menu
  in the grids and main tables (`ddm_clipboard.py`); pasting into an empty box no longer pastes into
  its gray hint, which had made the paste save nothing.
- Formula Builder (first pass, user, 2026-11-09): opens wherever a formula is entered, checks as
  you type with `Catalog.formula_issues`, and only saves a valid formula. Lists parameters (the
  family's own in a family row) and functions to insert. `ROUNDUP`/`ROUNDDOWN` added to the known
  functions. Of the live database's 68 formulas, only `HUM` on the steam humidifier's
  `IPS_TAG_EquipID_Abbrev` fails it.
- Schedule Builder and section windows open tall enough for their buttons (capped to the screen),
  with Close and the button row laid out first; fixes the width fit, which read Tk's 1x1 size
  before the window showed and could open it far too short.
- Duplicate Schedule... on the Schedules tab: a full copy with its own GUID, right after the original.
- Save writes two RF Tools files: `.rfps` (one template per family) and `_schedules.rfps` (one
  template per schedule, with each parameter's own settings). Combined parameters are left out.
- RF Tools exports fixed: values are written as they are (CSV quoting had wrapped formulas in quotes
  and doubled theirs, breaking `IPS__PHASE_Classification`), and Group Under is RF Tools' code, the
  Revit 2025 GroupTypeId name in capitals (`Mechanical - Flow` -> `MECHANICALAIRFLOW`,
  `Dimensions` -> `GEOMETRY`). Codes inferred from the user's example and RevitAPI.xml; not yet
  checked against a file RF Tools made.

## 2026-11-09: Section window like the Schedule Builder, with header groups
- Sections hold header groups besides the one over all columns, nested inside it; saved in JSON and CSV.
- The section window shows the Schedule Builder's grid (Group Level rows, headers, Hidden Column, an
  Included From row, the parameters' defaults) with Group Selected Headers and Ungroup Selected Headers.
- Test copy: the AHU sections got back 77 header groups from their old schedules, such as `MOTOR DATA`
  inside `SUPPLY FAN`; 5 old title groups that the new caption replaces were left out.

## 2026-11-09: Combined parameters
- A combined parameter is one schedule column joining several parameters, as Revit's combined
  parameters do (`ScheduleDefinition.InsertCombinedParameterField`). It's a column only: no family
  holds it and it isn't in the shared parameter file.
- Combined Parameters tab and window (name, header, width, parts with prefix, suffix and separator);
  Add Parameter... in the Schedule Builder and in sections offers them; the Schedule Builder shows the
  pattern and each family's resulting value. Saved in the JSON (format 4) and the CSV (`combined_param`).
- The macro builds combined columns; it compiles against Revit 2025. Not yet run in Revit.
- Test copy: `TAG` (terms 1 to 5, `-` before terms 2 and 4) is first in `Equipment Tag` and on the 100
  schedules with all five terms, just before their tag columns.

## 2026-11-06: Schedule sections
- A section is a standard block of columns that schedules link to; changing it changes them all.
- A section can include other sections: `Pump` includes `Electric Motor`, which includes `Electrical
  Data`. A change flows up through every level, and the outermost caption wins.
- Sections tab, section window with a schedule picker, a side by side preview with an accept check for
  each schedule, and Add Section... in the Schedule Builder.
- Catalog format 4; version 3 files still load, but an older app refuses version 4.
- The macro generator didn't change. On the real database its output is identical to `dev`'s, and
  applying the twelve starting sections in memory left no schedule in error and all 5,770 columns in place.
- `Fan` and `Basis Of Design` added to the starting sections in the test copy, after reviewing the user's
  equipment-inventory reference code. No app code changed.
- `Mechanical Equipment` section in the test copy (user, 2026-11-08), from the `_ALL MECH EQUIP FAMILIES`
  schedule's columns: `Equipment Tag`, `IPS_EQUIP_Area_Served`, `Revit Admin`. The schedule stays.
- The 18 `_AHU Section (...)` schedules became sections named `AHU ...` in the test copy and were deleted
  there (user, 2026-11-08). Each holds the schedule's own columns, without the tag and admin ones.

## 2026-11-06: Schedule Builder
- The schedule window is now titled Schedule Builder.
- Column Width (in) row in the Schedule section (this schedule's override; gray when inherited) and
  Default Column Width (in) in the Parameter section (the parameter's own, for every schedule).

## 2026-11-05: Shared table view template
- `table_view.py`: `DEFAULT_TABLE_VIEW` holds the settings for all tables. Bigger heading font,
  click a header to sort (ascending, descending, back to the table's order), columns fitted to their
  longest entry with a cap when a database loads, and dragging an edge changes that column only.
- The schedule window's grid takes the heading font only.
- Headings leave more room: with under about 20 px spare, Tk draws only a heading's first line.

## 2026-11-05: Create GitHub Ticket button
- On the main toolbar. Opens the repo's new issue page with the app version filled in.

## 2026-11-05: Schedules tracked within a Revit project
- `Schedule.guid`: stable through renames, saved in JSON and CSV (`schedule_guid`).
- The macro keeps `GUID|role` to `UniqueId` in Extensible Storage on a `DataStorage` element, and
  matches untracked schedules by name. A changed name prompts: Use Database Name, Keep Revit Name,
  Leave Unchanged, Create New Schedule, with Do the Same for the Rest. Compiled against the Revit
  API; not yet run in Revit.

## 2026-11-05: Parameter Name Builder matches the Family Name Builder
- Use, Prefix, Suffix and Order per term, in a shared `param_name_format` (JSON; like the family
  format, not in CSV). Both windows draw their terms with `_build_name_terms_table`.
- New term Company Code (`IPS`), which was fixed text. A Clarifier with no Descriptor becomes the
  Descriptor (121 parameters); this happens on load, and every name still builds the same.

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
