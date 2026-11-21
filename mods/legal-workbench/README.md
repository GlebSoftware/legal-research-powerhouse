# legal-workbench

A Claude Code mod for this repository (ADR-9, `docs/04-harness.md`). Built in phases H0 to H3 of `docs/03-implementation-plan.md`.

Last verified against: Claude Code 2.1.301 (the CLI, `%USERPROFILE%\.local\bin\claude.exe`) and 2.1.299 (the build bundled with the Claude desktop app, `%APPDATA%\Claude\claude-code\2.1.299\`), 2026-10-16. The mod API is early access; after each Claude Code update, run validate and test again before relying on the mod.

## What it does (H0)

- `prompt.submit`: attaches a hidden context block to every plain prompt in a research workspace (a working directory holding `research/`): active matter path, question, jurisdiction, audience, closed-universe flag, ledger counts by status and disclosure label, the mode (`research`, `draft`, `cite`, `free`, from `$.store` key `mode`), and the protocol reminder. Slash commands and meta prompts pass untouched.
- `prompt.compose`: appends the protocol as a session-scope system section (`legal-workbench:protocol`) so it survives compaction. A bare prompt is left alone.

## Develop

```
claude --plugin-dir mods/legal-workbench
claude plugin validate mods/legal-workbench
claude plugin test mods/legal-workbench
```

The engine writes `.claude-plugin/types/` beside a loaded mod; it stays out of git. Install from the repo marketplace with `claude plugin install legal-workbench@alr`; a folder marketplace with a relative source is read from this folder, so `/reload-plugins` picks up edits.

Note: on a machine where an organization manages Claude Code, `prompt.compose` hooks run only for plugins listed in managed settings (`claude plugin validate` reports this).
