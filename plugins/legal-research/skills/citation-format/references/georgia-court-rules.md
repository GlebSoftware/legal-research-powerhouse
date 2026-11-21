# Georgia court citation rules

Addition to the modified citation-format skill; not part of the DingDuff original.

Status: the rule text is not yet retrieved into this repository. The requirements below come from the planning research recorded in `docs/02-architecture.md` (ADR-7). Before formatting a document that will be filed, retrieve the current Supreme Court of Georgia Rules and Court of Appeals of Georgia Rules from the courts' own sites, save them to the matter's `sources/`, and confirm each line below against the saved text.

## Which reporter to cite

| Document | Reporter | Basis |
|---|---|---|
| Filed in the Supreme Court of Georgia | Official reporter (Ga., Ga. App.) first; add the S.E. or S.E.2d parallel | Sup. Ct. of Ga. R. 22(2); parallel by practice |
| Filed in the Court of Appeals of Georgia | Official reporter (Ga., Ga. App.) first; add the S.E. or S.E.2d parallel | Ct. App. of Ga. R. 24(d); parallel by practice |
| Academic work, Legal Writing memo, non-Georgia court | Regional reporter (S.E., S.E.2d) with the court and year in the parenthetical | Indigo Book T3: "Supreme Court (Ga.): Cite to S.E. or S.E.2d" |

Forms the `bluebook_case.py` formatter will emit (Phase 2), shown with the Test 1 case read this session (ledger `cl-cluster-1266402`):

- Georgia filing: *Becks v. Pierce*, 282 Ga. App. 229, 638 S.E.2d 390 (2006).
- Academic: *Becks v. Pierce*, 638 S.E.2d 390 (Ga. Ct. App. 2006).

## Known data gap

CourtListener holds no S.E.2d cites for Georgia opinions from 2024 forward (cluster 10680227 carries only `320 Ga. 381`; 2026 opinions carry docket numbers only). For those, emit the slip form (case name, docket number, court, exact date) and flag the citation for manual completion from Westlaw or Lexis by hand.
