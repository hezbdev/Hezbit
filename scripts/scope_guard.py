#!/usr/bin/env python3
"""PreToolUse Edit|Write|MultiEdit|NotebookEdit|Bash: ask before touching files outside the brief's scope,
and before changing the hezbit state (brief, plan, ...) that defines the contract."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glib import *

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
init_session(data.get("session_id"))
b = parse_brief()
if not b:
    sys.exit(0)
check_scope = b["type"] in NEEDS_SCOPE and b["scope_list"]
state, out = [], []
for t in tool_targets(data):
    r = rel(t)
    if is_state_path(r):
        if os.path.exists(os.path.join(ROOT, r)):  # creating a first brief is fine, rewriting it is not
            state.append(r)
    elif check_scope and not in_scope(t, b["scope_list"]):
        out.append(r)
reasons = []
if state:
    reasons.append("hezbit: " + ", ".join(sorted(set(state))[:3]) + " is the task contract. "
                   "Changing it can widen scope or drop constraints. Allow only if you want that.")
if out:
    reasons.append(f"hezbit: {', '.join(sorted(set(out))[:3])} outside the brief scope ({b.get('scope','')}). "
                   "Allow once, or add it with: hz scope-add <path>")
if reasons:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": " ".join(reasons)}}))
