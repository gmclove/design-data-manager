# Design Data Manager

Catalog, validate and sync Revit parameters, families and schedules.

- `revit_parameter_manager.py`: the model (`Catalog`, `Param`, `Fam`, `FamType`, `Schedule`), validation and JSON save/load
- `formula.py`: formula tokenizer, syntax checks and reference scanning
- `ddm_gui.py`: Tkinter review/edit GUI, a view on the model
- `ddm_tables.py`: converts between the model and flat tables (CSV, older saves, exports)
- `excel_import.py`: imports the old Excel master workbook
- `revit_macro_module.py`: finds, remembers and builds the user's Revit macro module
- `build_exe.py`: builds the standalone `.exe` (PyInstaller)
- `revit_shared_parameter_export.py`: Revit shared-parameter file export
- `revit_parameter_scheduler_export.py`: RF Tools Parameter Scheduler exports: `.rfps` (one template per
  family) and `_schedules.rfps` (one template per schedule)
- `revit_schedule_macro_generator.py`: Revit schedule macro (`.cs`) generator
- `quickbase_integration.py`: Quickbase REST client and sync service (work in progress)
- `config/`: Revit reference tables (data types, family categories, property-palette groups) and app paths
- `tests/`: pytest suite
- `data/`: working databases (untracked); `data/test_data/` holds tracked fixtures
- `parameter_model_overview.md`: how the model and validation fit together
- `chat/`: AI session notes: handoff state, plan, decisions and changelog

## Setup

The project environment lives in the `.conda/` folder inside the repo. Run things with it
directly, no activation needed:

```powershell
.\.conda\python.exe ddm_gui.py
```

or activate it from an Anaconda Prompt with `conda activate .\.conda`. In VS Code, pick
`.conda\python.exe` with **Python: Select Interpreter**.

Keep the repo out of OneDrive (or any synced folder): syncing the 900 MB environment breaks
Tkinter mid-run, and GitHub already backs up the code. This machine keeps it in
`C:\Users\glove\gits\design-data-manager`.

To create it on a new machine:

```bash
conda env create -f environment.yml -p ./.conda
```

Or with pip: `pip install -e ".[dev]"` (Python 3.12+, with Tkinter available).

## Run

```bash
python ddm_gui.py                 # launch the GUI
pytest                            # run the tests
```

The GUI saves to `data/database.ddm.json` by default, with a readable CSV and the Revit export files
alongside. The working database isn't in git (the repo is public), so keep it somewhere backed up:
set `database_folder` in `%APPDATA%\DesignDataManager\settings.json` to a OneDrive folder, e.g.

```json
{ "database_folder": "C:\\Users\\you\\OneDrive - IPS\\Documents\\_BIM\\_PARAMETERS\\ddm-data" }
```

and the app opens and saves its database there instead of `data/`. Closing the window, **Load** and **Import Excel...** check for unsaved changes first and
offer **Save**, **Discard** or **Cancel**. Closing while the schedule macro is still building
waits for the build to finish. CSV and older `.ddm.pkl` databases can still be loaded.
On first launch, before anything is saved, it opens the demo database from `data/test_data/`.

Each main tab (Parameters, Families, Schedules) has a **Search** box above its list. A row shows
only if it contains every word typed, in any column; case doesn't matter. Escape or **Clear** shows
every row again. Editing works the same on a filtered list.

Tables share one view template, `DEFAULT_TABLE_VIEW` in `table_view.py`. On the main tabs:
- **Click a column header to sort** by it: ascending, descending, then back to the table's own
  order. Numbers sort by value, and blanks go last.
- **Columns fit their longest entry,** up to a cap, when a database loads.
- **Drag a column's edge to resize that column only;** the others keep their width, and the table
  scrolls sideways if needed.

The schedule window's grid takes the template's heading font only. A click on its headers selects
the column, and its column order and widths are the Revit schedule's.

## Standalone .exe (Beta)

`dist/DesignDataManager.exe` runs without Python or conda. Copy it into its own folder and
run it.

- **First launch:** it opens the master database built into it.
- **Saving:** Save writes `data/database.ddm.json` and the exports into a `data` folder next to
  the `.exe`. Later launches open that copy.
