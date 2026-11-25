---
description: Plan small steps from the brief, wait for approval, then execute one step at a time
---
`hz` = the command after "[hz] cli:" in context (it carries this session id). If absent: `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py.sh" hz.py`.
Reply in the user's language. Follow the steps in order.

STEP 1. Run `hz status`. If it says "no brief": tell the user to run /hezbit:brief. Stop.
STEP 2. Write the plan, max 5 steps. One action per step, max 2 files per step. Format:
1. <action> -> files: <a, b> -> check: <command or behavior>
Read only files in scope. Use `hz find` to locate code. Do not paste file contents back.
STEP 3. List up to 3 assumptions you are guessing. Ask "Approve?". Stop and wait.

AFTER APPROVAL:
STEP 4. Run `hz plan "<step 1>" "<step 2>" ...` (survives /clear and compaction).
STEP 5. Do ONE step. Run its check. Run `hz step "<what changed>"`. Next step.
STEP 6. Need a file outside scope? Stop, say which and why, ask. If allowed: `hz scope-add <path>`.
STEP 7. A check fails twice? Stop. Report the error in <=5 lines. Ask the user.
STEP 8. After the last step run `hz verify` and fix failures before saying you are done.
Keep replies to the shape in the brief's `reply`.
