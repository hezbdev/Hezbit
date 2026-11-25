---
description: Create a lean CLAUDE.md (<150 lines) and ignore suggestions
---
Reply in the user's language. Write CLAUDE.md in English, terse.
STEP 1. Look only at: config files (package.json, pom.xml...), directory tree 2 levels, README. Do not read source files in bulk.
STEP 2. CLAUDE.md sections, nothing else: Stack+versions / Layout / Commands (build, test, lint) / Conventions / Never do. Under 150 lines.
STEP 3. Long content (architecture, API, schema) goes to docs/*.md; CLAUDE.md only links to it.
STEP 4. Suggest lines to add to .gitignore (build output, deps, logs, big data).
STEP 5. Show the draft and ask before overwriting an existing CLAUDE.md.
