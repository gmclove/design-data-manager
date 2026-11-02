# Decisions

Design decisions and the reasons for them. Append new ones; if one is reversed, mark it
superseded rather than deleting it.

## Model
- **Model objects are the source of truth; the GUI should be a view on them.** The `Catalog`
  object owns params, families and schedules (no more class-level `_instances` registries).
- **Versioned JSON replaces pickle for saves** (`Catalog.save` / `Catalog.load`).

## Overrides
- **Overriding a value asks whether to apply it to the levels above** (user decision,
  2026-11-01). The levels are parameter default value, family override (`Fam.overrides`) and
  schedule override for one family (`Schedule.family_overrides`); the most specific wins.
  Overriding in a schedule asks two questions: also override it for the family? Also make it the
  parameter's default? Overriding in a family asks only the parameter question. Both unticked by
  default; Cancel changes nothing; clearing asks the same way. The wording is a draft
  (`DDMGUI._override_questions`) for the user to refine.
- An earlier version listed every other family and schedule to copy the override to; the user
  rejected it in favour of the questions above.

## GUI
- **The GUI's catalog is the source of truth; tables are views.** Edits go through model methods
  and invalid edits are rejected. Loading a file fixes or skips what the model can't hold (unknown
  links, bad widths, duplicate names) and lists each problem, instead of storing bad data and
  flagging it at validation.
- **Schedules pick their columns** (`Schedule.field_names`), ordered alphabetically when loaded
  from schedule entries, as the GUI always showed them.

## Parameter GUIDs and renames
- **Renaming a parameter assigns a new GUID by default.** The user is warned that Revit labels
  must be remapped to the new GUID, and can choose to keep the current GUID or cancel. See
  `guid_change_warning` in `revit_parameter_manager.py`.
- **Each parameter stores its GUID** (`guid` column in the GUI tables, saved with the data). A
  blank GUID defaults to the name-based `uuid5` the exporters always produced
  (`parameter_guid` in `revit_shared_parameter_export.py`), so files exported before GUIDs were
  stored stay consistent. Both exporters use the stored GUID; without that, "keep the current
  GUID" would have no effect, since the exported GUID was derived from the name.
- **A rename updates every reference to the old name:** family links, schedule entries, schedule
  header groups and other parameters' formulas. Formulas use `formula.rename_reference`, which
  matches whole names only (`Width` doesn't touch `GlassWidth`).
- **Header text still equal to the old name follows the rename; custom header text is kept.**
- **Renaming onto a name another parameter already uses is rejected,** because the reference
  updates would merge the two parameters irreversibly.
- **Superseded: link by GUID instead of by name.** Once the catalog became the GUI's source of
  truth, families and schedules hold parameter objects, so renames need no reference updates.
  The GUI's own reference-rewriting code was replaced by `Catalog.rename_param`.

## Repo
- **AI chat notes live in `chat/`** in the repo, so both machines share them through git (moved
  from the single `chat.md`, originally `CLAUDE.md`).
- **`__pycache__` and `.pyc` files are not tracked.**
- **Working data stays out of git.** The GUI saves to `data/` (ignored); `data/test_data/` is
  tracked fixtures that the app never writes to by default.
- **All tests live in `tests/`, named `test_*.py`;** pytest config lives only in `pyproject.toml`.
- **Line endings are normalized by `.gitattributes`** (LF in the repo), since the machines differ.
