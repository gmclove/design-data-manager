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
