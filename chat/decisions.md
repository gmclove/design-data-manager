# Decisions

Design decisions and the reasons for them. Append new ones; if one is reversed, mark it
superseded rather than deleting it.

## Model
- **Model objects are the source of truth; the GUI should be a view on them.** The `Catalog`
  object owns params, families and schedules (no more class-level `_instances` registries).
- **Versioned JSON replaces pickle for saves** (`Catalog.save` / `Catalog.load`).
- **Client and country codes belong to the client/country, not the family** (2026-11-02). The
  catalog keeps one code per name; families look it up. Codes must be unique per kind. Countries
  aren't pre-seeded with an ISO list; the dropdown lists what's in the database plus "Add New...".

## Overrides
- **Overriding a value offers the connected places and the parameter default** (user decision,
  2026-11-01). The levels are parameter default value, family override (`Fam.overrides`) and
  schedule override for one family (`Schedule.family_overrides`); the most specific wins.
  - Override in a schedule: a multi-select list of the other families in that schedule that show
    the parameter; picked ones get the same override in that schedule.
  - Override in a family: a multi-select list of the schedules that family is in; picked ones get
    the value as their schedule override (replacing any value set there, which would otherwise
    hide the family value).
  - Both: a checkbox to also make it the parameter's default value.
  - Nothing picked by default; Cancel changes nothing; clearing works the same way. Wording lives
    in `DDMGUI._override_questions`.
- **What can be overridden where** (user decision, 2026-11-01): Value at all three levels;
  Formula and Group Under at Parameter and Family level only. In Revit they belong to the
  family, so a schedule shows them read-only (`Schedule.FAMILY_OVERRIDABLE_ATTRIBUTES`).
  Formula and Group Under overrides offer only the Parameter checkbox (schedules can't hold them).
- **Override windows are one table each** (`OverrideTable`), from the user's mockup: columns are
  parameters; rows are the schedule's Group Level N..1 and Column Header (schedule window
  only), a Parameter block (Name, Default Value, Formula, Group Under; read-only), then one block
  per family (Default Value, Formula, Group Under). Values set at that level are black,
  inherited ones gray, columns a family doesn't have are shaded. Double-click a value to
  edit it in place (Enter/Tab/click away commits, Escape cancels; the override prompt follows),
  a header for column settings.
- **A family missing a schedule column gets an "Add Parameter to Family" button** (user's
  mockup, 2026-11-01), merged over that family's rows in the column. Clicking it links the
  parameter to the family.
- **The schedule table has an All Families row** (user's mockup, 2026-11-01) between the
  Parameter block and the families. It's a shortcut, not a new level: setting a value there sets
  the Schedule Default Value of every family in the schedule with that column. It shows the shared
  value, "(Varies)" when families differ, or blank. Its prompt offers only the Parameter Default
  Value checkbox. Committing an unchanged cell does nothing, so opening a "(Varies)" cell can't
  wipe the families' values.
- **Main lists: one click edits in place, two clicks open a window** (user, 2026-11-01/02):
  the family window from Families, the edit pop-up from Parameters. A single click waits 300 ms before opening the editor so a double-click can cancel it.
- Rejected along the way: a list of every family and schedule in the catalog, and a yes/no
  "also override for the family in every schedule" question.

## GUI style guide
User's rules for GUI text (prompts, checkboxes, window sections, column headings):
- **Short Title Case questions or headings**, each followed by a `Parameter = value` line
  (`(no value)` when clearing). Example: "Override Parameter Default Value?" / "Length = 7".
- **No "Also ..." sentences.**
- **Fixed terms for the three override levels:**
  - **Parameter Default Value**: the parameter's own value (Parameters tab).
  - **Family Default Value**: a family's override, used in every schedule the family is in.
  - **Schedule Default Value**: one family's value in one schedule.
  The verb is "Override" or "Clear", e.g. "Override Schedule Default Value for These Families?".
- **Context lines name the place plainly:** `Family_A`, or `Schedule A: Family_A`.
- **Instructions inside a text box are gray placeholder text** (`PlaceholderEntry`), in Title Case,
  e.g. "Blank Uses Family Default Value", or the default the box falls back to (`Width`, `1`).
  The hint clears when typing starts and returns when the box is emptied.
- Keep wording in one place (`DDMGUI._override_questions`) so it's easy to adjust.

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

## Revit schedule macro
- **Three Revit schedules per database schedule** (user, 2026-11-03): `3D - {name}` multi-category
  for the model; two Detail Items schedules because multi-category schedules can't hold detail
  items: `{name} - Working` shows every column, `{name}` hides the columns marked hidden. The 3D
  schedule hides hidden columns too (my default; not specified).
- **Filter on `IPS_GROUP_Schedule_Name` equal to the database schedule name** (user). The filter
  field is added hidden when it isn't a column.
- **Re-running updates existing schedules** (user): fields and filters are cleared and rebuilt, so
  the view and its sheet placements stay. A same-named schedule of another category is left alone.
- **Save installs the macro into the GLoveMacros module** (user), as
  `CreateSchedulesFromDatabase.cs`; other files starting with the generated header are deleted
  so the method isn't defined twice.
- **Schedule filter value overrides `IPS_GROUP_Schedule_Name` for every family in the schedule**
  (user, 2026-11-03), default the schedule's name. It is forced, not per family: a family's own
  schedule override of that parameter is ignored inside the schedule.
- **Itemize Every Instance defaults to on** (user). **View template** is a name typed in the
  GUI (the database can't see the Revit project); applied to all three Revit schedules last.

## Excel import (user, 2026-11-03)
- **Schedules stand alone**: the workbook doesn't link families to schedules or parameters, so
  schedule columns come straight from catalog parameters and families import unlinked.
- **Schedule filters import blank** (default to the schedule name), even where the sheet has one.
- **"Hidden Parameters" captions mark Hidden Columns**, not header groups.
- **Only sheets after Backstage are schedules** (the AHU sheets before it aren't imported).
- Formulas: Static over Dynamic when both exist (my default; differences are reported).

## Parameter names (user, 2026-11-05)
- **The scheme is the workbook's Parameter Name Editor,** and it must not change any existing name
  (user). Names it can't reproduce get sorted through one by one; there is no rename-all.
- **The scheme is fixed, not a format like families'** (my call). Per-term prefixes can't express
  it: Descriptor and Clarifier share one separator, so a Clarifier alone still needs one.
- **Terms are kept verbatim** (underscores and spaces), since the names depend on them.
- **The stray space in `IPS_SPACE_AirReq_DuctLeak _PRCNT` was removed** (user), keeping the GUID
  (my call: the same parameter, and Revit links hold). This is the exception to the default of a
  new GUID on rename.
- **Recorded terms only count while they build the current name.** A rename from anywhere else (a
  schedule window's Name cell) outdates them, and the builder shows a guess that rebuilds the name.
- **Parent Category, Child Category and Units are dropdowns of the values in use;** typing adds a
  new one, with no separate list to maintain (user chose dropdowns; typing is my call).
