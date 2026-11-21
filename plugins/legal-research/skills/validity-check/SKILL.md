---
name: validity-check
description: "Trigger: a load-bearing case (the answer changes if the case is bad): the anchor of a rule, any case quoted or pincited in graded or filed work, adverse authority being distinguished, a case supplied by an opponent or a professor, or any case the treatment screen flagged with Tier A or B language. Runs in the validity-checker subagent, one case at a time. Do NOT load for: background or redundant cites (use treatment-screen); statutes or regulations; cases not yet read with read_document; running several checks in parallel. Adapted from DingDuff Inc.'s validity-check skill; modified, not official and not endorsed by DingDuff Inc."
license: "DingDuff Skills License 1.0 (https://www.dingduff.com/skills-license/1.0) for the portions adapted from DingDuff; LICENSE.md has complete terms"
allowed-tools: Read, Grep, Glob, Bash
---

> Adapted from DingDuff Inc.'s "dingduff-validity-check" skill v3.8 (`SKILL.md` hard rules, verdict format, and `references/fallback.md`), https://www.dingduff.com. **Modified version, not official and not endorsed by DingDuff Inc.** Changes: rewritten for the CourtListener connector (`search` with `cites:`, `search_document`, `read_document`, `get_endpoint_item`) in place of DingDuff's `opinion_verify`, `show_citing_opinions`, and PACER tools; ledger recording added; Georgia court sets added; confidence caps at moderate, as DingDuff's fallback route does. License: DingDuff Skills License 1.0, full terms in `LICENSE.md`.

# Validity check (heavyweight)

Determines whether one case is still good law **for the specific proposition it is cited for**. Runs in the `validity-checker` subagent. One case per run; never run two at once.

## Inputs (the delegation contract)

1. The case: ledger id, full citation, cluster id, opinion id.
2. The proposition: the specific rule it is cited for. Required.
3. Jurisdiction and posture: the target court, and whether a federal court applies state law.
4. The role: anchor, supporting cite, or adverse case being distinguished.

## Hard rules

1. Passages and snippets are triage only. Read the treating opinion with `read_document` before saying what it did.
2. Separate writings (dissents, concurrences) do not overrule.
3. Recurse on adverse authority: the overruling case may itself be overruled.
4. Deduplicate by case name before counting: one decision can appear as a combined opinion, a lead opinion, and a dissent.
5. A citation that will not resolve is no evidence that the case does not exist; say which routes were tried.
6. Report uncertainty as uncertainty. Confidence caps at **moderate**: this route has no tiered ranking, no curated flag-term co-occurrence, and no truncation reporting.

## Leg 1: direct history (same litigation)

`get_endpoint_item` on `clusters` for the case (fields `id, case_name, docket, sub_opinions, citations, date_filed`), then on `dockets` for its docket (fields `id, case_name, docket_number, court_id, clusters`). Any later cluster on the same docket is a candidate reversal, vacatur, or amendment; read it. Search CourtListener for the docket number in quotes to catch a further appeal filed under a new docket (for a Court of Appeals of Georgia case, a Supreme Court of Georgia certiorari decision). For a federal origin, check RECAP for the docket's later entries.

## Leg 2: forward treatment

1. Scope the invalidating courts: the case's own court, the courts above it, and the Supreme Court of the United States. For a federal court applying Georgia law, add the Supreme Court of Georgia (`ga`).
2. Three sweeps, all with fields: `cites:(<opinion_id>)` ordered `dateFiled desc`; the same ordered `citeCount desc`; the same with `court` set to the invalidating courts. Raise `num_results` for heavily cited cases.
3. Word searches regardless of what the sweeps returned: `"<case name>"`; `"<reporter cite>"`; and `"<case name>" AND (overruled OR abrogated OR "no longer good law" OR "we disapprove" OR "receded from" OR "declined to follow" OR "superseded by statute" OR "limited to its facts" OR "called into question" OR "to the extent that")`.
4. Passages: `search_document` on the citers from invalidating courts and on every word-search hit, query = the first party name. Then run the lightweight scorer for the flags:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/treatment_screen.py" "<matter>" <id>
   ```
5. For every flagged passage outside a separate opinion: read the citing opinion, then answer three questions. Is this a reference to the case? Which of the case's holdings is the court engaging? Is the court doing something to the case, or describing it? Classify: overruled, limited, questioned, criticized, distinguished, explained, followed.

## Leg 3: upstream

Read the case and identify the three to eight authorities it relies on for the proposition (not everything it cites). Screen each for later overruling or limitation the same way. A parent undermined after the case relied on it puts the case AT RISK even with a clean citing history.

## Leg 4: change without citation

State the current rule independently: one semantic CourtListener query for the proposition in current doctrinal language, restricted to the controlling courts and the last decade, then read the most recent authoritative statements. A new element, a shifted burden, a rephrased standard, or a vanished exception is a silent-shift flag. Check Georgia Commons (or `uslaw-mcp`) for statutory amendments to any statute the case construed, with effective dates.

## Verdict and recording

One of: VALID · VALID BUT NARROWED · AT RISK · QUESTIONED · INVALID FOR THIS PROPOSITION · INVALID · INDETERMINATE. Write the report below to `notes/<ledger-id>-validity.md`, then record it:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/ledger.py" treatment "<matter>" <id> --verdict "<VERDICT>" --confidence moderate --proposition "<the rule>" --report "<matter>/notes/<id>-validity.md" [--replacement "<ledger id of the authority now stating the rule>"]
```

Report, about 250 words, quoting operative language:

```
CASE: <full citation>
PROPOSITION CHECKED: <the rule>
JURISDICTION: <target court>
STATUS: <verdict>, confidence <low/moderate>
DIRECT HISTORY: <later clusters on the docket and further appeals, or none located; say what was checked>
ADVERSE TREATMENT: <each: citing case, full cite, the operative language quoted, the holding it reached; deduplicated; or none located>
AT-RISK FINDINGS: <undermined upstream authority or divergence from the current rule; or none>
RECENT APPLICATION: <most recent case applying it for this proposition, with cite>
IF UNUSABLE, WHAT REPLACES IT: <authority now stating the rule, or n/a>
COVERAGE: <citing_count; citers listed and read in passage; invalidating courts swept; word searches run; legs run; routes that produced citers; the moderate cap and why>
```

Every case in graded or filed work still gets the user's manual KeyCite; the verdict never replaces it.
