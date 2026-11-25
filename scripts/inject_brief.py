#!/usr/bin/env python3
"""UserPromptSubmit. Saves the user's words verbatim; injects the brief only when it CHANGED."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glib import *

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
prompt = (data.get("prompt") or "").strip()
sid = data.get("session_id", "x")
init_session(sid)
touch_session()
try:
    if os.path.isfile(p("stop_retries")):
        os.remove(p("stop_retries"))
except OSError:
    pass

m = re.match(r"^/(?:hezbit:)?brief\b\s*(.*)$", prompt, re.S)
if m:
    if m.group(1).strip():
        write(p("request.md"), m.group(1).strip() + "\n")
    stat("prompt0", "", sid)
    sys.exit(0)

if parse_brief():
    h = brief_hash()
    try:
        old = open(marker(sid)).read()
    except OSError:
        old = ""
    if old != h:
        s = summary()
        print(s)
        try:
            open(marker(sid), "w").write(h)
        except OSError:
            pass
        stat("reinject", s, sid)
    else:
        stat("prompt0", "", sid)
    sys.exit(0)

ACTION = re.compile(r"\b(fix|add|implement|refactor|build|create|change|update|remove|migrate|"
                    r"sửa|thêm|tạo|làm|xây|đổi|chuyển|viết|cập nhật)\b", re.I)
if len(prompt) > 25 and not prompt.startswith("/") and ACTION.search(prompt):
    write(p("request.md"), prompt + "\n")
    mark = marker("nudge-" + str(sid))
    if not os.path.exists(mark):
        open(mark, "w").close()
        msg = "[hz] no brief. If this task is ambiguous or touches >2 files, run /hezbit:brief first."
        print(msg)
        stat("nudge", msg, sid)
        sys.exit(0)
stat("prompt0", "", sid)
