# Design Data Manager

Catalog, validate and sync Revit parameters, families and schedules.

- `revit_parameter_manager.py`: the model (`Param`, `Fam`, `FamType`, `Schedule`) and its validation
- `ddm_gui.py`: Tkinter review/edit GUI
- `quickbase_integration.py`: Quickbase REST client and sync service (work in progress)
- `config/`: Revit reference tables (data types, family categories, property-palette groups)
- `parameter_model_overview.md`: how the model and validation fit together

## Setup

```bash
conda env create -f environment.yml
conda activate parameter-catalog
```

Or with pip: `pip install -e ".[dev]"` (Python 3.12+, with Tkinter available).

## Run

```bash
python ddm_gui.py                 # launch the GUI
pytest                            # run the tests
```

Quickbase sync reads `QB_APP_ID`, `QB_USER_TOKEN` and optionally `QB_APP_TOKEN` from the environment.
