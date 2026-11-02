# Design Data Manager: handoff notes for Claude

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
- Each parameter stores its GUID (`guid` column in the GUI tables). A blank GUID defaults to the
  name-based `uuid5` the exporters always produced (`parameter_guid` in
  `revit_shared_parameter_export.py`), so earlier exports stay consistent. Both exporters use the
  stored GUID, which is what makes "keep the current GUID" on rename actually work.
- Renaming a parameter in the GUI rewrites every reference to the old name: family links,
  schedule entries, schedule header groups and other parameters' formulas (whole-name matches via
  `formula.rename_reference`). Header text still equal to the old name follows the rename; custom
  header text is kept. Renaming onto a name another parameter uses is rejected, because it would
  merge their references irreversibly.
- Deferred: linking families and schedules to parameters by GUID instead of by name (makes renames
  free, but changes the save format). Revisit when the model becomes the GUI's source of truth.

## Handoff state (2026-11-01)
- `catalog-model` was deprecated, merged into `dev` and deleted. `dev` and `main` now have the
  formula tokenizer and syntax checks (`formula.py`), the `Catalog` object (no more
  `_instances` globals), JSON `Catalog.save`/`load`, the `FamType` fix, and the header text,
  column width and header group features from the parallel rework.
- `ddm_gui.py` is the GUI. Its tables are still its source of truth; each validation builds a
  fresh `Catalog` from them. Next step: make the model the GUI's source of truth and switch
  its saves to `Catalog.save` (check with the user who is editing `ddm_gui.py` first; someone
  pushes Copilot-authored commits to `dev`/`main` in parallel, so always `git fetch` first).
- `main` and `dev` are identical (dev merged into main on 2026-11-01); `catalog-model` is deleted.
- Known failing test (pre-existing on `dev`):
  `ddm_gui_test.py::test_main_tab_table_headings_wrap_after_column_resize` (heading padding).
- Second machine (Windows, HTTPS remote) is synced: local `dev` and `main` fast-forwarded to
  origin on 2026-11-01; 112 tests pass, only the known failure above.
- Paused on the second machine: the parameter rename work (GUID prompt, reference updates) is done
  and merged; nothing in progress.
- Git pushes work from the first machine over SSH. A new machine needs its own SSH key added
  at https://github.com/settings/keys.
- Open question: on the Schedules tab, is an override value per family within a schedule, or
  for the family everywhere?
