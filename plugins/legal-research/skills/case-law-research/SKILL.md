---
name: case-law-research
description: "Trigger: finding cases on an issue; resolving a case name or reporter citation to one CourtListener cluster; reading an opinion before stating its holding; gathering the cases that interpret a statute; a forward citing-opinion sweep for treatment; /find-case. Do NOT load for: statutes, regulations, or constitutions (use statute-research); paywalled secondary sources (use secondary-source-request); citation formatting (use citation-format); cases the ledger already holds as retrieved, unless re-reading a passage."
allowed-tools: Read, Grep, Glob
---

# Case-law research on CourtListener

Follow `research-protocol` throughout. The connector's tool names carry a prefix that varies by surface (`mcp__<uuid>__search` in the desktop app); match tools by their suffix: `search`, `read_document`, `search_document`, `get_endpoint_item`, `call_endpoint`, `analyze_citations`, `get_more_results`.

## 1. Frame the query

Write down the issue, the jurisdiction's court ids, and the date window before searching. The court ids come from the `[legal-workbench context]` block's Courts line, which reads the matter's jurisdiction (default Federal) from `data/jurisdictions.json`: search the binding courts first, then the federal courts listed with them. Without that line, read the matter's `jurisdiction_id` and its entry in `${CLAUDE_PLUGIN_ROOT}/data/jurisdictions.json`. Georgia, for example: `ga` (Supreme Court of Georgia), `gactapp` (Court of Appeals of Georgia); federal courts in Georgia `ca11`, `gand`, `gamd`, `gasd`. For Federal, `scotus` and the circuits bind by circuit; omit the court filter to search every federal court. Use `get_choices` with `field_name="court"` for any court id the table lacks.

## 2. One semantic query first

For an open question, run one natural-language query with `semantic=true`, `type="o"`, the court filter, and `num_results` of 10 to 20:

```json
{"q": "dram shop liability when the server did not know the patron would soon drive", "semantic": true,
 "type": "o", "court": ["ga", "gactapp"],
 "fields": ["caseName", "cluster_id", "court_id", "dateFiled", "citation", "citeCount", "absolute_url"]}
```

Always pass `fields`. These seven cover triage, ledgering, and the gate.

## 3. Narrow with keyword search

Use Lucene syntax on the terms the semantic hits use: quoted phrases, `AND`, `NOT`, and field prefixes such as `caseName:"Becks v. Pierce"` or `citation:"638 S.E.2d 390"`. To resolve a known case, search `caseName:` with the court filter; two or more plausible clusters means stop and ask which one.

## 4. Triage from snippets, then read

Snippets decide what to read and nothing more. For each case you may rely on, call `read_document` with `cluster_id`. For long opinions, read the whole document; use `chunk_index` only to jump to a known part after a full read, because the ledger saves the text once every chunk of one `chunk_size` is present.

After reading:

- Check `cluster_opinions`. Read a concurrence or dissent by `opinion_id` when it bears on the proposition, and never attribute a dissent's reasoning to the court.
- Note star pagination (`<span class="star-pagination" label="230">`) for pincites. When the saved text has none, flag the pincite for manual completion.
- Write reading notes to `notes/<ledger-id>.md`: holding, rule, key facts, pin pages, and quotations copied from the saved text.

## 5. Forward treatment sweep (lightweight screen)

Search `cites:(<opinion_id>)` with `type="o"`, `order_by="dateFiled desc"`, and fields `["caseName", "cluster_id", "court_id", "dateFiled", "citeCount"]`. Read the newest 20 citing snippets for negative phrases (overruled, abrogated, no longer good law, superseded, disapproved, declined to follow, limited). Use `search_document` on a citing opinion to pull the passage around the citation. Any hit escalates to the heavyweight check; record the screen in the ledger notes and label the case Screened (lightweight).

## 6. Typed citations for formatting

Search results give citation strings. For the Bluebook formatter, fetch the cluster record once with `get_endpoint_item` (endpoint `clusters`, fields `id, case_name, case_name_full, citations, date_filed, sub_opinions, absolute_url`). Its `citations[]` carries reporter types (1 federal, 2 official state, 3 regional, 8 neutral), and the ledger hook stores them.

## 7. Budget

A typical issue costs 1 semantic search, 2 to 4 keyword searches, 1 read per relied-on case, 1 sweep per case, and 1 cluster record per cited case. With 1,000 requests per hour that leaves wide margin; the 20-per-minute limit is the one to pace against.
