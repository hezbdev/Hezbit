---
description: Scan the repo for token sinks and propose fixes
---
!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py.sh" audit.py`

From the scan above give max 5 fixes, ordered by tokens saved. Each fix = one concrete action (which line to add to which ignore file, which file to split, which part of CLAUDE.md to cut). Reply in the user's language. Do not edit anything without approval.
