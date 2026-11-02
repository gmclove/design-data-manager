# AI chat notes

Shared memory for AI sessions on this project, kept in git so every machine and every session
sees the same context. Claude's own memory is per machine and doesn't sync; this folder does.

| File | What goes in it |
| --- | --- |
| [handoff.md](handoff.md) | Current state: what's in progress, where things stand, who/what is working where. Overwrite freely. |
| [plan.md](plan.md) | Next steps, open questions and known issues. Tick items off as they're done. |
| [decisions.md](decisions.md) | Design decisions and why. Append; don't rewrite history, mark superseded ones instead. |
| [changelog.md](changelog.md) | What changed, newest first, one entry per piece of work. |

## How to use it

**At the start of a session:** `git fetch`, pull `dev`, then read `handoff.md` and `plan.md`.

**After finishing a piece of work:**
1. Add an entry to `changelog.md`.
2. Record any new decision in `decisions.md`.
3. Update `plan.md` (tick items, add new ones) and `handoff.md` (current state).
4. Commit the notes with the work they describe.

Add another `.md` file here when a topic outgrows these four (for example a design write-up for a
large feature), and list it in the table above.
