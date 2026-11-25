#!/usr/bin/env python3
"""SessionStart (startup|resume|clear|compact): the ONE place context is restored."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glib import *

try:
    sid = json.load(sys.stdin).get("session_id", "x")
except Exception:
    sid = "x"
init_session(sid)
touch_session()
prune_sessions()
if os.path.isdir(GL_BASE):  # project already uses hezbit: remember what was already dirty
    save_git_baseline()
cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hz.py")
# the session id is part of the command, so every hz call hits THIS session's state
out = f'[hz] cli: "{sys.executable or "python3"}" "{cli}" -s {resolve_session(sid)}'
out += f"\n[hz] brief file: {p('brief.md')}"
s = summary(with_next=True)
if s:
    out += "\n" + s
    try:
        open(marker(sid), "w").write(brief_hash())
    except OSError:
        pass
print(out)
stat("session", out, sid)
