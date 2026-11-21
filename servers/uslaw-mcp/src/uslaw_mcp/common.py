"""Shared plumbing: repository paths, API keys, the active matter, saving sources, the result envelope.

Every document tool returns {text, source_url, retrieved_at, version_or_date, sha256, local_path, ledger_hint}
and saves the document to the active matter's sources/ with a manifest line, using the same layout as the
plugin's ledger.py, so the PostToolUse ingest hook records the entry without saving the text twice.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "uslaw-mcp/0.1 (personal legal research; contact via repository owner)"
RETURN_CHARS = 60_000


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_root() -> Path:
    env = os.environ.get("ALR_REPO") or os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (Path(env) / "research").is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "research").is_dir() and (parent / ".claude-plugin").is_dir():
            return parent
    return Path.cwd()


def env_value(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    path = repo_root() / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def active_matter() -> Path:
    root = repo_root()
    env = os.environ.get("ALR_MATTER", "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else root / p
    marker = root / ".session" / "active-matter"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip():
        p = Path(marker.read_text(encoding="utf-8").strip())
        return p if p.is_absolute() else root / p
    return root / ".session" / "inbox"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", text.lower()).strip("-")


def save_source(entry_id: str, text: str, ext: str, meta: dict) -> tuple[str, str, str]:
    """Write sources/<entry_id><ext> in the active matter; return (matter path, relative path, sha256)."""
    matter = active_matter()
    sources = matter / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    rel = f"sources/{entry_id}{ext}"
    (matter / rel).write_text(text, encoding="utf-8", newline="\n")
    digest = sha256_text(text)
    line = {"path": rel, "sha256": digest, "bytes": len(text.encode("utf-8")), "retrieved_at": now_iso(),
            "id": entry_id, "tool": meta.get("tool"), "system": meta.get("system"), **{k: v for k, v in meta.items() if k not in ("tool", "system")}}
    with (sources / "manifest.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    try:
        mrel = matter.resolve().relative_to(repo_root().resolve()).as_posix()
    except ValueError:
        mrel = str(matter)
    return mrel, rel, digest


def html_to_text(markup: str) -> str:
    """Plain text from XML or HTML: block tags become line breaks, entities decoded."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", markup)
    t = re.sub(r"(?i)<\s*(br|/p|/div|/head|/h\d|/li|/tr|/fp|/extract|/note)\b[^>]*>", "\n", t)
    t = re.sub(r"(?i)<\s*(p|div|head|h\d|li|tr|fp)\b[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)  # control characters in some FR raw text
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def envelope(*, entry_id: str, text: str, ext: str, system: str, tool: str, source_url: str,
             version_or_date: str | None, ledger_hint: dict, extra: dict | None = None) -> dict:
    """Save the document and build the tool result."""
    matter, rel, digest = save_source(entry_id, text, ext, {"tool": tool, "system": system, "source_url": source_url,
                                                          "version_or_date": version_or_date})
    truncated = len(text) > RETURN_CHARS
    out = {
        "system": system,
        "text": text[:RETURN_CHARS],
        "text_truncated": truncated,
        "total_chars": len(text),
        "source_url": source_url,
        "retrieved_at": now_iso(),
        "version_or_date": version_or_date,
        "sha256": digest,
        "matter": matter,
        "local_path": rel,
        "ledger_hint": {"id": entry_id, **ledger_hint},
    }
    if truncated:
        out["note"] = f"Text truncated at {RETURN_CHARS} characters; the full text is saved at {matter}/{rel}."
    out.update(extra or {})
    return out
