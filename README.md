# Design Data Manager

Catalog, validate and sync Revit parameters, families and schedules.

- `revit_parameter_manager.py`: the model (`Catalog`, `Param`, `Fam`, `FamType`, `Schedule`), validation and JSON save/load
- `formula.py`: formula tokenizer, syntax checks and reference scanning
- `ddm_gui.py`: Tkinter review/edit GUI, a view on the model
- `ddm_tables.py`: converts between the model and flat tables (CSV, older saves, exports)
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

## Revit Schedule Macro

Saving the database also writes a Revit macro, `CreateSchedulesFromDatabase`. It goes next to
the save as `<database>.cs` and, when the Revit 2025 macro module exists on this machine, into
`C:\ProgramData\Autodesk\Revit\Macros\2025\Revit\AppHookup\GLoveMacros\Source\GLoveMacros` as
`CreateSchedulesFromDatabase.cs`. Any older generated macro file in that folder is removed, since
two copies would stop the module building.

To run it in Revit 2025:

1. Open **Manage > Macro Manager** and select the **GLoveMacros** application module. Rebuild
   it so it picks up the new file: open it with **Edit** and build it there.
2. Open the project, select `CreateSchedulesFromDatabase` and click **Run**.

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

**All Families row:** in a schedule, this row is a shortcut, not another level. A value set there
becomes the Schedule Default Value of every family in the schedule that has that column. The row
shows the shared value, **(Varies)** when the families differ, or blank when none is set. Leaving
a (Varies) cell unchanged changes nothing.

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
