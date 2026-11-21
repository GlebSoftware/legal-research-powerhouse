# Report-back template

Source: `docs/05-secondary-sources.md` section 4. The protocol follows the stricter reading of Thomson Reuters General Terms v6.0 §4.4(a), which forbids uploading Thomson Reuters content to an AI tool. Whether v6.0 governs law-school accounts is unverified.

The user writes `research/<matter>/audit/secondary-reports/SR-NNN.md` (or answers the same fields in chat, and Claude writes the file from their answers verbatim). Then `/secondary ingest SR-NNN` runs `ledger.py secondary ingest`.

## What comes back

| Bring back | Never paste |
|---|---|
| Full citation: title, edition, volume, section, year, publisher | Full sections or pages of Am. Jur. 2d, C.J.S., A.L.R., treatises |
| Pinpoint: section, comment letter, or page | West headnotes, key numbers, KeyCite flags, synopses, other Thomson Reuters editorial text |
| The user's own summary for the proposition, two to six sentences | Bulk text from any Westlaw screen |
| The short quotations the memo will use, verbatim, each under 50 words | |
| Cases and statutes the source points to, as citations only | |
| KeyCite status of any case they will rely on | |

## File format

```markdown
---
request_id: SR-003
system: westlaw-manual
secondary_kind: restatement
citation: "<full citation as the user copied it>"
pin: "<section, comment letter, or page>"
retrieved_at: 2026-10-16
keycite: "<KeyCite status of each case they will rely on, in their words>"
points_to:
  - "<case or statute citation>"
quotes:
  - text: "<verbatim, under 50 words>"
    pin: "<pin for ttheir quote>"
---

<The user's summary: two to six sentences, their own words.>
```

## What ingest enforces

- `request_id` matches an open request in the ledger.
- Each quote is under 50 words; at most five quotes.
- The summary has two to six sentences and at most 200 words.
- `citation` and `pin` are present.
- Each quote is stored with its SHA-256; Phase 2 `verify_anchors.py` checks the memo's quotation against it after normalization.
- Each `points_to` citation is matched to a ledger entry where one exists; unmatched ones are listed for re-pulling from CourtListener, Georgia Commons, or `uslaw-mcp`, which then ledger them normally.
- The entry becomes `status: "reported"`, `verification.existence: "manual"`, `verification.method: "user-westlaw"`, with the disclosure label "Manual (Westlaw), reported <date>" (Lexis and Bloomberg variants name their platform).

The citation gate lets a draft cite the secondary source only after ingest sets `reported`. Bluebook form for the source comes from the `citation-format` skill (Indigo Book rules for Restatements, treatises, encyclopedias, A.L.R., and law reviews).
