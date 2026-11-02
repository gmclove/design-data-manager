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

## State (2026-11-02)
- `dev` and `main` are identical and include `gui-on-catalog` (GUI on the `Catalog`, JSON saves,
  override prompt and tables, in-place editing). See [changelog.md](changelog.md).
- 139 tests pass; 1 known failure (heading wrap, see [plan.md](plan.md)). On the second machine
  Tk sometimes fails to start ("can't find a usable init.tcl"), failing a random window test;
  rerun it alone. Likely cause: the `.conda` env sits inside OneDrive.
