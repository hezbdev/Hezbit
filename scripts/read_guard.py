#!/usr/bin/env python3
"""PreToolUse Read: block token sinks (deps, build output, lock/min files, huge files without offset).

Directory rules apply only to the path RELATIVE to the project root, so a project that
lives under e.g. /home/me/build/myapp is not blocked as a whole."""
import json, os, sys

for _s in (sys.stdin, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

MAX_BYTES = int(os.environ.get("HEZBIT_MAX_READ_BYTES", 100_000))
BLOCK_DIRS = ("node_modules", "dist", "build", ".next", "target", ".git", "__pycache__", "coverage", ".venv")
BLOCK_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "composer.lock")
BLOCK_SUFFIX = (".min.js", ".min.css", ".map")
RENDERED = (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def rel_parts(path, root):
    """Directory parts of path inside root; [] if the path is outside root."""
    try:
        ap = os.path.abspath(path if os.path.isabs(path) else os.path.join(root, path))
        r = os.path.relpath(ap, root).replace("\\", "/")
    except ValueError:  # different drive on Windows
        return []
    if r == ".." or r.startswith("../"):
        return []
    return r.split("/")[:-1]


try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = data.get("tool_input") or {}
path = ti.get("file_path", "")
if not path:
    sys.exit(0)
root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
name = os.path.basename(path.replace("\\", "/"))
if (any(x in BLOCK_DIRS for x in rel_parts(path, root))
        or name in BLOCK_FILES or name.lower().endswith(BLOCK_SUFFIX)):
    print(f"hezbit: '{path}' is generated/dependency content (token sink). "
          "Use `hz find <term>` or Grep for the exact string instead.", file=sys.stderr)
    sys.exit(2)
try:
    size = os.path.getsize(path)
except OSError:
    sys.exit(0)
if name.lower().endswith(RENDERED) or "pages" in ti:  # Read renders these itself; offset/limit do not apply
    sys.exit(0)
if size > MAX_BYTES and "offset" not in ti and "limit" not in ti:
    print(f"hezbit: file is {size//1024}KB. Use `hz find <term>` to get the line, "
          "then Read with offset/limit (<=80 lines).", file=sys.stderr)
    sys.exit(2)
