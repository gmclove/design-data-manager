# Handoff

Current state of the project for the next AI session. See [README.md](README.md) for how this
folder works.

## Workflow
- `dev` is the integration branch. Branch features off `dev`, merge finished work back into `dev`,
  then merge `dev` into `main`.
- Commit/push only when the user asks.
- Always `git fetch` first: work happens on two machines.
- Run tests with `pytest`. All tests live in `tests/`; config is `[tool.pytest.ini_options]` in
  `pyproject.toml`. On the second machine use the project env: `./.conda/python.exe -m pytest`.
- The GUI saves to `data/database.ddm.json` (untracked). `data/test_data/` is fixtures only.

## Machines
- **First machine:** pushes over SSH; commits authored as George.
- **Second machine** (Windows, OneDrive path, HTTPS remote): commits before 2026-11-01's
  housekeeping are authored as "GitHub Copilot" (its old git identity), not a separate person.
  Its repo-local git identity is now gmclove <george.love077@gmail.com>. It cannot reach claude.ai artifacts (corporate TLS inspection: `UNABLE_TO_VERIFY_LEAF_SIGNATURE`),
  which is why the plan moved into this folder. Fix would be `NODE_EXTRA_CA_CERTS` pointing at the
  IPS root certificate.
- A new machine needs its own SSH key added at https://github.com/settings/keys.

## State (2026-11-04)
- `dev` and `main` are identical; `v0.1.0-beta` tags `82727d5`. The beta `.exe` is shared with
  testers outside GitHub (the repo is public and the `.exe` holds the master database).
- Latest work (see [changelog.md](changelog.md)): main-tab search; schedule window Add/Remove
  Parameter, Move Left/Right, Add/Remove Family, editable title; Apply to All Families rows
  (Formula, Group Under, Instance or Type set the family itself); per-family Instance or Type
  reaches the `.rfps`; header groups from merged cells.
- Imported families have no parameters yet (the workbook doesn't record them).
- 191 tests; 1 known failure (heading wrap, see [plan.md](plan.md)). On this machine Tk sometimes
  fails to start ("can't find a usable init.tcl"), failing a random window test; rerun it alone.
  Likely cause: the `.conda` env sits inside OneDrive.
