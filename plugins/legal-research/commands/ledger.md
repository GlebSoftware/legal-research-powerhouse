---
description: "Show or update the authority ledger: show, keycite-list, mark <id> keycite=<result>, use <matter>"
argument-hint: "[show|keycite-list|mark <id> keycite=<result>|use <matter>]"
---

Run the ledger command for: $ARGUMENTS (default `show`).

- `show` or empty:
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" show
  ```
- `keycite-list`:
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" keycite-list
  ```
- `mark <id> keycite=<result>`: record a KeyCite or Shepard's result that the user ran by hand. Pass the active matter path from `.session/active-matter`:
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" mark "<matter>" <id> "keycite=<result>"
  ```
  Record only results the user states in this conversation. Never infer a KeyCite result.
- `use <matter>`: switch the active matter.
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" use "<matter>"
  ```

Print the script output as a table: id, status, existence, label, KeyCite, citation.
