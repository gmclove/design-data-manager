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
- `revit_parameter_scheduler_export.py`: RF Tools Parameter Scheduler (`.rfps`) export
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
alongside. CSV and older `.ddm.pkl` databases can still be loaded.
On first launch, before anything is saved, it opens the demo database from `data/test_data/`.

Each main tab (Parameters, Families, Schedules) has a **Search** box above its list. A row shows
only if it contains every word typed, in any column; case doesn't matter. Escape or **Clear** shows
every row again. Editing works the same on a filtered list.

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

Under the schedule window's table are **Add Parameter...**, **Remove Parameter**, **◀ Move
Left**, **Move Right ▶**, **Add Family...** and **Remove Family**:

- **Selecting:** click a column header or a parameter's Name cell to select a column, or click a
  family's name on the left to select the family. Ctrl-click adds to the selection and
  Shift-click selects a range.
- **Add Parameter...** opens a searchable list of the parameters that aren't columns yet; pick
  one or several. They go to the right of the selected column (the rightmost one, if several
  are selected), or at the right end with none selected.
- **◀ Move Left** and **Move Right ▶** move the selected columns one place; they stay selected,
  so click again to keep moving. A move that would split a header group is refused: select all
  of the group's columns to move the group.
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
- **Builds:** it builds the module with `dotnet build`. The build's errors, warnings and a summary
  appear in Messages, and a failed build also pops up its errors.
- **Fixes the .NET version:** Revit updates can need a newer .NET than the module targets. Since
  Revit 2025.5 the API needs .NET 10, and a .NET 8 module fails with error CS1705. Save then
  switches the module to the needed version, keeps the old project file as `.csproj.bak`, and
  builds again. If that .NET SDK isn't installed, Messages says which one to install.

**Running it:** in Revit, open **Manage > Macro Manager**, select `CreateSchedulesFromDatabase`
under your module and click **Run**. If Revit was open when you saved and the macro doesn't
appear, restart Revit. To build by hand instead, open the module with **Edit** and press
**Ctrl+Shift+B**.

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
- **Running it again** updates the schedules it made before: their columns, filter and header
  groups are rebuilt to match the database, and the views keep their place on sheets.
- **When it finishes,** a dialog lists what was created and updated, plus any problems. Problems
  include a parameter that isn't loaded in the project's families, or a same-named schedule of a
  different category.

`tests/test_revit_schedule_macro_generator.py` builds the generated macro against the installed
Revit API (it needs Revit 2025+ and the .NET SDK; otherwise it's skipped), so a macro that won't
compile fails the tests.

## Clients and Countries

A family's **Client** and **Country** are picked from dropdowns listing every client (or country)
already in the database. To add one that isn't listed, choose **Add New...** and enter its name and
code. The **Client Code** and **Country Code** columns show the abbreviation of the family's client
and country, for example ACME or USA. A code belongs to the client or country, not the family, so
editing it on one family changes it for every family with that client or country. Each code must be
unique among clients (or among countries).

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
- **Formula and Group Under:** at the Parameter and Family levels only. They describe the family,
  so a schedule shows them read-only.

**Reading the tables:**
- **Black text:** set at this level.
- **Gray text:** inherited from the level above.
- **Shaded cell:** doesn't apply, because the family doesn't have that parameter. In a schedule,
  an **Add Parameter to Family** button adds the missing parameter to the family.

To edit a cell, double-click it and type. Enter or clicking away saves, Tab moves to the next
cell, and Escape cancels.

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
