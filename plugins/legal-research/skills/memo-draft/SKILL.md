---
name: memo-draft
description: "Trigger: drafting or revising a memo, exam answer, brief section, or any prose under a matter's drafts/ folder; mode draft; a request to write up research the ledger already holds. Do NOT load for: finding or reading authorities (use research-protocol, case-law-research, statute-research); formatting one citation (use citation-format); deciding whether a case is good law (use treatment-screen or the validity-checker agent)."
allowed-tools: Read, Grep, Glob, Write, Edit, Bash
---

# Memo drafting

Draft from the ledger and the saved sources only. Every authority in the draft is `retrieved` in `authorities.json` (or a `reported` secondary source), and every statement of a holding comes from the saved text in `sources/`. The citation gate blocks a write that cites anything else.

## 1. Before writing

1. Read `question.md` (question, jurisdiction, audience, `closed_universe`) and `plan.md`.
2. Run `ledger.py show` and read each validity note in `notes/*-validity.md`. Build the authority list per issue: anchor cases (Verified (heavyweight)), supporting cases (Screened at least), statutes, and anything adverse.
3. Re-read the passages you will rely on in the saved opinion. Record the star page of each passage; the pin comes from the `*NNN` marker before it.

## 2. Structure per issue: CREAC

- **Conclusion.** One or two sentences that answer the issue.
- **Rule.** The statute first, then the governing case rule in the court's words, cited to the anchor case at the page that states it.
- **Explanation.** Two or three illustrations: facts, holding, and the reasoning that drives the rule, each from the saved text with pins.
- **Application.** The rule applied to the client's facts, fact by fact, with the analogous and the distinguishable cases named.
- **Conclusion.** The answer again, tied to the application.

Then a **Contrary authority** block for every issue, without exception: adverse holdings, limits the validity checks found (a later case that narrows or explains the rule, a statute that displaces it in one setting), and the strongest argument for the other side. When the searches found nothing adverse, say so and name the searches that ran.

## 3. Citations: tokens

Write each citation as a token, `[[src:<ledger-id> <pin>]]`, in the place the citation goes, and close the citation sentence with your own period:

```
An intervening wrongful act insulates the defendant unless the defendant had reason to anticipate it. [[src:cl-cluster-5749642 841]].
```

`render_memo.py` turns tokens into the full citation on first reference, *Id.* after a lone citation of the same authority, and the short form after that. Join a string citation with `; `. For a statute, the pin is the subsection: `[[src:gc-code-51-12-9 (a)]]`. Signals go before the token as words: `See [[src:...]]`.

Quote verbatim from the saved text, inside quotation marks, with the token right after the quoted sentence. Quotations of 50 words or more go in a block quote (`> `). Mark omissions with spaced ellipses (`. . .`) and alterations with brackets. The audit anchors every quotation in the cited source.

## 4. Audience modes

| Audience (from `question.md`) | Form | Citation mode |
|---|---|---|
| Legal Writing memo | Heading (To, From, Date, Re), Question Presented, Brief Answer, Facts, Discussion (CREAC per issue), Conclusion | `ga` for a Georgia question, else `academic` |
| Exam answer | Issue headings, IRAC per issue, short case names allowed after the first full cite | `academic` |
| Court filing | The court's required sections; parallel Georgia reporter cites | `ga` (Ga. Sup. Ct. R. 22(2), Ga. Ct. App. R. 24(d)) |

## 5. Voice

- Active voice, declarative sentences. Each sentence states a fact, a rule, a holding, or an application.
- No em dashes or long hyphens. No "X, not Y" constructions.
- State conclusions with confidence. Qualify only with a specific reason: a fact the record lacks, a split between courts, an open question a named case left open.
- Name cases, courts, years, and pages. A sentence about a holding names the case and the page.

## 6. Authority status

End the draft with an **Authority status** list: each case with its label (Verified (heavyweight), Screened (lightweight), or Not validated) and its KeyCite state from the ledger. Graded or filed work needs every load-bearing case Verified and KeyCited by the user.

## 7. Finish

1. Write the draft to `drafts/<name>.md`. A gate denial names the citation it rejected: ledger the authority or cut the sentence.
2. Run `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/cite_audit.py" <matter> --html` and fix every red item. Red items block the Stop hook; only the user waives one.
3. Run `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/render_memo.py" <matter> drafts/<name>.md --mode <mode>` for the finished `.docx` in `final/`.
4. Run `keycite_checklist.py <matter>` and hand the user the list.
