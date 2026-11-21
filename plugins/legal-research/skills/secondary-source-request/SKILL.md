---
name: secondary-source-request
description: "Trigger: a research step where a paywalled secondary source would change the answer: a Restatement or UCC rule the free path did not surface as quoted by a court in the jurisdiction; fewer than three on-point appellate opinions after one semantic and one keyword CourtListener round; retrieved cases stating a rule inconsistently; a need for doctrinal history, policy rationale, or a defined term of art; an element checklist for a cause of action; an assignment that calls for secondary sources; /secondary request, ingest, or list; the user reporting back from Westlaw, Lexis+, or Bloomberg Law. Do NOT load for: closed-universe matters unless the assignment supplies the source; formatting a secondary citation already in the ledger (use citation-format); free sources such as CourtListener, Georgia Commons, CRS, or Wex; any request to search Westlaw, Lexis+, or Bloomberg Law directly, which never happens."
allowed-tools: Read, Grep, Glob
---

# Secondary-source request (the Westlaw relay)

Design: `docs/05-secondary-sources.md`, ADR-10. Claude never touches Westlaw, Lexis+, or Bloomberg Law. Claude decides when a secondary source would change the answer, drafts the searches, and records what the user brings back. Run the steps through the `/secondary` command, which calls `ledger.py secondary`.

## 1. Confirm a trigger

A request needs at least one trigger (`research-protocol` section 9 lists them, numbered 1 to 6). Name the trigger numbers. In a closed-universe matter, stop unless the assignment itself supplies the secondary source.

## 2. Run the free path first, and record it

| Need | Free path |
|---|---|
| Restatement or UCC section text as adopted | CourtListener full-text search for the section string in quotes, restricted to the jurisdiction's courts; read the quoting opinions; then `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/restatement_quotes.py" <matter> <section>` pulls each quotation of the section from the saved opinions, anchored with its star page, into `notes/restatement-*.md` |
| Federal criminal and enforcement practice | Justice Manual, USSG, FCPA Resource Guide, SEC and OFAC releases through `uslaw-mcp` (Phase 2 and 3) |
| Policy background and legislative context | CRS reports through Congress.gov |
| Definitions | Wex, human reading only |
| Open-access law reviews | The journal's own site, only when the citation is already known |

Write what was tried and what it returned into `free_sources_tried`.

## 3. Build the request spec

Follow `references/request-template.md`. The script enforces its rules and refuses a spec that breaks them:

- **Locate rule.** A section number, volume, title, or author appears only as a `known_pointer`, and only when a retrieved primary source in the ledger contains that exact string (a Georgia opinion quoting a Restatement section). Everything else says "locate".
- **Syntax.** Use only operators in `references/westlaw-syntax.md`. Label a query "Terms and Connectors" when it uses connectors and expanders only; label it "Advanced Search" when it uses `&`, `OR`, or a quoted phrase.
- **Navigation.** Use category and publication names from `references/westlaw-content-sets.md`; add "(confirm on screen)" to any other step.
- Rank three or four source types, most useful first, and write two to four searches: one Precision plain-language query, one or two Terms and Connectors or Advanced Search queries, and one navigation path.

Then run `/secondary request <issue>` with the spec. The script appends the SR block to `audit/secondary-requests.md` and ledgers `sec-SR-NNN` as `requested`. Show the user the block exactly as written.

## 4. Take the report-back

The user returns only the fields in `references/report-template.md`: full citation, pinpoint, their own two-to-six-sentence summary, verbatim quotations under 50 words each that the memo will use, citations the source points to, and KeyCite status of cases they will rely on.

- If they paste more (full sections, headnotes, key numbers, KeyCite flags, synopses, bulk text), do not store, quote, summarize, or reason from the excess. Say that the relay keeps only the listed fields and ask for those.
- Write their answers verbatim into `audit/secondary-reports/SR-NNN.md` in the template's format, then run `/secondary ingest SR-NNN`.
- Re-pull every case and statute the source points to from CourtListener, Georgia Commons, or `uslaw-mcp`, and read each before citing it. Ingest lists the ones not yet in the ledger.

## 5. Cite it

The citation gate passes a secondary citation only after ingest marks it `reported`. Build the Bluebook form with the `citation-format` skill. Wherever the source is cited, give its disclosure label from the ledger, for example "Manual (Westlaw), reported 2026-10-16". Quote only the quotations the user brought back, word for word.
