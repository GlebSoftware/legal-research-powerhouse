---
description: "Audit a matter's drafts: every citation, token, bare name, and quotation against the ledger and saved sources; writes the review page, table of authorities, and KeyCite checklist"
argument-hint: "[draft path] (default: every draft in the active matter)"
---

Run the citation audit for: $ARGUMENTS (default: all of `drafts/` in the active matter from `.session/active-matter`).

1. Audit:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/cite_audit.py" "<matter>" [<draft>] --html
   ```
2. Checklist:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/keycite_checklist.py" "<matter>"
   ```
3. Open `audit/cite-check.html` in the browser for the user (Windows: `cmd /c start "" "<matter>\audit\cite-check.html"`).
4. Report the red and yellow counts, then each red item with its fix:
   - no ledger entry, or not read: `/find-case` or `/find-statute`, then `read_document`;
   - name mismatch or bare name: `/bluebook` from the ledger entry;
   - quotation that does not anchor: correct the quotation from the saved source, or remove it;
   - secondary source not reported: `/secondary ingest`.
   Yellow items: missing or mismatched pincites (the audit names the star page), Not validated cases (`/validate --screen`), KeyCite pending, open Westlaw requests.
5. A red item the user accepts as is: ask them, and only on their word record `ledger.py waive "<matter>" "<key>" --reason "<their reason>"`. Never waive on your own.
