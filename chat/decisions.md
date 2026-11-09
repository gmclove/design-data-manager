# Decisions

Design decisions and the reasons for them. Append new ones; if one is reversed, mark it
superseded rather than deleting it.

## Design criteria
Standing rules that every design has to meet. Check new work against them.
- **Stay away from project parameters as much as possible** (user, 2026-11-06). Parameters belong in
  families, for two reasons:
  - **Control of formulas:** the database has to stay in control of each parameter's formula.
  - **A usable Properties palette:** a project parameter shows on every family in its categories.
    Enough of them crowd the palette of all families until it's a useless interface.

  So the macro doesn't bind shared parameters to the project, even behind an option. A column that
  can't be scheduled because a parameter is missing is reported, and the fix is to add that parameter
  to the families that need it. Anything that would add a project parameter needs the user's approval
  first, for that specific case.

## Schedule sections
- **A section is a catalog definition that schedules link to, not a copy** (user asked for a data
  structure; link is my call): the 130 imported schedules show copies drift, e.g. `MOTOR DATA` has 18
  variants across 22 uses.
- **Schedules keep their resolved columns, header groups and hidden columns** (my call). A section writes
  into them, so the macro, CSV and sync read what they always read.
- **One section per standard, and a schedule can leave columns out** (my call), instead of a variant
  for each combination. Removing a section's column from a schedule records it as excluded.
- **The section owns order, caption and which columns are hidden; parameters own headers and widths; a
  schedule can still override a header** (my call). A local header stays until the preview's check clears it.
- **A parameter can be in only one section per schedule** (my call), because Revit can't repeat a column.
- **Sections can include other sections** (user, 2026-11-06): electrical data -> electric motor -> pump.
  Members are parameters or sections, so a change to `Electrical Data` flows up without repeating it.
  Includes rather than single-parent inheritance (my call), so `Pump` could also include `Vibration
  Isolation`. Loops, and a column listed twice through includes, are refused.
- **The outermost caption wins** (my call): a section with a caption covers everything inside it, and one
  without leaves its included sections' captions showing. That gives today's Pump layout: `MOTOR DATA` over
  the motor and electrical columns, and the pump's own columns ungrouped.
- **A schedule links to its top section only** (my call). Applying a section takes over any section inside
  it that the schedule already uses. A schedule reaching a section through another can't be unticked in that
  section's window; change it on the section it uses.
- **Deleting an included section lists its columns directly in the sections including it** (my call), so
  their schedules keep the same columns.
- **No separate equipment type list** (user, 2026-11-06): whether a schedule is electrical or motor-driven
  follows from the sections it uses.
- **Prefixes are future development** (user, 2026-11-06), see [plan.md](plan.md).
- **Took ideas, not code, from the user's equipment-inventory reference** (user approved, 2026-11-06). Its
  components are what includes already do. Taken: `Fan` beside `Pump` under `Electric Motor`, `Basis Of
  Design` from `Manuf`, and one component in two roles as the design for prefixes. Skipped: the class tree as
  a type list (decided against above); `serial`, `status`, `qty` and `aka`, which describe one real unit, while
  this app defines schedules and values live in Revit (no schedule has a serial or status column); `Glycol`
  (no such columns). `abbrev` as a default per schedule is left for the user to raise.
- **`Mechanical Equipment` section from `_ALL MECH EQUIP FAMILIES`** (user, 2026-11-08). It includes
  `Equipment Tag` and `Revit Admin` rather than listing their columns again (my call). Its tag columns are
  hidden, as `Equipment Tag` hides them on most schedules; the schedule shows them. The user first had the
  schedule deleted, then kept it as a schedule too, as with `_MECH EQUIP - Elect Connections`, which is
  made of sections too but stays a schedule.
- **A section's header groups sit inside its caption; the outermost caption still wins over included
  sections** (my call, 2026-11-09). A section's own groups always show; an included section's show only
  when the section including it has no caption, as before. Groups nest or stay apart, never overlap or
  repeat the same columns, since Revit can't build that.
- **Ungroup removes the innermost group around the selected headers** (my call); grouping every column
  sets the caption instead of adding a group.
- **In the section window, a column from an included section is hidden or grouped in that section**
  (my call): the window says where.
