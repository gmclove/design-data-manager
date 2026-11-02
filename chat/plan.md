# Plan

Next steps, open questions and known issues. Tick items as they're done and move the details to
[changelog.md](changelog.md).

The original living plan is a claude.ai doc: https://claude.ai/artifact/EVpeSRoyvJHmLp6cW37dtZ.
Its checklist hasn't been copied here yet (the second machine can't open it). Next session on the
first machine: copy its open items into this file, then treat this file as the plan.

## Next steps
- [ ] Copy the open items from the claude.ai plan doc into this file.
- [ ] Make the model the GUI's source of truth in `ddm_gui.py` (tables become views on the
      `Catalog`; edits go through model methods). Check with the user before starting, since
      `ddm_gui.py` is edited on both machines.
- [ ] Switch `ddm_gui.py` saves to `Catalog.save` / `Catalog.load` (versioned JSON).
- [ ] Revisit linking families and schedules to parameters by GUID instead of by name (see
      [decisions.md](decisions.md)); best done together with the source-of-truth change.

## Open questions
- On the Schedules tab, is an override value per family within a schedule, or for the family
  everywhere?

## Known issues
- `ddm_gui_test.py::test_main_tab_table_headings_wrap_after_column_resize` fails (heading padding
  assertion). Pre-existing on `dev`; also flaky on the second machine because Tk sometimes fails
  to start there.
