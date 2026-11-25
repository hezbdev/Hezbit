---
description: Turn a request into a short, checkable brief (per-session brief file)
argument-hint: [task in your own words, or "TYPE | scope | cmd :: expected"]
---
Task from user: $ARGUMENTS

`hz` = the command after "[hz] cli:" in context (it carries this session id). If absent: `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py.sh" hz.py`.
Reply to the user in the user's language. Write the brief file in English, terse.
Do NOT write code here. Do NOT rewrite the user's request: it is saved verbatim by a hook.

STEP 0. Run `hz request`. If it prints "no request saved", run `hz request "<the user's exact words, copied unchanged>"`.

STEP 1. Pick type. First match wins:
- asks why / how / what is -> EXPLAIN
- asks to check / review code -> REVIEW
- something broken, error, bug -> FIX
- new feature, file, endpoint, screen -> ADD
- anything else (refactor, rename, tweak, config) -> CHANGE

STEP 2. Find scope: run `hz find <keyword>` at most 2 times. Do not scan the repo. Do not read whole files.

STEP 3. If a field cannot be inferred, ask. Max 2 questions, multiple choice A/B/C, best guess marked (default). Never ask what `hz find` can answer.

STEP 4. Write the file at "[hz] brief file:" (or `hz path brief`) in EXACTLY this format:
```
type: FIX
scope: src/auth/, tests/auth/
out: no DB schema change; no new dependency
done:
- npm test -- auth :: passed
- manual: POST /login with "huy@exämple.com" returns 200
reply: diff-only, <=10 lines
```
Field rules:
- type: FIX|ADD|CHANGE|EXPLAIN|REVIEW
- scope: files/dirs allowed to change, comma separated (EXPLAIN/REVIEW may leave empty)
- out: every "do not / only / except / never" from the request, copied in the user's words. Else "none".
- done: 1-3 items. Best form `command :: expected text` (it is run automatically). Use `:: exit 0` when only the exit code matters. If it cannot be a command, write a visible behavior.
  Commands allowed for auto-run: npm/pnpm/yarn test or run test|lint|typecheck|check|tsc|test:*, npx jest|vitest|tsc|eslint, pytest, python -m pytest|unittest, mvn/gradle test, go/cargo/dotnet test, make test.
- reply: output shape, e.g. "diff-only, <=10 lines" or "explain in <=8 lines"

STEP 5. Run `hz lint`. Fix every ERROR line and rerun until it prints `ok`. NOTE lines are advice only.

STEP 6. Show the brief in <=8 lines. Ask: "OK to proceed?" Stop and wait.
