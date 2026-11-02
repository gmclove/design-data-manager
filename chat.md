# Design Data Manager: notes for Claude

## Plan
The living development plan is a Claude Docs doc: https://claude.ai/artifact/EVpeSRoyvJHmLp6cW37dtZ
Read it at the start of a session (status, known issues, short-term checklist, decisions,
changelog) and update it after finishing work: tick checklist items, mark issues fixed, add a
changelog row (newest first).

## Workflow
- Merge finished work into both `dev` and `main`.
- Work happens on feature branches; commit/push only when asked.
- Run tests with `pytest` (config in `pyproject.toml` / `pytest.ini`).

## Decisions so far
- Renaming a parameter assigns a new GUID by default. The user is warned (Revit labels must be
  remapped to the new GUID) and can choose to keep the current GUID. See `guid_change_warning`.
- Model objects are the source of truth; the GUI should be a view on them.
- Versioned JSON replaces pickle for saves.

## Handoff state (2026-11-01)
- `origin/main` and `origin/dev` (877a149) include a parallel rework: `ddm_gui.py` replaced
  `parameter_catalog_gui.py`, config modules were renamed `revit_*_definitions.py`, Revit
  exporters were added, and the model gained header text, column widths and header groups.
- Branch `catalog-model` (based on the older layout) holds steps 3-6: formula tokenizer and
  syntax checks (`formula.py`), a `Catalog` object replacing the `_instances` globals, the old GUI
  rewired onto it, JSON saves, and a `FamType` fix. It does not merge cleanly: `ddm_gui.py`
  still uses `Param._instances` and treats its DataFrames as the source of truth.
- Agreed next step (pending the user's confirmation): branch from `dev`, port the tokenizer,
  the `FamType` fix and `Catalog`/JSON (keeping the new header/width fields), then rewire
  `ddm_gui.py` onto `Catalog` as a separate step. Check with the user who is editing
  `ddm_gui.py` before rewiring it. Keep `catalog-model` as a reference until ported.
- Open question: on the Schedules tab, is an override value per family within a schedule, or
  for the family everywhere?