- **Combined parameters are columns, not parameters** (my call, 2026-11-09): kept in their own list
  so they never reach families, the shared parameter file or the RFPS export, but a schedule lists one
  by name like any column, so order, hiding, header groups, widths and sections work unchanged. One name
  space: a combined parameter can't share a name with a parameter.
- **A schedule with all of a combined parameter's parts has it by default** (my call), for Only Add
  Columns a Schedule Already Has when adding a section.
- **Deleting a part parameter drops that part** (my call); with no parts left it shows an error rather
  than disappearing from schedules.
- **The preview of a combined value leaves out an empty part with its prefix** (my call, unverified):
  check against Revit.
- **TAG goes just before a schedule's tag columns, and first in `Equipment Tag`** (my call, 2026-11-09);
  the user asked for terms 1 to 5 with a `-` before 2 and 4.
- **`_AHU Section (...)` schedules are sections only** (user, 2026-11-08): each became an `AHU ...`
  section and the schedule was deleted, in the test copy. The tag and admin columns stay out, since
  `Equipment Tag` and `Revit Admin` hold them and a column can be in only one section of a schedule (my
  call). Each has a header group like `COOLING COIL` and `PRE-COOLING COIL` (user), using wording already
  on the user's schedules where there was one, such as `SUPPLY FAN` and `HEATING COIL` (my call). Header
  groups inside the old schedules aren't kept (such as `MOTOR DATA` on the fans and `SUMMER`, `WINTER` on
  energy recovery), since a section has one header group and the outer one wins. No families were linked. The live database still has the schedules.
- **A fan with its own `IPS_FAN_HP` doesn't use `Fan`** (my call): it's one part of something larger, such as
  a boiler or cooling tower, and the `IPS_EQUIP_Elec_*` columns there describe the whole unit.
- **Not accepting an edit to a section stops that schedule using it, keeping its columns** (my call):
  a schedule can't stay linked and differ.
- **Preview adds only columns a schedule already has by default** (my call), so adopting a section
  doesn't add empty columns. A schedule with none of them gets them all.
- **The starting sections went in a separate file, not the live database** (my call, a change from the
  approved plan): format 4 would stop any copy of the app without this work opening the database.

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
- **Superseded: the scheme is fixed, not a format like families'.** The user wants the two windows
  very similar, so parameters have a shared format too. It reproduces every name once `IPS` is a
  term (Company Code) and a Clarifier with no Descriptor is stored as the Descriptor.
- **No rename-all for parameters,** unlike families (the user's rule that names get sorted through
  one by one, and each rename touches a GUID). Changing the format renames nothing by itself.
- **A parameter's Values are edited in its builder;** a family's come from its table columns.
- **Terms are kept verbatim** (underscores and spaces), since the names depend on them.
- **The stray space in `IPS_SPACE_AirReq_DuctLeak _PRCNT` was removed** (user), keeping the GUID
  (my call: the same parameter, and Revit links hold). This is the exception to the default of a
  new GUID on rename.
- **A rename clears a parameter's recorded terms,** so a rename from anywhere else (a schedule
  window's Name cell) leaves no stale terms; the builder then shows a guess from the new name.
- **Parent Category, Child Category and Units are dropdowns of the values in use;** typing adds a
  new one, with no separate list to maintain (user chose dropdowns; typing is my call).

## Schedule tracking (user, 2026-11-05)
- **Track within one project first** (user), by Revit `UniqueId`. Tracking across projects is not
  built.
- **A changed name prompts the user** (user). The four options are my reading: the user asked for
  "the options" without listing them. Keep Revit Name isn't remembered, so it asks again next run.
- **The record lives in the project, not the database** (my call): the database is shared across
  projects, and the macro can't write back to it. One `DataStorage` element holds the whole map.
- **Records for schedules no longer in the database don't block a name match** (my call), so
  re-importing the workbook, which makes new GUIDs, takes over the same Revit schedules by name.

## Table view template (user, 2026-11-05)
- **One set of defaults in code, `DEFAULT_TABLE_VIEW`; nothing is stored** (user). A saved template is
  possible future work (see plan.md). Sort and dragged widths are not remembered between runs.
- **The schedule window's grid takes the heading font only** (my call): a click on its headers selects
  the column, its order is the Revit column order, and its widths are the Revit widths.
- **Columns fit once per database** (my call), so an edit or validation never undoes a dragged width.
- **A third header click returns to the table's own order** (my call), since that order is otherwise lost.
