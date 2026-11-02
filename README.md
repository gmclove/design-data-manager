# Design Data Manager

Catalog, validate and sync Revit parameters, families and schedules.

- `revit_parameter_manager.py`: the model (`Catalog`, `Param`, `Fam`, `FamType`, `Schedule`), validation and JSON save/load
- `formula.py`: formula tokenizer, syntax checks and reference scanning
- `ddm_gui.py`: Tkinter review/edit GUI
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

```bash
conda env create -f environment.yml
conda activate design-data-manager
```

Or with pip: `pip install -e ".[dev]"` (Python 3.12+, with Tkinter available).

## Run

```bash
python ddm_gui.py                 # launch the GUI
pytest                            # run the tests
```

The GUI saves to `data/database.ddm.pkl` by default, with its CSV and export files alongside.
On first launch, before anything is saved, it opens the demo database from `data/test_data/`.

Quickbase sync reads `QB_APP_ID`, `QB_USER_TOKEN` and optionally `QB_APP_TOKEN` from the environment.
