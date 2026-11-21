# Request template (SR block)

Source: `docs/05-secondary-sources.md` section 3. `ledger.py secondary request` renders the block from a JSON spec, appends it to `research/<matter>/audit/secondary-requests.md`, and writes a ledger entry `sec-SR-NNN` with `type: "secondary"` and `status: "requested"`. Never write the block by hand.

## The block

```
## SR-003 · 2026-10-16 · Issue 2: intervening criminal act and proximate cause (Georgia)

Proposition needed: whether a third party's intentional crime cuts off the original tortfeasor's liability, and the exception when the crime was foreseeable.
Trigger: 1 and 3. Free sources tried: CourtListener full-text search for "Restatement (Second) of Torts § 448" returned 2 Georgia opinions quoting the section; treatise reconciliation still needed because [case A] and [case B] state the foreseeability test differently.

Ranked source types
1. Restatement of the Law, torts: intervening and superseding cause sections, with comments and illustrations.
2. Texts & Treatises: a torts treatise chapter on superseding cause (locate).
3. Georgia practice material on proximate cause (locate).
4. Encyclopedias > American Jurisprudence: negligence, intervening and superseding cause (locate).

Westlaw searches (paste as written)
A. Precision plain language, content: Secondary Sources, jurisdiction: Georgia plus All States
   intervening criminal act of a third party superseding cause foreseeability
B. Terms and Connectors, content: Secondary Sources > Restatements of the Law
   intervening /s crim! /p supersed! /p foresee!
C. Advanced Search, content: Secondary Sources > Texts & Treatises
   ("superseding cause" OR "intervening cause") /p (crim! OR "third party") /p foresee!
D. Navigation: Secondary Sources > Encyclopedias > American Jurisprudence > table of contents for negligence, intervening and superseding cause (confirm on screen).

Known pointers (from retrieved primary sources only): Restatement (Second) of Torts § 448 (quoted in cl-cluster-111, cl-cluster-222). Everything else: locate.

Bring back (see section 4)
- Full citation: title, edition, volume, section, year, publisher
- Pinpoint: section, comment letter, or page
- Your own summary of what the source says for the proposition, two to six sentences
- The short quotations you will use in the memo, verbatim, each under 50 words
- Cases and statutes the source points to, as citations only
- KeyCite status of any case you will rely on
Do not paste: full sections or pages; West headnotes, key numbers, KeyCite flags, synopses, or other Thomson Reuters editorial text; bulk text from any screen.
```

## The rules the script enforces

1. **Locate rule.** Specific section numbers, volume numbers, titles, and authors appear only in `known_pointers`, and each pointer names the ledger ids of retrieved primary sources whose saved text contains the pointer string. The script rejects a pointer whose text is absent from every named source, and rejects a `§` anywhere outside `known_pointers` unless that exact section string is a known pointer. Everything else is "locate".
2. **Syntax rule.** A search labeled "Terms and Connectors" uses only terms, expanders, and connectors listed in `westlaw-syntax.md` (`!`, `*`, `#`, `/s`, `+s`, `/p`, `+p`, `/n`, `+n`, `%`, parentheses, field codes). A query with `&`, `OR`, or a quoted phrase is labeled "Advanced Search".
3. **Navigation rule.** Paths use category and publication names from `westlaw-content-sets.md`. Any other step carries "(confirm on screen)".
4. **Trigger rule.** `triggers` lists one or more of 1 to 6 (`docs/05-secondary-sources.md` section 2); `free_sources_tried` is required.
5. **Closed universe.** The script refuses a request in a closed-universe matter unless `assignment_supplied` is true.

## JSON spec

```json
{
  "issue": "Issue 2: intervening criminal act and proximate cause (Georgia)",
  "proposition": "whether a third party's intentional crime cuts off ...",
  "triggers": [1, 3],
  "free_sources_tried": "CourtListener full-text search for ... returned ...",
  "secondary_kind": "restatement",
  "system": "westlaw-manual",
  "ranked_source_types": ["Restatement of the Law, torts: intervening and superseding cause sections, with comments and illustrations.", "..."],
  "searches": [
    {"label": "A", "method": "Precision plain language", "content": "Secondary Sources", "jurisdiction": "Georgia plus All States", "query": "..."},
    {"label": "B", "method": "Terms and Connectors", "content": "Secondary Sources > Restatements of the Law", "query": "..."},
    {"label": "C", "method": "Advanced Search", "content": "Secondary Sources > Texts & Treatises", "query": "..."},
    {"label": "D", "method": "Navigation", "path": "Secondary Sources > Encyclopedias > American Jurisprudence > ... (confirm on screen)"}
  ],
  "known_pointers": [{"pointer": "Restatement (Second) of Torts § 448", "named_in": ["cl-cluster-111", "cl-cluster-222"]}],
  "assignment_supplied": false
}
```

`system` is `westlaw-manual` by default; `/secondary request --lexis` sets `lexis-manual` and `--bloomberg` sets `bloomberg-manual`, with the same structure and the platform's own search forms marked "(confirm on screen)", since no Lexis+ or Bloomberg Law help pages are stored yet.
