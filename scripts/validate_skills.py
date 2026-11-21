"""Validate SKILL.md, agent, and command frontmatter in every plugin under plugins/.

Catches the DingDuff issue #35 failure (an unquoted description containing a colon silently disabled a
skill) and enforces the CLAUDE.md frontmatter rules. Exit 1 on any error. Run: uv run scripts/validate_skills.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PORTABLE = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
CLAUDE_CODE_ONLY = {"context", "agent", "model", "hooks", "disable-model-invocation", "user-invocable",
                    "argument-hint", "effort", "background", "paths"}
AGENT_FIELDS = {"name", "description", "tools", "disallowedTools", "model", "maxTurns", "autoCompactWindow",
                "skills", "memory", "background", "omitClaudeMd", "effort", "isolation", "color", "experimental"}
AGENT_IGNORED = {"permissionMode", "mcpServers", "hooks", "initialPrompt"}
COMMAND_FIELDS = {"description", "argument-hint", "allowed-tools", "model", "disable-model-invocation"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def split_front(text: str) -> tuple[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    return text[4:end], text[end + 5:]


def raw_value_quoted(front: str, key: str) -> bool:
    for line in front.splitlines():
        if line.startswith(f"{key}:"):
            value = line.split(":", 1)[1].strip()
            return value[:1] in ("'", '"')
    return False


def check_file(path: Path, kind: str) -> list[str]:
    errs: list[str] = []
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    if "\r\n" in text:
        errs.append(f"{rel}: CRLF line endings")
        text = text.replace("\r\n", "\n")
    parts = split_front(text)
    if parts is None:
        return errs + [f"{rel}: missing or unterminated YAML frontmatter"]
    front, body = parts
    try:
        meta = yaml.safe_load(front)
    except yaml.YAMLError as exc:
        return errs + [f"{rel}: frontmatter is not valid YAML: {exc}"]
    if not isinstance(meta, dict):
        return errs + [f"{rel}: frontmatter is not a mapping"]
    desc = meta.get("description")
    if not isinstance(desc, str) or not desc.strip():
        errs.append(f"{rel}: description missing or not a string")
    elif not raw_value_quoted(front, "description"):
        errs.append(f"{rel}: description must be a quoted string (CLAUDE.md; DingDuff issue #35)")
    elif len(desc) > 1024:
        errs.append(f"{rel}: description is {len(desc)} characters; the limit is 1024")
    if not body.strip():
        errs.append(f"{rel}: empty body")
    keys = set(meta)
    if kind == "skill":
        name = meta.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            errs.append(f"{rel}: name must be lowercase words joined by hyphens")
        elif name != path.parent.name:
            errs.append(f"{rel}: name '{name}' differs from directory '{path.parent.name}'")
        cc_only = "claude code only" in str(meta.get("compatibility", "")).lower()
        allowed = PORTABLE | (CLAUDE_CODE_ONLY if cc_only else set())
        extra = keys - allowed
        if extra:
            hint = "" if cc_only else " (mark the skill 'Claude Code only' in compatibility to allow Claude Code fields)"
            errs.append(f"{rel}: frontmatter fields not allowed: {sorted(extra)}{hint}")
        if isinstance(desc, str) and not (desc.startswith("Trigger:") and "Do NOT load for:" in desc):
            errs.append(f"{rel}: description must be a trigger list ('Trigger: ...') plus a 'Do NOT load for: ...' "
                        f"list (docs/04-harness.md section 5.1)")
        if len(body.splitlines()) > 500:
            errs.append(f"{rel}: body exceeds 500 lines; move detail to references/")
    elif kind == "agent":
        name = meta.get("name")
        if not isinstance(name, str) or ":" in name or not NAME_RE.match(name):
            errs.append(f"{rel}: agent name must be lowercase words joined by hyphens")
        if keys & AGENT_IGNORED:
            errs.append(f"{rel}: fields ignored for plugin agents: {sorted(keys & AGENT_IGNORED)}")
        if keys - AGENT_FIELDS - AGENT_IGNORED:
            errs.append(f"{rel}: unknown agent fields: {sorted(keys - AGENT_FIELDS - AGENT_IGNORED)}")
    elif kind == "command":
        if keys - COMMAND_FIELDS:
            errs.append(f"{rel}: unknown command fields: {sorted(keys - COMMAND_FIELDS)}")
    return errs


def main() -> int:
    errors: list[str] = []
    count = 0
    for plugin in sorted((ROOT / "plugins").iterdir()):
        for path in sorted(plugin.glob("skills/*/SKILL.md")):
            errors += check_file(path, "skill"); count += 1
        for path in sorted(plugin.glob("agents/*.md")):
            errors += check_file(path, "agent"); count += 1
        for path in sorted(plugin.glob("commands/*.md")):
            errors += check_file(path, "command"); count += 1
    for e in errors:
        print(f"ERROR {e}")
    print(f"validate_skills: {count} files checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