- **Startup:** takes about 10 seconds, while Windows unpacks the app.
- **Unsigned:** the `.exe` isn't signed, so Windows SmartScreen may warn the first time. Choose
  **More info > Run anyway**.
- **Revit macro:** see **Revit Schedule Macro** below. Each user needs a Revit 2025+
  application macro module and the .NET SDK.

To build it, use a pip environment rather than `.conda`. Conda's numpy brings Intel MKL, which
makes the `.exe` about 230 MB. The master database to bundle defaults to
`data/database.ddm.json`.

```powershell
.\.conda\python.exe -m venv $env:LOCALAPPDATA\ddm-build\venv
& $env:LOCALAPPDATA\ddm-build\venv\Scripts\pip install pandas==3.0.6 numpy==2.5.3 openpyxl requests pyinstaller
& $env:LOCALAPPDATA\ddm-build\venv\Scripts\python build_exe.py [master database] [--console]
```

`--console` builds a version that shows errors in a console window.

## Importing the Excel Master Workbook

**Import Excel...** reads the old master workbook (`REVIT Schedules_Masters_Macro.xlsm`) into a
new database:

- **Parameters** come from the Parameters sheet: name, GUID, data type, instance or type, Group
  Parameter Under, default value and formula. Where the Static and Dynamic formulas differ, the
  Static one is used and the difference is listed.
- **Families** come from the Families sheet, with category, client and country, and the client
  and country abbreviations as codes.
- **Schedules** come from every sheet after **Backstage**. Rows are found by their labels in
  column B, so their positions can vary.
  - **Columns** are the Parameter Name row.
  - **Headings** are the text rows directly above it; stacked lines are joined.
  - **Header groups** are captions spanning several columns above the headings.
  - **Hidden columns** are those under a "Hidden ..." caption.
  - **Settings** are Itemize Every Instance and View Template.

  Schedule filters are left blank, so each defaults to its schedule's name. A column flagged
  REMOVE is left out. A parameter used on a schedule but missing from the Parameters sheet is
  defined from the schedule's own rows.

The workbook doesn't record which families belong to which schedule, or which parameters each
family has. Schedules are therefore imported on their own, with their columns taken straight
from the parameters, and families are imported unlinked. A family without parameters shows a
warning.

To rename a schedule, edit its name at the top of the schedule window. Enter or clicking away
renames it, and Escape undoes the edit. A blank name or one another schedule has is refused. A
blank Schedule Filter follows the new name.

To copy a schedule, select it on the Schedules tab and click **Duplicate Schedule...**. Name the
copy (it suggests "*name* Copy") and click **Duplicate**. The copy gets everything the original
has: columns, families, overrides, header groups, hidden columns, sections and settings. It goes
right after the original and opens in the Schedule Builder. It has its own GUID, so the macro
makes it a new schedule in Revit.

Under the schedule window's table are **Add Parameter...**, **Remove Parameter**, **◀ Move
Left**, **Move Right ▶**, **Add Family...** and **Remove Family**:

- **Frozen labels and headers:** the two label columns on the left and the header rows (group
  levels, column headers, Hidden Column, Column Width) stay in place while the table scrolls.
- **Selecting:** click a column header or a parameter's Name cell to select a column, or click a
  family's name on the left to select the family. Ctrl-click adds to the selection and
  Shift-click selects a range.
- **Add Parameter...** opens a searchable list of the parameters that aren't columns yet; pick
  one or several. They go to the right of the selected column (the rightmost one, if several
  are selected), or at the right end with none selected.
- **◀ Move Left** and **Move Right ▶** move the selected columns one place; they stay selected,
  so click again to keep moving. A move that would split a header group is refused: select all
  of the group's columns to move the group.
- **Group Selected Headers** (above the table, in the Header Groups row) puts a header group over the
  selected columns. **Ungroup Selected
  Headers** removes the innermost group around them; a group that comes from a section is changed
  in that section instead.
- **Add Family...** does the same for families not yet in the schedule. Each linked family is a
  row in the table.
- **Remove Parameter** and **Remove Family** act on the selection and ask first. A removed column
  takes its column settings and Schedule Default Values with it; a removed family takes its
  Schedule Default Values in that schedule.

