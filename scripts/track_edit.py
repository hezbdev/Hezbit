#!/usr/bin/env python3
"""PostToolUse Edit|Write|MultiEdit|NotebookEdit|Bash: record touched files (zero model tokens)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glib import *

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
init_session(data.get("session_id"))
if not os.path.isfile(p("brief.md")):
    sys.exit(0)
seen = read_lines(p("touched.txt"))
new = []
for path in tool_targets(data):
    r = rel(path)
    if outside(r) or is_state_path(r) or r in seen or r in new:
        continue
    new.append(r)
if new:
    write(p("touched.txt"), "\n".join(seen + new) + "\n")
elif tool_targets(data) and os.path.isfile(p("touched.txt")):
    os.utime(p("touched.txt"))  # bump mtime so Stop hook knows verify is stale
