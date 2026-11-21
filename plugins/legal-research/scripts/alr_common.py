"""Shared helpers for the legal-research plugin scripts: paths, matters, ledger I/O, citation keys.

Standard library only, so every hook starts fast.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

LEDGER_NAME = "authorities.json"
SCHEMA_VERSION = 1
MATTER_DIRS = ("sources", "notes", "drafts", "audit")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def project_dir(payload: dict | None = None) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    if payload and payload.get("cwd"):
        return Path(payload["cwd"])
    return Path.cwd()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- matters


def find_matter_for_path(path: Path) -> Path | None:
    """Nearest ancestor of `path` that holds a ledger or a question.md."""
    for parent in [path, *path.parents]:
        if (parent / LEDGER_NAME).is_file() or (parent / "question.md").is_file():
            return parent
        if parent.name == "research":
            return None
    return None


def active_matter(project: Path) -> Path | None:
    """ALR_MATTER env var first, then .session/active-matter."""
    env = os.environ.get("ALR_MATTER", "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else project / p
    marker = project / ".session" / "active-matter"
    if marker.is_file():
        rel = marker.read_text(encoding="utf-8").strip()
        if rel:
            p = Path(rel)
            return p if p.is_absolute() else project / p
    return None


def inbox(project: Path) -> Path:
    """Holding matter for retrievals made while no matter is active."""
    return project / ".session" / "inbox"


def ensure_matter(matter: Path) -> None:
    matter.mkdir(parents=True, exist_ok=True)
    for d in MATTER_DIRS:
        (matter / d).mkdir(exist_ok=True)
    if not (matter / LEDGER_NAME).exists():
        save_ledger(matter, empty_ledger(matter))


# ---------------------------------------------------------------- ledger I/O


def empty_ledger(matter: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "matter": matter.name,
        "closed_universe": False,
        "created_at": now_iso(),
        "authorities": [],
    }


def load_ledger(matter: Path) -> dict:
    path = matter / LEDGER_NAME
    if not path.is_file():
        return empty_ledger(matter)
    return json.loads(path.read_text(encoding="utf-8"))


def save_ledger(matter: Path, ledger: dict) -> None:
    path = matter / LEDGER_NAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def ledger_lock(matter: Path, timeout: float = 20.0):
    """Exclusive lock file; parallel PostToolUse hooks serialize their ledger writes here."""
    matter.mkdir(parents=True, exist_ok=True)
    lock = matter / ".authorities.lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 60:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"ledger lock busy: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def get_entry(ledger: dict, entry_id: str) -> dict | None:
    for e in ledger["authorities"]:
        if e["id"] == entry_id:
            return e
    return None


def deep_merge(dst: dict, src: dict) -> dict:
    """Merge src into dst. Dicts merge recursively; None in src never overwrites a value."""
    for k, v in src.items():
        if v is None:
            dst.setdefault(k, None)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def upsert(ledger: dict, entry: dict) -> dict:
    existing = get_entry(ledger, entry["id"])
    if existing is None:
        ledger["authorities"].append(entry)
        return entry
    return deep_merge(existing, entry)


# ---------------------------------------------------------------- citation keys

_CITE_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s+(\d+)\s*$")


def norm_reporter(reporter: str) -> str:
    return re.sub(r"[\s.]", "", reporter).lower()


def parse_reporter_cite(cite: str) -> dict | None:
    """'638 S.E.2d 390' -> {'volume': '638', 'reporter': 'S.E.2d', 'page': '390'}."""
    m = _CITE_RE.match(cite)
    if not m:
        return None
    return {"volume": m.group(1), "reporter": m.group(2), "page": m.group(3)}


def case_key(volume: str, reporter: str, page: str) -> str:
    return f"case|{volume}|{norm_reporter(reporter)}|{page}"


def volume_key(volume: str, reporter: str) -> str:
    return f"vol|{volume}|{norm_reporter(reporter)}"


def strip_subsections(section: str) -> str:
    return re.sub(r"(\([^)]*\))+$", "", section.strip())


def ocga_key(section: str) -> str:
    return f"ocga|{strip_subsections(section)}"


def usc_key(title: str, section: str) -> str:
    return f"usc|{title}|{strip_subsections(section)}"


def cfr_key(title: str, section: str) -> str:
    return f"cfr|{title}|{strip_subsections(section)}"


def fr_key(volume: str, page: str) -> str:
    return f"fr|{volume}|{page}"


def entry_keys(entry: dict) -> set[str]:
    """Every lookup key an entry answers to."""
    keys: set[str] = set()
    cit = entry.get("citation") or {}
    for r in cit.get("reporters") or []:
        keys.add(case_key(r["volume"], r["reporter"], r["page"]))
        keys.add(volume_key(r["volume"], r["reporter"]))
    code = (cit.get("code") or "").lower()
    section = cit.get("section")
    if section:
        if code in ("o.c.g.a.", "ocga", "ga. code ann."):
            keys.add(ocga_key(section))
        elif code == "u.s.c." and cit.get("title"):
            keys.add(usc_key(str(cit["title"]), section))
        elif code == "c.f.r." and cit.get("title"):
            keys.add(cfr_key(str(cit["title"]), section))
        elif code == "fed. reg." and cit.get("title"):
            keys.add(fr_key(str(cit["title"]), str(section)))
    return keys


def index_ledger(ledger: dict) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for e in ledger["authorities"]:
        for k in entry_keys(e):
            idx.setdefault(k, []).append(e)
    return idx


_NAME_STOP = {"v", "the", "of", "and", "inc", "co", "corp", "llc", "ltd", "in", "re", "ex", "rel", "et", "al", "a", "an"}


def name_tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in _NAME_STOP and len(t) > 1}