Linking families doesn't change the Revit macro: Revit finds a schedule's elements by
`IPS_GROUP_Schedule_Name`.

The import replaces the open database but saves nothing until you click **Save**. Anything that
was fixed or skipped is listed in Messages.

## Revit Schedule Macro

Saving the database also writes a Revit macro, `CreateSchedulesFromDatabase`. A copy always goes
next to the save as `<database>.cs`. Save also installs the macro in the user's own Revit
application macro module and builds that module, so the macro appears in Macro Manager.

**What each user needs (once):**

1. **A macro module.** If you don't have an application macro module yet, create one in Revit
   2025 or later: **Manage > Macro Manager > Application > Module**, language C#, any name.
2. **The .NET SDK,** from https://dotnet.microsoft.com/download. Save uses it to build the module.
3. **Pick the module.** Save picks it by itself when there's only one. With several, it asks
   once, or you can choose under **Revit Macro Settings**. The choice is remembered per user in
   `%APPDATA%\DesignDataManager\settings.json`.

**What Save does:**

- **Installs:** it writes the macro into the module's source folder,
  `%ProgramData%\Autodesk\Revit\Macros\<year>\Revit\AppHookup\<module>\Source\<module>`, as
  `CreateSchedulesFromDatabase.cs`. The code uses that module's namespace. Any older generated
  macro file there is removed, since two copies would stop the module building.
- **Builds:** it builds the module with `dotnet build`, in the background and after the other
  save files are written, so you can keep working. The build's errors, warnings and a summary
  appear in Messages when it finishes, and a failed build also pops up its errors. If you save
  again while it's building, that save's macro is installed and built once the build finishes.
- **Fixes the .NET version:** Revit updates can need a newer .NET than the module targets. Since
  Revit 2025.5 the API needs .NET 10, and a .NET 8 module fails with error CS1705. Save then
  switches the module to the needed version, keeps the old project file as `.csproj.bak`, and
  builds again. If that .NET SDK isn't installed, Messages says which one to install.

**Running it:** in Revit, open **Manage > Macro Manager**, select `CreateSchedulesFromDatabase`
under your module and click **Run**. If Revit was open when you saved and the macro doesn't
appear, restart Revit. To build by hand instead, open the module with **Edit** and press
**Ctrl+Shift+B**.

When it runs, the macro asks what to build:
- **Rebuild All Schedules** (the default) or **Rebuild Selected Schedules**. Pick schedules from
  the list; the search box narrows it, and **Select All** / **Clear** act on the schedules shown.
  Checking a schedule switches to Rebuild Selected. A ✓ marks schedules already in the project.
- **Override Existing Schedules** (on by default). On, a Revit schedule that already exists is
  updated in place. Off, it's left as it is, and the summary lists it as left unchanged; only
  missing schedules are created.

The project remembers which Revit schedules the macro built, even after a rename in the database
or in Revit. When a schedule's Revit name differs from the database name, the macro asks what to
do with it:
- **Use Database Name:** rename the Revit schedule and update it.
- **Keep Revit Name:** update the Revit schedule and leave its name. The macro asks again next run.
- **Leave Unchanged:** don't change this Revit schedule. Cancel does the same.
- **Create New Schedule:** build a new schedule with the database name. The old one stays in the
  project, no longer tracked.

Tick **Do the Same for the Rest** to apply the choice to every other changed name in that run. The
record belongs to one project: in another project, including a schedule copied there, schedules are
matched by name.

