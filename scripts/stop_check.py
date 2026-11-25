#!/usr/bin/env python3
"""Stop: if files were edited and the runnable `done` checks fail, send the model back (max 2 times).
"Edited" = touched by an edit tool OR changed in git since the session baseline (catches shell edits)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from glib import *
    from verify import run_verify
    try:
        sid = json.load(sys.stdin).get("session_id", "x")
    except Exception:
        sid = "x"
    init_session(sid)
    b = parse_brief()
    if not b or not any(" :: " in d and allowed_cmd(d.split(" :: ", 1)[0].strip()) for d in b["done"]):
        sys.exit(0)
    changed = git_changed()
    has_touched = os.path.isfile(p("touched.txt"))
    if not has_touched and not changed:
        sys.exit(0)
    vj = p("verify.json")
    gsig = change_sig(changed)
    try:
        last = json.loads(read(vj) or "{}")
    except ValueError:
        last = {}
    stale = (not os.path.isfile(vj) or last.get("gsig") != gsig
             or (has_touched and os.path.getmtime(p("touched.txt")) > os.path.getmtime(vj)))
    if stale:
        status, _, npass, ntotal = run_verify()
        try:
            r = json.loads(read(vj))
            r["gsig"] = gsig
            write(vj, json.dumps(r))
        except ValueError:
            pass
    else:
        status, npass, ntotal = last.get("status", "FAIL"), last["pass"], last["total"]
    if status != "FAIL":  # PASS or INCOMPLETE: nothing the model can still fix by itself
        sys.exit(0)
    try:
        n = int(read(p("stop_retries")) or 0)
    except ValueError:
        n = 0
    if n >= 2:
        print(json.dumps({"systemMessage": f"hezbit: verify still FAIL {npass}/{ntotal} after 2 tries. "
                                           "Stopping here; run `hz last` to see why."}))
        sys.exit(0)
    write(p("stop_retries"), str(n + 1))
    reason = f"hezbit: verify FAIL {npass}/{ntotal} (try {n+1}/2). Run `hz last`, fix, then finish."
    print(json.dumps({"decision": "block", "reason": reason}))
    stat("stop", reason, sid)
except SystemExit:
    raise
except Exception:
    sys.exit(0)
