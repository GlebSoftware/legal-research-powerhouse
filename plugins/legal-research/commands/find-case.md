---
description: "Resolve a case name or citation to one CourtListener cluster, read the opinion, and ledger it"
argument-hint: "<case name or citation>"
---

Find and ledger the case: $ARGUMENTS

Delegate to the `authority-finder` agent with this brief: the case reference above, the active matter (from `.session/active-matter`), and the instruction to follow the `case-law-research` skill. The agent must:

1. Refuse if the matter's `question.md` sets `closed_universe: true` and the case is not in its `universe` list.
2. Resolve the reference to exactly one cluster: `search` with `caseName:"..."` or `citation:"..."`, `type="o"`, the matter's court filter, and fields `caseName, cluster_id, court_id, dateFiled, citation, absolute_url`. Two or more plausible clusters: stop and report them.
3. Read it in full with `read_document` (`cluster_id`), which saves the text to `sources/` and promotes the ledger entry to `retrieved`.
4. Fetch the typed citations once with `get_endpoint_item` on `clusters` (fields `id, case_name, case_name_full, citations, date_filed, sub_opinions, absolute_url`).
5. Return the ledger id, case name, reporter cites, court, date, the saved file path, whether star pagination is present, and a three-sentence summary of the holding drawn from the saved text.

Then show the entry:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" show
```

Label the case Not validated until a treatment screen runs.
