---
name: statute-research
description: "Trigger: a question that turns on statutory, constitutional, or regulatory text; quoting or paraphrasing an O.C.G.A. section, the Georgia Constitution, a U.S. Code section, or a C.F.R. section; checking a section's currency or amendments; verifying a quotation from a code section; /find-statute. Do NOT load for: case law (use case-law-research); Restatements, treatises, or other secondary sources (use secondary-source-request); bills that never became law unless the question asks about pending legislation; citation formatting (use citation-format)."
allowed-tools: Read, Grep, Glob
---

# Statute and regulation research

Follow `research-protocol` throughout. Statutes come before cases: they define the elements the cases interpret.

## Georgia: Georgia Commons

Georgia Commons covers the O.C.G.A., the Georgia and U.S. constitutions, General Assembly bills, and Supreme Court of Georgia opinions, CC0. No key; 120 requests per minute.

1. **Find the section.** `code_search` for the concept, or `code_find_chapter` and `code_browse` to walk the title and chapter. Read the whole chapter's definitions section first, since definitions control the operative sections.
2. **Retrieve.** `code_lookup_section` with `citation`, for example `{"citation": "O.C.G.A. § 51-1-40"}`. For several sections at once, `code_lookup_sections`. The result is Markdown with front matter; the ledger hook saves it and records `cite_as`, `current_through`, `corpus_version`, and `in_force`.
3. **Verify quotations.** Before a draft quotes the section, run `verify_quote` with the section `id` (for example `51-1-40`) and the exact quoted text. The hook records the result in the entry's `quote_checks`.
4. **Currency.** Report the `current_through` line (for example "Including Acts of the 2025 Regular Session of the General Assembly"). For anything newer, search `bills_search` for amending bills and check LegiScan for pending legislation.
5. **Interpreting cases.** Search CourtListener for the section string in quotes (for example `"51-1-40"`) with the Georgia court filter, then follow `case-law-research`.

Cite the section as `O.C.G.A. § 51-1-40(b)`; the gate matches subsections to the section's ledger entry.

## Federal: interim path (until uslaw-mcp, Phase 2)

1. U.S. Code: GovInfo `USCODE` collection or uscode.house.gov, current release point recorded.
2. Regulations: eCFR point-in-time text (`https://www.ecfr.gov/api/versioner/v1/full/<date>/title-<n>.xml?part=<part>&section=<section>`), with the `up_to_date_as_of` date recorded.
3. Save every fetched page to the matter's `sources/` and record a ledger entry with `ledger.py upsert`, setting `source.system`, `citation.code` (`U.S.C.` or `C.F.R.`), `citation.title`, `citation.section`, and `verification.existence: "verified"` only after the text is saved.

The gate denies federal statute citations in drafts until a verified ledger entry exists, so the interim path must finish with the upsert.
