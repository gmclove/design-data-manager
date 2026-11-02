# Changelog

Newest first. One entry per piece of work; link commits where useful.

## 2026-11-01: Housekeeping
- GUI default save moved from the tracked fixture `data/test_data/test_data.ddm.pkl` to untracked
  `data/database.ddm.pkl`, so saving no longer rewrites test fixtures (the save also writes CSV,
  `.cs`, `.rfps` and `.txt` siblings).
- `.gitattributes` added (`* text=auto`; `.pkl` and the UTF-16 shared-parameter fixture binary).
- All tests moved into `tests/` (`ddm_gui_test.py` is now `tests/test_ddm_gui.py`); `pytest.ini`
  removed, config lives in `pyproject.toml`.
- README: correct conda env name, list the export modules, `tests/`, `data/` and `chat/`.
- `parameter_model_overview.md`: GUI section covers stored GUIDs and rename reference updates.
- Second machine's git identity set to George (repo-local).

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
