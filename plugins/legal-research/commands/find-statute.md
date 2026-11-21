---
description: "Retrieve a statute or regulation section, save and ledger it, and verify any quotation"
argument-hint: "<citation, e.g. O.C.G.A. § 51-1-40> [\"quoted text to verify\"]"
---

Retrieve and ledger: $ARGUMENTS

Follow the `statute-research` skill.

1. If the matter's `question.md` sets `closed_universe: true` and the section is not in its `universe` list, refuse and say why.
2. Georgia (O.C.G.A. or Ga. Const.): call Georgia Commons `code_lookup_section` (or `constitution_lookup`) with the citation. The ledger hook saves the section and records it.
3. If $ARGUMENTS includes quoted text, run `verify_quote` with the section id and that exact text, and report `verified` and `occurrences`.
4. Federal: follow the interim path in `statute-research` and finish with `ledger.py upsert`.
5. Report the section heading, the `cite_as` and `current_through` lines, the saved path, and the operative text of the subsection asked about, quoted from the saved file.
