---
description: "Format a ledgered authority as a full citation and short form, in Georgia-filing or academic mode"
argument-hint: "<case name, ledger id, or citation> [pin <page>] [mode ga|academic]"
---

Format the citation for: $ARGUMENTS

1. Find the authority in the active matter's ledger:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" show --json
   ```
   Match by ledger id, case name, or reporter cite. If there is no entry, or the entry is not `retrieved` with `existence: verified`, stop and tell the user to run `/find-case` or `/find-statute` first.
2. Mode: `ga` when `question.md` names a Georgia court audience, otherwise `academic`, unless $ARGUMENTS says otherwise. A pin taken from the saved opinion's star pagination is a page of the official reporter: pass `--pin-reporter` with that reporter (for Georgia cases, `Ga.` or `Ga. App.`). `verify_anchors.py` reports the star page of any quotation.
3. Cases: run the formatter, which builds the citation from the ledger data alone:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/bluebook_case.py" "<matter>" <id> --mode <mode> [--pin <page> --pin-reporter "<reporter>"]
   ```
   Statutes, regulations, and secondary sources: delegate to the `citation-formatter` agent with the entry JSON.
4. Return the full citation, the short form, and every flag verbatim (missing pincite, pin on the other reporter, missing parallel, slip form, given names dropped). Resolve a flag before graded use; when the academic form cannot carry a verified pin, use the parallel form, which keeps the official-reporter pin.
5. Use the returned full citation verbatim in the draft; the citation gate checks it against the ledger.
