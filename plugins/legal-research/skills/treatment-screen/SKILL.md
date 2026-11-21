---
name: treatment-screen
description: "Trigger: every case that will be cited in an answer, memo, or draft; a ledger entry labeled Not validated; a request to check whether a case is still good law at screening depth; the Screen step of /research. Do NOT load for: load-bearing cases headed into graded or filed work after the screen (use the validity-checker agent, heavyweight); statutes or regulations (use statute-research currency checks); cases not yet read with read_document."
allowed-tools: Read, Grep, Glob, Bash
---

# Treatment screen (lightweight)

Architecture section 5, steps 1 to 3. The screen catches loud failures and decides which cases need the heavyweight check. A clean screen is no finding of validity; label the result **Screened (lightweight)**, never Verified.

## Steps, per case

1. **Forward sweep.** CourtListener `search` with `q="cites:(<opinion_id>)"`, `type="o"`, `order_by="dateFiled desc"`, `num_results=20`, fields `["caseName", "cluster_id", "court_id", "dateFiled", "citeCount", "citation"]`. Use the entry's `source.opinion_id`. The ingest hook stores the list under `sources/treatment/<id>.citing.json` and records `citing_count`; citing opinions do not become ledger candidates.
2. **Second ordering.** When `citing_count` exceeds 20, run the sweep again with `order_by="citeCount desc"`, so a heavily cited treating case below the date horizon is seen.
3. **Passages.** `search_document` with up to 10 citing `opinion_id`s per call and `query` set to the case's first party name (for example "Becks"), `snippet_size=400`. Prioritize citers from courts that can invalidate the case (for a Court of Appeals of Georgia case: `gactapp` and `ga`; for a federal case: the circuit and `scotus`). The hook files each passage under the cited case by the citation markup.
4. **Score.**
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/treatment_screen.py" "<matter>" <id>
   ```
   The script scans six-sentence-scale windows around each mention for Tier A (overruled, abrogated, no longer good law, disapproved, superseded), Tier B (questioned, limited, declined to follow or extend, distinguished), and Tier C (reversed, vacated, remanded) language, marks separate opinions, lists citers from invalidating courts, and writes `treatment.level = "lightweight"`.
5. **Act on the result.** Any Tier A or Tier B flag outside a separate opinion: escalate to the `validity-checker` agent. Never adjudicate a flag from a passage; the passage may quote a party or describe a reversed court. A Tier C flag: confirm direct history with the case's own docket and later clusters.

## Report

Per case: "Screened (lightweight): N of M listed citing opinions read in passage; most recent citing decision <date>; <flags or 'no Tier A or B signals'>." Then the tradeoff line from `research-protocol` section 7.

## Budget

Steps 1 to 3 cost two to four CourtListener requests per case: one or two sweeps and one `search_document` per ten citers.
