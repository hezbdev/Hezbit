#!/bin/sh
# Portable launcher: py.sh <script.py> [args...]. Finds a working Python on Linux/macOS/Windows (Git Bash).
d=${0%[/\\]*}
s=$1
shift
for c in python3 python py; do
  # the Windows Store "python3" stub exists but fails, so test that it really runs
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "" >/dev/null 2>&1; then
    exec "$c" "$d/$s" "$@"
  fi
done
echo "hezbit: python not found on PATH (hook skipped)" >&2
exit 0
