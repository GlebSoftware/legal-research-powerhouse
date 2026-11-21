---
description: "Check whether a ledgered case is still good law: lightweight screen for any case, heavyweight validity check for a load-bearing one"
argument-hint: "<ledger id or case name> [for \"<proposition>\"] [--screen]"
---

Validate: $ARGUMENTS

1. Find the case in the active matter's ledger (`ledger.py show --json`). It must be `retrieved` (read with `read_document`); if not, run `/find-case` first.
2. With `--screen`, or when no proposition is given: run the `treatment-screen` skill for the case and report its Screened (lightweight) line.
3. Otherwise delegate to the `validity-checker` agent with the ledger id, the full citation, cluster and opinion ids, the proposition, the target court from `question.md`, and the role (anchor, supporting, or adverse). Run one check at a time.
4. Report the verdict block verbatim and the label it earns: Verified (heavyweight), with verdict, confidence, and proposition. Remind the user that graded or filed work still needs their manual KeyCite (`/ledger keycite-list`).