The dialog uses Windows Forms, so the first Save switches it on in the module's project file
(`<UseWindowsForms>`, without its automatic `using`s, so names such as `View` don't clash with
Revit's). The original project file is kept as `.csproj.bak`, and Messages says so.

Each schedule in the database becomes three Revit schedules:

| Revit schedule | Category | Columns |
| --- | --- | --- |
| `3D - {name}` | Multi-Category (model elements) | hidden columns hidden |
| `{name} - Working` | Detail Items | every column shown |
| `{name}` | Detail Items | hidden columns hidden |

- **Schedule Settings,** at the top of the schedule window:
  - **Schedule Filter:** the `IPS_GROUP_Schedule_Name` value. It defaults to the schedule's
    name and overrides that parameter for every family in the schedule. Each Revit schedule
    lists only the elements with that value; the filter column itself is hidden.
  - **Itemize Every Instance:** on by default. It sets Revit's option of the same name.
  - **View Template:** the name of a schedule view template in the Revit project. It's applied
    to all three schedules after they're built. If the template controls fields or filters, its
    settings win. A name the project doesn't have is listed as a problem.
- **Columns:** every column takes its header text, width and header groups from the database. To
  hide a column, tick its box in the **Hidden Column** row under the column headers in the
  schedule window. The same checkbox is also in the column settings that open when you
  double-click a header.
- **Running it again** with Override Existing Schedules on updates the schedules it made
  before: their columns, filter and header groups are rebuilt to match the database, and the
  views keep their place on sheets.
- **When it finishes,** a dialog lists what was created, updated and left unchanged, plus any
  problems. Problems
  include a parameter that isn't loaded in the project's families, or a same-named schedule of a
  different category.

`tests/test_revit_schedule_macro_generator.py` builds the generated macro against the installed
Revit API (it needs Revit 2025+ and the .NET SDK; otherwise it's skipped), so a macro that won't
compile fails the tests.

## Schedule Sections

A section is a standard block of columns that many schedules share, such as electrical data. Change
the section and every schedule using it changes. Sections only change a schedule's columns: they never
add a parameter to the Revit project.

- **What a section decides:** which columns travel together, their order, their header groups and
  which columns are hidden. Headers and widths still come from each parameter, and a schedule can
  still override a header.
- **Sections tab:** click **Add Section...**, or double-click a section. The window lays out its columns
  like the Schedule Builder: Group Level rows, column headers, a Hidden Column row, where each column is
  included from, and the parameters' defaults. On the right, tick the schedules that use it; those with
  the most of its columns are listed first.
- **Header groups:** **Header Group Over All Columns** is the one over the whole section. For more, click
  headers to select them and **Group Selected Headers**, as in the Schedule Builder; groups can sit inside
  one another but can't overlap. **Ungroup Selected Headers** removes the innermost group around the
  selected headers. Selecting every column and grouping sets the one over all columns.
- **Sections inside sections:** a section can include others, so `Pump` includes `Electric Motor`, which
  includes `Electrical Data`. Change `Electrical Data` and the preview lists every schedule it reaches, at any
  level. The outermost caption wins: `Electric Motor` shows one `MOTOR DATA` caption over its columns and
  the electrical ones, and `Pump`, having no caption, keeps `MOTOR DATA` and leaves its own columns ungrouped.
- **Only Add Columns a Schedule Already Has** is on by default, so a section doesn't add empty columns.
  A schedule with none of the section's columns gets them all.
- **Preview Changes...** shows each schedule's columns now and after, and which header groups are replaced,
  trimmed or dropped. Nothing changes until **Apply Selected**. If a schedule shows a different header from
  the parameter's, a check lets you go back to the parameter's.
- **In the Schedule Builder:** **Add Section...** adds a whole section after the selected column, and a label
  names the sections in use. Remove a section's column to leave it out of that schedule; add it back and it
  returns to its place. A section's columns move only together, and only the section can reorder them.
- **Rules:** a parameter can be in only one section of a schedule. If you don't accept an edit for a schedule,
  it keeps its columns and stops using its section. Deleting a section leaves its columns as ordinary ones,
  and any section including it lists them directly. Adding a section takes over any section inside it that
  the schedule already uses.

## Combined Parameters

A combined parameter is one schedule column that joins several parameters, as Revit's combined
parameters do. `TAG` joins the five tag terms, with a `-` before terms 2 and 4, so it reads like `HW-P-1A`.
It's only a column: no family holds it, it isn't in the shared parameter file, and Revit works out its value.

- **Combined Parameters tab:** click **Add Combined Parameter...**, or double-click one. Give it a name, a
  column header and width, then add the parameters to combine, in order. Select rows to set their
  **Prefix**, **Suffix** and **Separator** (the separator goes before the next part); spaces count.
- **Using it:** **Add Parameter...** in the Schedule Builder lists combined parameters too, and a section can
  list one. When adding a section, a schedule with all of a combined parameter's parts counts as having it.
- **In the Schedule Builder:** its column shows its pattern in the Formula row, and each family's row shows
  the value its Default Values come to. Header, width and hidden work like any column.
- **Renames and deletes:** renaming a part parameter updates it. Deleting one drops that part; a combined
  parameter with no parts left shows an error. Deleting a combined parameter takes it out of every schedule
  and section.

## Families: Codes and Names

On the Families tab, one click on a cell edits it in place; one click on a **Name** opens the Family
Name Builder (below). Double-click does nothing.

A family's **Client**, **Country**, **Category 1** and **Category 2** are picked from dropdowns
listing every one already in the database. To add one that isn't listed, choose **Add New...** and
enter its name and code. The **Client Code**, **Country Code**, **Category 1 Code** and
**Category 2 Code** columns show their abbreviations, for example IPS, US, EQUIP and AHU. A code
belongs to the client (country, ...), not the family, so editing it on one family changes it for
every family with that client. Each code must be unique within its kind.

**Category Code** belongs to the Revit category: **3D** for categories placed in floor plans
(Mechanical Equipment, Duct Accessories, ...), **2D** for those on drafting views (Detail Item,
Generic Annotation, ...), and blank for categories used in both (Multi-Category Tags). Several
categories share a code; editing it on one family changes it for every family of that category.

**Parameter Name Builder:** one click on a Name on the Parameters tab opens it, and **Add
Parameter...** opens it to add a new one. It works like the Family Name Builder below. The terms
are Company Code, Parent Category, Child Category, Descriptor, Clarifier and Units, each with
**Use**, a **Prefix**, a **Suffix** and ▲▼ to reorder it, in one format shared by every parameter.
The default format reproduces the master workbook's names, e.g. `IPS_SPACE_Air_ExhOccMax_CFM`:
nothing separates Descriptor from Clarifier, so a Clarifier like `_TermUnit` brings its own
underscore. Parameters have no other place for their terms, so the Values are edited here: Company
Code, Parent Category, Child Category and Units list the values already in use, and typing adds a
new one. Names over 30 characters get the workbook's long name warning.
- **Rename This Parameter** saves the terms and the format, and renames the parameter if the
  **New Name** differs, asking about the GUID as any parameter rename does. Opening a parameter and
  saving with nothing changed changes nothing.
- Changing the format doesn't rename other parameters. There's no rename-all: when a parameter is
  next opened, the builder shows the name the new format gives it.
- A parameter without recorded terms shows a guess from its name.
- A new parameter's Data Type, Default Group Under and Instance or Type are chosen in the builder.

**Family Name Builder:** builds a family's name from its terms: Client Code, Country Code,
Category 1 Code, Category 2 Code, Description, Category Code, and the Category 1 and Category 2
names. Each term has **Use**, a **Prefix**, a **Suffix** and ▲▼ to reorder it. A used term adds
Prefix + value + Suffix; a blank value is left out with its prefix and suffix, and the first term
in a name has no prefix, so prefixes work as separators. The default format reproduces the master
workbook's names, e.g. `IPS-US_CTRL_Device_Pilot Light_2D`. The **New Name** can be edited before
renaming.
- **Rename This Family** renames the family and saves the format.
- **Rename All Families to Match...** lists the families whose names differ from the format and
  renames them after you confirm. Families whose new name would be blank, or the same as another
  family's, are left as they are and listed in Messages. Only names in the database change.

The format (order, prefixes, suffixes) is shared by every family and saved in the `.ddm.json`
database (not in the CSV copy).

## Overriding Default Values

A parameter's default value, formula and Group Under can be overridden for a family, and its
default value can be overridden for a family in one schedule. The family and schedule windows show
all of this in one table, and their **ⓘ Override Rules** button explains it in the GUI. The
explanation is kept in `OVERRIDE_RULES` in `ddm_gui.py`, so keep it in step with this section.

**Three levels**

| Level | Set on | Applies to |
| --- | --- | --- |
| Parameter Default Value | the parameter | every family and schedule that doesn't override it |
| Family Default Value | one family | that family, in every schedule it's in |
| Schedule Default Value | one family in one schedule | that family, in that schedule only |

**Which value wins:** the most specific one. A Schedule Default Value beats a Family Default
Value, and a Family Default Value beats the Parameter Default Value. If you clear an override
(delete the value and save), the level above shows through again.

**What can be overridden:**
- **Default Value:** at all three levels.
- **Formula, Group Under and Instance or Type:** at the Parameter and Family levels only. They
  describe the family, so in a schedule a family's row sets the family's own, which every schedule
  it's in uses.

**Reading the tables:**
- **Black text:** set at this level.
- **Gray text:** inherited from the level above.
- **Bold text** (schedule window): the value the schedule ends up using. A family's cell is bold
  when the schedule or the family sets its own value; the Parameter cell is bold when a family
  falls back to the parameter's (or the schedule has no family with that column). The Default
  Header is bold unless the schedule overrides the column's header.
- **White cell:** editable. Shaded cells are labels.
- **Shaded value cell:** doesn't apply, because the family doesn't have that parameter. In a
  schedule, an **Add Parameter to Family** button adds the missing parameter to the family, and
  **Add All Parameters** under the family's name adds every column it's missing at once.
- **Column Width (in)** (Schedule Builder, Schedule section): this column's width in this schedule
  only. It's gray while it's the parameter's; clear it to go back to that.
- **Default Column Width (in)** (Schedule Builder, Parameter section): the parameter's own width, used
  by every schedule that doesn't set its own.
- **Default Header** (schedule window, Parameter section): the parameter's own header text, which
  a column uses unless the schedule overrides it (double-click the column header). Gray means
  the parameter has none, so the header is its name.
- **Parameter section in the schedule window:** click a cell to edit the parameter itself
  (Name, Default Header, Default Value, Formula, Group Under, Instance or Type). It changes the
  parameter for every family and schedule, as editing it on the Parameters tab does; a rename
  asks about the GUID first. In the family window the section is read-only.

To edit a cell, click it in the schedule window (double-click it in the family window) and type.
Enter or clicking away saves, Tab moves to the next cell, and Escape cancels.

**Apply to All Families rows:** in a schedule, these rows are a shortcut, not another level. They set
every family in the schedule that has that column:
- **Default Value** becomes each family's Schedule Default Value, in this schedule only.
- **Formula** and **Group Under** become each family's Family Default Formula or Group Under.
  Revit keeps these in the family, so they change the family in every schedule it's in.
- **Instance or Type** (a drop-down) sets each family's own Instance or Type the same way.

**Instance or Type:** each family can make a parameter Instance or Type, whatever the parameter's
own setting. Set it in the family window, or in a schedule on the family's row or the Apply to
All Families row; both set the family itself, so every schedule it's in uses it. Blank uses the
parameter's. The RF Tools export (`.rfps`) uses each family's own Instance or Type, Default
Value, Formula and Group Under, and the CSV keeps them on the family's link rows.

**RF Tools exports:** Save writes two. `database.rfps` has one template per family, with the
family's own parameters and settings. `database_schedules.rfps` keeps the older layout: one
template per schedule, named after it, with the schedule's columns and each parameter's own
settings. Combined parameters are left out of both, since they aren't Revit parameters.

Each cell shows the shared value, **(Varies)** when the families differ, or blank when none is
set. Leaving a (Varies) cell unchanged changes nothing.

**Where else to override:** after you change a Family or Schedule Default Value, a prompt asks
where else it should go.
- **From a schedule:** pick other families in the same schedule to get the same value.
- **From a family:** pick schedules that family is in to get the same value.
- **Override Parameter Default Value?** makes the value the parameter's default for everything
  that doesn't override it.

Formula and Group Under changes offer only the parameter checkbox, because schedules can't hold
them.

**Renames:** overrides follow parameter and family renames. That includes parameter names used
inside formula overrides.

The model behind this is `Catalog.apply_override` and `Catalog.resolved_value` in
`revit_parameter_manager.py`. For how the model fits together, see
`parameter_model_overview.md`.

Quickbase sync reads `QB_APP_ID`, `QB_USER_TOKEN` and optionally `QB_APP_TOKEN` from the environment.
