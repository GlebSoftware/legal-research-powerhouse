# /// script
# requires-python = ">=3.12"
# ///
"""Research matters for the workbench forms: create one, change its settings, list them. Spends zero quota.

  matter.py new <course> <name> --question "<text>" [--jurisdiction federal] [--audience "Legal Writing memo"]
                [--closed-universe]
  matter.py set <matter> <key>=<value>     keys: jurisdiction (an id or label from data/jurisdictions.json),
                                           audience, question, closed_universe (true or false), deadline
  matter.py list [--json]
  matter.py jurisdictions [--json]

A matter is research/<course>/<name>/ with question.md (front matter), plan.md, authorities.json, sources/, notes/,
drafts/, audit/. `new` makes it the active matter. Jurisdiction defaults to Federal.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import active_matter, ensure_matter, project_dir  # noqa: E402

JURISDICTIONS = Path(__file__).resolve().parents[1] / "data" / "jurisdictions.json"
AUDIENCES = ("Legal Writing memo", "Exam answer", "Court filing", "Research notes")
KEYS = ("question", "jurisdiction", "jurisdiction_id", "audience", "deadline", "closed_universe")


class MatterError(Exception):
    pass


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not s:
        raise MatterError(f"'{text}' has no letters or digits to name a folder with.")
    return s[:60]


def jurisdictions() -> list[dict]:
    return json.loads(JURISDICTIONS.read_text(encoding="utf-8"))["jurisdictions"]


def find_jurisdiction(value: str) -> dict:
    v = value.strip().lower()
    for j in jurisdictions():
        if v in (j["id"], j["label"].lower()) or (j["id"] == "federal" and v in ("fed", "federal", "united states", "u.s.")):
            return j
    raise MatterError(f"No jurisdiction '{value}'. Choose Federal or a state name.")


def read_front(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if kv:
            raw = kv.group(2).strip()
            try:
                meta[kv.group(1)] = json.loads(raw) if raw.startswith('"') else raw
            except ValueError:
                meta[kv.group(1)] = raw.strip('"')
    return meta, m.group(2)


def write_front(path: Path, meta: dict, body: str) -> None:
    lines = ["---"]
    for k in [*KEYS, *[k for k in meta if k not in KEYS]]:
        if k not in meta:
            continue
        v = meta[k]
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif v is None or v == "":
            v = "null"
        elif k in ("question", "audience", "jurisdiction") or re.search(r"[:#\"']", str(v)):
            v = json.dumps(str(v), ensure_ascii=False)
        lines.append(f"{k}: {v}")
    lines.append("---")
    path.write_text("\n".join(lines) + "\n" + (body if body.startswith("\n") or not body else "\n" + body),
                    encoding="utf-8", newline="\n")


def set_active(project: Path, matter: Path) -> None:
    marker = project / ".session" / "active-matter"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(matter.relative_to(project).as_posix() + "\n", encoding="utf-8", newline="\n")


def new(project: Path, course: str, name: str, question: str, jurisdiction: str = "federal",
        audience: str = "Legal Writing memo", closed: bool = False) -> Path:
    if not question.strip():
        raise MatterError("Write the research question first.")
    j = find_jurisdiction(jurisdiction)
    matter = project / "research" / slug(course) / slug(name)
    if (matter / "question.md").exists():
        raise MatterError(f"research/{slug(course)}/{slug(name)} already exists; switch to it or pick another name.")
    ensure_matter(matter)
    meta = {"question": question.strip(), "jurisdiction": j["label"], "jurisdiction_id": j["id"],
            "audience": audience, "deadline": None, "closed_universe": closed}
    body = ("\nCreated from the workbench. Claude writes plan.md when research starts.\n")
    write_front(matter / "question.md", meta, body)
    if not (matter / "plan.md").exists():
        (matter / "plan.md").write_text(f"# Plan: {name.strip()}\n\n## Issues\n\n- [ ] Issue 1: to be set when research "
                                        f"starts\n", encoding="utf-8", newline="\n")
    set_active(project, matter)
    return matter


def set_key(matter: Path, key: str, value: str) -> dict:
    path = matter / "question.md"
    if not path.is_file():
        raise MatterError(f"{matter.as_posix()} has no question.md.")
    meta, body = read_front(path)
    if key == "jurisdiction":
        j = find_jurisdiction(value)
        meta["jurisdiction"], meta["jurisdiction_id"] = j["label"], j["id"]
    elif key == "closed_universe":
        meta[key] = value.strip().lower() in ("true", "yes", "1")
    elif key in ("audience", "question", "deadline"):
        meta[key] = value.strip() or None
    else:
        raise MatterError(f"'{key}' is not a setting; use one of jurisdiction, audience, question, deadline, "
                          f"closed_universe.")
    write_front(path, meta, body)
    return meta


def listing(project: Path) -> list[dict]:
    active = active_matter(project)
    out = []
    root = project / "research"
    for q in sorted(root.glob("*/*/question.md")):
        m = q.parent
        meta, _ = read_front(q)
        try:
            ledger = json.loads((m / "authorities.json").read_text(encoding="utf-8"))
            n = len([e for e in ledger.get("authorities", []) if e.get("status") == "retrieved"])
        except (OSError, ValueError):
            n = 0
        out.append({"path": m.relative_to(project).as_posix(), "course": m.parent.name, "name": m.name,
                    "question": meta.get("question"), "jurisdiction": meta.get("jurisdiction") or "Federal",
                    "audience": meta.get("audience"), "retrieved": n,
                    "active": active is not None and active.resolve() == m.resolve()})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("course")
    n.add_argument("name")
    n.add_argument("--question", required=True)
    n.add_argument("--jurisdiction", default="federal")
    n.add_argument("--audience", default="Legal Writing memo")
    n.add_argument("--closed-universe", action="store_true")
    s = sub.add_parser("set")
    s.add_argument("matter")
    s.add_argument("pair")
    ls = sub.add_parser("list")
    ls.add_argument("--json", action="store_true")
    js = sub.add_parser("jurisdictions")
    js.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    project = project_dir()
    try:
        if a.cmd == "new":
            m = new(project, a.course, a.name, a.question, a.jurisdiction, a.audience, a.closed_universe)
            print(f"Created and switched to {m.relative_to(project).as_posix()}")
        elif a.cmd == "set":
            key, _, value = a.pair.partition("=")
            matter = Path(a.matter) if Path(a.matter).is_absolute() else project / a.matter
            meta = set_key(matter, key.strip(), value)
            print(f"{key.strip()} set: {meta.get(key.strip()) if key.strip() != 'jurisdiction' else meta['jurisdiction']}")
        elif a.cmd == "list":
            rows = listing(project)
            print(json.dumps(rows, indent=1, ensure_ascii=False) if a.json else
                  "\n".join(f"{'*' if r['active'] else '-'} {r['path']} ({r['jurisdiction']})" for r in rows) or "No matters.")
        else:
            rows = jurisdictions()
            print(json.dumps([{k: j[k] for k in ("id", "label")} for j in rows]) if a.json
                  else "\n".join(j["label"] for j in rows))
    except MatterError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
