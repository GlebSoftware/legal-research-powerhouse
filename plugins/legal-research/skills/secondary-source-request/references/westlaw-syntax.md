# Westlaw search syntax

Sources, fetched 2026-10-16 with WebFetch:

1. Thomson Reuters, Westlaw Precision help, "Search with Terms and Connectors": https://www.thomsonreuters.com/en-us/help/westlaw-precision/searching/search-with-terms-and-connector-0/search-with-terms-and-connectors.html (the Westlaw Edge page at https://www.thomsonreuters.com/en-us/help/westlaw-edge/searching/search-with-terms-and-connectors.html carries the same content).
2. Thomson Reuters Law School, "Terms & Connectors": https://lawschool.thomsonreuters.com/advanced-searching/
3. Thomson Reuters, Westlaw Precision help, "Thesaurus": https://www.thomsonreuters.com/en-us/help/westlaw-precision/searching/thesaurus.html

Everything below restates those pages. Nothing here comes from memory. If an operator is not listed here, do not use it in a request; ask the user to check it on screen.

## Expanders

| Symbol | Effect | Example from the source |
|---|---|---|
| `!` | Root expander: matches every ending of the root | `object!` finds object, objected, objection, objecting (1) |
| `*` | Universal character: stands for one variable letter | `withdr*w` finds withdraw, withdrew (1) |
| `#` | Exact form: suppresses automatic endings | `#damage` finds damage, skips damages (1) |

Source 1 also advises adding variant forms by hand, for example "liable" and "liability".

## Grammatical and numerical connectors

| Connector | Effect | Example from the source |
|---|---|---|
| `/s` | Same sentence | `design /s defect` (1) |
| `+s` | First term precedes the second in the same sentence | `attorney +s fee` (1) |
| `/p` | Same paragraph | `hearsay /p utterance` (1) |
| `+p` | First term precedes the second in the same paragraph | `ti(burke +p burke)` (1) |
| `/n` | Within n terms, n from 1 to 255 | `personal /3 jurisdiction` (1); `attractive /5 nuisance` (2) |
| `+n` | First term precedes the second by n terms, n from 1 to 255 | `capital +3 gain` (1) |
| `%` | BUT NOT: excludes documents containing the terms after it | `tax taxation % income /3 tax taxation` (1) |

## AND, OR, and phrases

- Source 2 shows `OR` ("either (or both) of your terms within a document", example `attractive OR nuisance`), `AND` ("two or more terms that must appear anywhere in the document", example `attractive AND nuisance`), and quotation marks for an exact phrase (`"attractive nuisance"`). Its sample searches also join terms with `&`, for example `TO(contract & employment) & employ! /p ...`.
- Source 1 states: "Use Advanced Search if you want to use an AND connector (&) or an OR connector (represented by a space) in Westlaw," and "Use Advanced Search if you want to add alternative terms to your query or search for a phrase in Westlaw."
- Rule for requests, to satisfy both: a query that uses `&`, `OR`, a space as OR, or a quoted phrase is labeled "Advanced Search" in the request block. A query built only from terms, expanders, and the connectors in the table above is labeled "Terms and Connectors". Processing order of mixed connectors is not documented in either source, so requests group alternatives in parentheses as source 2's samples do and never rely on precedence.

## Field restrictions

Source 2: "All documents on Westlaw are broken into parts called fields."

| Field | What it searches (source 2) | Example from the source |
|---|---|---|
| `SY,DI` | Synopsis and digest: the summary and headnotes of cases | `SY,DI(attractive /5 nuisance)` |
| `PR,CA` | Preliminary and caption: major headings and the description of each statute | `PR,CA(attractive /5 nuisance)` |
| `WP` | Words and phrases: definitions of terms in statutes and cases | `WP(attractive /5 nuisance)` |
| `TI` | Appears in source 1's `+p` example, `ti(burke +p burke)`, without explanation | |
| `TO`, `IN` | Appear in source 2's sample searches (`TO(evidence)`, `in(law lawsuit legal)`, which source 2 calls an "index field") without explanation | |

`SY,DI` targets West editorial text. Requests may use it to find a source; the user brings back citations only and never pastes the synopsis or headnotes (report-template.md).

## Thesaurus

Source 3: in Advanced Search, enter terms under "All of these terms" or "Any of these terms," choose the option to add synonyms and related concepts, pick Synonyms or Related concepts for a term, check the terms to include, and run the search. Requests may suggest it when a term of art has known variants.
