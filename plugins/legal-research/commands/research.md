---
description: "Start a research matter: create research/<course>/<assignment>/ with its question and jurisdiction, make it the active matter, and plan the research"
argument-hint: "<course>/<assignment> <question>"
---

Start a legal research matter from: $ARGUMENTS

The Home pane's New matter form does the same without a command. Both run `matter.py new`.

1. Load the `research-protocol` skill and run its connection check.
2. Parse the first token as `<course>/<assignment>`. Ask for it if it is missing.
3. Ask, in one message, only for what $ARGUMENTS leaves out: the question, the jurisdiction (default Federal; any state by name), the audience (Legal Writing memo, exam answer, court filing), and whether the assignment is a closed universe.
4. Create the matter and set it active:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/matter.py" new "<course>" "<assignment>" --question "<question>" --jurisdiction "<Federal or state>" --audience "<audience>" [--closed-universe]
   ```
   For a closed universe, add the supplied authorities to `question.md` under `universe:`, one line each, as given.
5. Write `plan.md`: issues, sub-issues, the authority types each needs (statute, regulation, binding case, persuasive), and the search plan. Statutes first. Use the courts in the context block's Courts line.
6. Report the matter path and the plan, then wait for the user's go-ahead before spending CourtListener quota.
