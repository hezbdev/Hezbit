---
name: goal-alignment
description: Use before coding any request that is vague, has no clear finish line, or touches more than 2 files. Also use when a [hz] line is present in context. Keeps work on the stated goal and saves tokens.
---
Rules. Apply in order. Reply in the user's language.

R1. A `[hz]` line in context is the contract: request (user's own words), scope, out, done, reply.
    - Do not edit outside `scope`. Never do anything in `out`.
    - Shape the answer as `reply` says. Full request text: `hz request`.
R2. No `[hz]` brief and the request is clear and touches <=2 files: just do it.
R3. No brief and the request is vague OR touches >2 files: tell the user to run /hezbit:brief. Do not code yet.
R4. Locate code with `hz find <term>` (path is in the [hz] cli line). Do not scan the repo. Do not read a whole file: find the line, then Read with offset/limit <=80 lines.
R5. Never re-read a file already in context. Never paste code back; say `path:line`.
R6. Broad exploration (>3 files to look at): hand it to the `scout` subagent.
R7. After each finished plan step run `hz step "<note>"`.
R8. Before saying "done" on a task with a brief: run `hz verify` and fix FAIL lines.

Type cheat sheet:
- FIX: reproduce or locate cause -> smallest change -> run the check.
- ADD: find the closest existing example -> copy its pattern -> add a check.
- CHANGE: list affected files via `hz find` -> change one file at a time -> run tests.
- EXPLAIN: <=8 lines with `path:line` references. No edits.
- REVIEW: `path:line - problem - fix`, max 7. No edits.

Ask only if a required field is unknown. Max 2 questions, multiple choice A/B/C, mark your best guess (default).
