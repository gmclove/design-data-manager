# Changelog

Newest first. One entry per piece of work; link commits where useful.

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
- Main Families list: one click edits the cell in place (Enter or clicking away saves, Escape
  cancels; Category is a dropdown); a double-click opens the family window.

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
