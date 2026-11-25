---
description: Verify the work against the brief, report PASS/FAIL, then archive
---
`hz` = the command after "[hz] cli:" in context (it carries this session id). If absent: `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py.sh" hz.py`.
Reply in the user's language. Follow the steps in order.

STEP 1. Run `hz check`, then `hz verify`. Do not run the done commands yourself; verify did.
STEP 2. For each MANUAL item: check it (run something or read the code) and give evidence. Never write PASS without evidence.
STEP 3. If `out-of-scope` lists files: explain why each changed, or offer to revert it.
STEP 4. Report in exactly this shape:
Result: PASS | FAIL | INCOMPLETE   (INCOMPLETE = verify did not run every done item; never call it PASS)
1. <item> - PASS/FAIL - <evidence, 1 line>
Out-of-scope: <files or none>
STEP 5. If PASS: ask "Close this task? (archives the brief, then use /clear)". On yes run `hz close`.
