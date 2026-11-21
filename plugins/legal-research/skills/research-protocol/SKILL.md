---
name: research-protocol
description: "Trigger: any question about what the law is, whether a case or statute is still good law, what a statute or regulation requires, how a court would rule, or what authority supports a proposition; the start of any research, case-finding, statute lookup, memo, exam answer, or cite-check; any moment a holding, quotation, or citation is about to be stated. Do NOT load for: formatting a citation that is already ledgered (use citation-format); drafting from an approved outline whose authorities are all ledgered; questions about this repository's code, hooks, or plugin. Adapted in part from DingDuff Inc.'s legal research skill; modified, not official and not endorsed by DingDuff Inc."
license: "DingDuff Skills License 1.0 (https://www.dingduff.com/skills-license/1.0) for the portions adapted from DingDuff; LICENSE.md has complete terms"
allowed-tools: Read, Grep, Glob
---

> Portions of this skill adapt DingDuff Inc.'s "dingduff-legal-research" skill v2.7 (SKILL.md lines 13 to 23 and `references/validity.md`), https://www.dingduff.com. **Modified version, not official and not endorsed by DingDuff Inc.** Changes: rewritten for the CourtListener and Georgia Commons connectors, the authority ledger, and the citation gate in this plugin; the two-tier labels and verification checklist are kept in substance. License: DingDuff Skills License 1.0, full terms in `LICENSE.md`.

# Research protocol

These rules apply to every research step. The plugin's hooks enforce the ones marked **[gate]**; the rest depend on you.

## 1. Connection check

Before the first research call, confirm the CourtListener tools are present (a tool whose name ends in `__search` and `__read_document` with CourtListener's parameters). If CourtListener is missing, disconnected, or returns an authorization error, say exactly:

> CourtListener is disconnected, reconnect it before I proceed

and stop. Do not fall back to memory or web search for case law.

## 2. Sources of law

- Cite only authorities retrieved in this session or recorded in the matter's `authorities.json`. Memory and web search are never sources of law. **[gate]**
- Case law comes from CourtListener. Georgia statutes, constitution, and Supreme Court of Georgia opinions come from Georgia Commons. Federal statutes and regulations come from `uslaw-mcp` once it ships (Phase 2); until then use the interim path in the statute-research skill.
- Never drive Westlaw, Lexis+, Bloomberg Law, Justia, or Google Scholar with browser automation. Their KeyCite and Shepard's checks are done by hand, and results are recorded with `/ledger mark`. Their secondary sources arrive only through the `/secondary` relay (section 9).

## 3. Retrieve before you assert

- A search snippet supports one decision: whether to read the document. It never supports a holding, a quotation, or a characterization.
- Read the opinion with `read_document` before stating any holding. Read the statute section with `code_lookup_section` (or the federal equivalent) before quoting or paraphrasing it.
- If the text cannot be retrieved, say the authority was not read and do not discuss its substance.

## 4. Save and ledger everything

- Every retrieval is saved to the matter's `sources/` with a SHA-256 hash and recorded in `authorities.json` by the PostToolUse hook. **[gate]** Search hits enter as `candidate`; a full read promotes the entry to `retrieved` with `existence: verified`.
- Start every matter with `/research`, which creates `research/<course>/<assignment>/` and makes it the active matter. Retrievals made with no active matter land in `.session/inbox/`.
- Never edit `authorities.json` or `sources/` by hand. **[gate]** Use `/ledger`.
- Drafts under `drafts/` may carry only citations whose ledger entries are verified and, for cases, read. Bare "X v. Y" names in drafts need a full citation. **[gate]** Notes under `notes/` and `plan.md` are free.

## 5. Jurisdiction ladder

Work down the ladder and stop at the first binding authority that answers the question: constitution, statute, regulation, binding case law (the jurisdiction's highest court, then its intermediate court), then persuasive authority. Statutes and regulations first, because they define the elements; cases second, because they interpret them. State which rung each authority occupies.

## 6. Good law and the two tiers

The free databases do not flag overruled, abrogated, or superseded authority. Check every authority you rely on.

- **Lightweight (Screened):** an inline screen of recent citing opinions for negative treatment phrases (overruled, abrogated, no longer good law, superseded, declined to follow, limited). A clean screen is no evidence of validity.
- **Heavyweight (Verified):** the `validity-checker` subagent (`/validate`), proposition-specific, sequential, with its coverage limits stated. The lightweight screen is the `treatment-screen` skill.
- The test for heavyweight: does the answer change if this case is bad? If yes, escalate. Escalate anything the screen flags; never adjudicate a treatment signal from a snippet.
- Statutes and regulations: record the edition or `current_through` date and check for amendments after it.
- Every authority in a graded or filed document also gets a manual KeyCite or Shepard's check by the user, listed by `/ledger keycite-list`.

## 7. Labels in every output

Label every case as **Verified (heavyweight)** with the verdict, confidence, and proposition; **Screened (lightweight)** with what was screened; or **Not validated**. Add one line naming which cases were escalated and why. If no case received heavyweight validation, say so in those words.

## 8. Quota

Request `fields` on every CourtListener call. The EDU membership allows 1,000 requests per hour and 20 per minute. The SessionStart hook reports the remaining quota; plan reads before broad searches when it runs low.

## 9. Secondary sources: when to request one

Paywalled secondary sources (Restatements, Am. Jur. 2d, C.J.S., A.L.R., treatises, most law reviews) enter only through the Westlaw relay: the `secondary-source-request` skill and `/secondary`. Never automate Westlaw, Lexis+, or Bloomberg Law. A request is justified when at least one trigger holds (`docs/05-secondary-sources.md` section 2):

1. The operative rule is a Restatement or UCC section and the free path did not surface the section text as quoted by a court in the jurisdiction.
2. Primary authority in the controlling jurisdiction is thin: fewer than three on-point appellate opinions after two CourtListener rounds (one semantic, one keyword).
3. Retrieved cases state the rule inconsistently and a treatise's reconciliation would decide the synthesis.
4. The memo needs doctrinal history, policy rationale, or a defined term of art.
5. An element checklist or proof structure for a cause of action is needed.
6. The assignment itself calls for secondary sources.

Never in a closed-universe matter unless the assignment supplies the secondary source. Run the free path first and record it. Section numbers, titles, and authors appear in a request only when a retrieved primary source names them; everything else is "locate". A reported secondary source carries its disclosure label, for example "Manual (Westlaw), reported 2026-10-16", wherever it is cited.

## Verification pass before any answer or draft

- [ ] Every authority came from a retrieval this session or the ledger.
- [ ] Every case relied on was read in full with `read_document`.
- [ ] Every case carries a tier label, and every load-bearing case is escalated or flagged for escalation.
- [ ] Every statute carries its edition or currency date.
- [ ] No more recent controlling authority from the same or a higher court supersedes a case relied on.
- [ ] The KeyCite checklist covers every authority headed into graded or filed work.
- [ ] Every secondary source cited is `reported` in the ledger and carries its disclosure label.
