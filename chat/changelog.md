# Changelog

Newest first. One entry per piece of work; link commits where useful.

## 2026-11-03: Save builds the macro module
- After installing the macro, Save runs `dotnet build` in the GLoveMacros module
  (`build_macro_module`) and lists the build's errors, warnings and a summary in Messages, so
  Macro Manager shows the new macro without opening VS Code.

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
