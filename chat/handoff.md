# Handoff

Current state of the project for the next AI session. See [README.md](README.md) for how this
folder works.

## Workflow
- `dev` is the integration branch. Branch features off `dev`, merge finished work back into `dev`,
  then merge `dev` into `main`.
- Commit/push only when the user asks.
- Build the `.exe` (`build_exe.py`, see the README) only when merging `dev` into `main`, never for
  a `dev` push; then check it starts.
- Always `git fetch` first: work happens on two machines.
- Run tests with `pytest`. All tests live in `tests/`; config is `[tool.pytest.ini_options]` in
  `pyproject.toml`. On the second machine use the project env: `./.conda/python.exe -m pytest`.
- The repo lives off OneDrive (this machine: `C:\Users\glove\gits\design-data-manager`); OneDrive
  syncing `.conda` broke Tk. The working database is untracked and stays on OneDrive:
  `%APPDATA%\DesignDataManager\settings.json` has `database_folder` =
  `...\OneDrive - IPS\Documents\_BIM\_PARAMETERS\ddm-data`. `data/test_data/` is fixtures only.
- The old OneDrive repo folder was deleted on 2026-11-05. The `.exe` build venv
  (`%LOCALAPPDATA%\ddm-build\venv`) was recreated from this repo's `.conda\python.exe` the same day
  (pandas 3.0.6, numpy 2.5.3, PyInstaller 6.22.3); no `.exe` has been built with it yet. The beta
  `.exe` was kept in this repo's ignored `dist/`.

## Machines
- **First machine:** pushes over SSH; commits authored as George.
- **Second machine** (Windows, OneDrive path, HTTPS remote): commits before 2026-11-01's
  housekeeping are authored as "GitHub Copilot" (its old git identity), not a separate person.
  Its repo-local git identity is now gmclove <george.love077@gmail.com>. The Artifact tool cannot
  reach claude.ai artifacts from it (corporate TLS inspection: `UNABLE_TO_VERIFY_LEAF_SIGNATURE`),
  which is why the plan moved into this folder; the Claude Docs connector does work. Fix would be
  `NODE_EXTRA_CA_CERTS` pointing at the IPS root certificate.
- A new machine needs its own SSH key added at https://github.com/settings/keys.

## State (2026-11-05)
- Next time the user saves in the GUI, the `.txt`, `.rfps` and `.cs` in `ddm-data` pick up the
  `IPS_SPACE_AirReq_DuctLeak_PRCNT` rename (GUID kept). In Revit it keeps the old name until its
  shared parameter is updated. Fix it in the workbook too; import corrects it either way.
- `dev` is ahead of `main` (merge when asked; build the `.exe` then); `v0.1.0-beta` tags `82727d5`. The beta `.exe` is shared with
  testers outside GitHub (the repo is public and the `.exe` holds the master database).
- Latest work (see [changelog.md](changelog.md)): unsaved-changes warning (close / Load / Import);
  Families tab: Category 1/2 + codes, Category Code (2D/3D per Revit category), Family Name Builder
  (one click on a Name; shared `family_name_format`), no family double-click window; schedule
  window edits Parameter properties and shows Default Header; macro asks Rebuild All / Selected and
  Override Existing (Windows Forms, turned on in the module's .csproj); Save builds the macro in
  the background after the other files.
- Open questions for the user: the database's country code is USA but family names use US; the
  family window (family Default Values, a family's parameter list) is now unreachable.
- Imported families have no parameters yet (the workbook doesn't record them).
- Parameter Name Builder added; every parameter now has recorded name terms.
- 246 tests; the heading wrap failure is fixed (the test was out of date, not the app). On this
  machine Tk sometimes fails to start in full runs, failing a random window test; rerun it alone.
  Moving off OneDrive didn't cure it (see [plan.md](plan.md)).
- Top priority is still the real Revit run of the schedule macro, which needs the user.
