# legal-research plugin

v0.1 (Phase 1): citation gate, authority ledger, session hooks, four skills, five commands, two agents. Later components arrive in the phases listed in `../../docs/03-implementation-plan.md`. Hook payload field names are recorded in `../../docs/hook-payloads.md`. Hooks run scripts with `uv run --script`, so uv must be on PATH. Tests: `uv run pytest` from the repository root.

Planned layout:

```
.claude-plugin/plugin.json
.mcp.json                 georgiacommons (http) now; uslaw (stdio) in Phase 2. Create it by renaming mcp.json.example (remote sessions cannot write .mcp.json)
skills/
  research-protocol/      standing rules, loads in every session
  case-law-research/
  statute-research/
  regulation-research/
  treatment-screen/
  validity-check/         runs in a forked subagent on opus
  citation-format/        Indigo Book rules (vendored from DingDuff under its license) plus Bluebook 22 deltas and Georgia court rules
  cite-check/
  memo-draft/
commands/
  research.md  find-case.md  find-statute.md  validate.md  cite-check.md  bluebook.md  memo.md  ledger.md  sources.md
agents/
  authority-finder.md  validity-checker.md  citation-formatter.md  quote-verifier.md  counter-authority.md  memo-writer.md  memo-reviewer.md
hooks/
  hooks.json              SessionStart, PreToolUse (Edit|Write citation gate), PostToolUse (ledger ingest, changed files), Stop (citation audit)
scripts/
  ledger.py  cite_gate.py  cite_extract.py  bluebook_case.py  verify_anchors.py  treatment_screen.py  cite_audit.py  audit_html.py  keycite_checklist.py
```

CourtListener stays a claude.ai connector, which syncs into Claude Code. Do not add it here or two copies load.

Development: `claude --plugin-dir plugins/legal-research` from the repository root.
Install: `claude plugin marketplace add <repo path or owner/repo>` then `claude plugin install legal-research@alr`.
