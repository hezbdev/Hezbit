#!/usr/bin/env python3
"""Quick scan for token sinks."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glib import *

files, present = [], []
for d, dirs, fs in os.walk(ROOT):
    for s in SKIP:
        if s in dirs:
            present.append(rel(os.path.join(d, s)))
    dirs[:] = [x for x in dirs if x not in SKIP]
    for f in fs:
        fp = os.path.join(d, f)
        if os.path.splitext(f)[1] in CODE_EXT:
            try: files.append((os.path.getsize(fp), rel(fp)))
            except OSError: pass
print(f"text/code files: {len(files)}; ~{sum(s for s,_ in files)//4000}k tokens if all read")
cm = os.path.join(ROOT, "CLAUDE.md")
if os.path.isfile(cm):
    n = len(read_lines(cm))
    print(f"CLAUDE.md: {n} lines" + (" (TOO LONG, target <150)" if n > 150 else " (ok)"))
else:
    print("CLAUDE.md: MISSING (run /hezbit:init-context)")
print("brief active:", os.path.isfile(p("brief.md")))
print("heavy dirs present (must be ignored):", ", ".join(sorted(set(present))[:10]) or "none")
print("largest files:")
for s, f in sorted(files, reverse=True)[:8]:
    print(f"  {s//1024:>6} KB  {f}")
