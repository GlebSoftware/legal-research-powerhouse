---
description: "Westlaw relay for paywalled secondary sources: request <issue> drafts searches for the user, ingest <SR-id> records their report-back, list shows open and reported requests"
argument-hint: "request <issue> [--lexis|--bloomberg] | ingest <SR-id> | list | withdraw <SR-id>"
---

Run the secondary-source relay for: $ARGUMENTS

Load the `secondary-source-request` skill and follow it. Use the active matter from `.session/active-matter`. Claude never opens, searches, or reads Westlaw, Lexis+, or Bloomberg Law.

- `request <issue>`: confirm a trigger and run the free path (skill steps 1 and 2), build the JSON spec from `references/request-template.md` (add `"system": "lexis-manual"` for `--lexis`, `"bloomberg-manual"` for `--bloomberg`), then:
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" secondary request "<matter>" - <<'JSON'
  <spec>
  JSON
  ```
  If the script prints "Refused:", fix the spec as the message says and run it again. Show the user the new SR block from `audit/secondary-requests.md` verbatim.
- `ingest <SR-id>`: ask the user for the report-back fields in `references/report-template.md` unless `audit/secondary-reports/<SR-id>.md` already exists. Write their answers verbatim to that file, then:
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" secondary ingest "<matter>" <SR-id>
  ```
  Re-pull and read every citation the output lists as unresolved.
- `list`:
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" secondary list
  ```
- `withdraw <SR-id>`: only when the user says the request is no longer needed.
  ```bash
  uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" secondary withdraw "<matter>" <SR-id>
  ```
