---
description: "Show the active matter's saved sources with hashes and retrieval times, and check that every file still matches its recorded SHA-256"
argument-hint: "[status]"
---

Report the saved sources of the active matter (from `.session/active-matter`).

1. Run:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/sources_status.py" "<matter>"
   ```
2. Show the table it prints: ledger id, file, system, retrieved at, size, and hash status (`ok`, `CHANGED`, or `missing`).
3. A `CHANGED` or `missing` file means the text the audit checks no longer equals what was retrieved. Re-retrieve that authority with its tool (`read_document`, `code_lookup_section`, `ecfr_section`) before relying on it, and tell the user which entries were affected.
