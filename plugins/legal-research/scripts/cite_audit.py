# /// script
# requires-python = ">=3.12"
# dependencies = ["eyecite==2.7.8", "reporters-db==3.2.67", "courts-db==0.10.27"]
# ///
"""Deterministic citation audit of a matter's drafts (architecture section 6, step 7; ADR-3).

  cite_audit.py <matter> [<draft> ...] [--html] [--quiet]

Checks every citation, [[src:<id> <pin>]] token, bare case name, and quotation in each draft under drafts/:
  red     no ledger entry; entry not read or not verified; name mismatch; bare case name; unreported secondary
          source; quotation that does not anchor in the cited source
  yellow  quotation without a pincite; pincite that disagrees with the quotation's star page; case still
          Not validated; KeyCite pending; secondary-source request still open
Red items block the Stop hook unless the ledger's `waivers` list holds them (the user's call, recorded with
`ledger.py waive`). Writes audit/cite-check.json and audit/toa.md; --html also writes audit/cite-check.html.
Exit 1 when unwaived red items remain.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import load_ledger, now_iso  # noqa: E402
from cite_extract import Cite, extract, quotations  # noqa: E402

ASSOC_CHARS = 400


def label(entry: dict) -> str:
    if entry.get("type") == "secondary":
        return entry.get("disclosure") or "Not reported"
    if entry.get("type") != "case":
        return "n/a"
    level = (entry.get("treatment") or {}).get("level")
    return {"heavyweight": "Verified (heavyweight)", "lightweight": "Screened (lightweight)"}.get(level, "Not validated")


def audience_mode(matter: Path) -> str:
    q = matter / "question.md"
    text = q.read_text(encoding="utf-8") if q.is_file() else ""
    m = re.search(r"^audience:\s*(.*)$", text, re.M)
    return "ga" if m and re.search(r"Georgia|Ga\.", m.group(1)) and re.search(r"court|filing|brief|motion", m.group(1), re.I) else "academic"


def pin_pages(pin: str | None) -> set[str]:
    if not pin:
        return set()
    pages = set()
    for part in re.split(r",\s*", pin):
        m = re.match(r"(\d+)(?:\s*[-–]\s*(\d+))?", part.strip())
        if m:
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            if hi < lo and m.group(2):  # 233-35 style
                hi = int(str(lo)[: len(str(lo)) - len(m.group(2))] + m.group(2))
            pages.update(str(p) for p in range(lo, min(hi, lo + 50) + 1))
    return pages


def item(severity: str, kind: str, text: str, start: int, detail: str, entry_id: str | None = None) -> dict:
    flat = re.sub(r"\s+", " ", text).strip()[:160]
    return {"severity": severity, "kind": kind, "text": text, "start": start, "detail": detail, "entry_id": entry_id,
            "key": f"{kind}:{flat}"}


def audit_text(matter: Path, text: str, ledger: dict) -> tuple[list[dict], list[Cite]]:
    from verify_anchors import anchor_for_entry

    entries = {e["id"]: e for e in ledger["authorities"]}
    cites = extract(text, ledger)
    items: list[dict] = []
    for c in cites:
        if c.problem:
            items.append(item("red", c.kind, c.text, c.start, c.problem, c.entry_id))
    # carry each case citation's entry forward so short forms and id. resolve to it
    last_case: Cite | None = None
    resolved: list[Cite] = []
    for c in cites:
        if c.kind in ("case", "token") and c.entry_id:
            last_case = c
        if c.kind == "id" and last_case:
            c.entry_id = last_case.entry_id
        resolved.append(c)
    citable_cites = [c for c in resolved if c.entry_id and c.kind in ("case", "short_case", "id", "token", "statute", "regulation", "secondary")]
    for q in quotations(text):
        para_end = text.find("\n\n", q.end)
        para_end = len(text) if para_end == -1 else para_end
        after = [c for c in citable_cites if q.end <= c.start <= min(q.end + ASSOC_CHARS, para_end)]
        before = [c for c in citable_cites if c.end <= q.start and q.start - c.end <= ASSOC_CHARS]
        c = after[0] if after else (before[-1] if before else None)
        if c is None:
            items.append(item("red", "quotation", q.text, q.start, "quotation with no citation to anchor it"))
            continue
        entry = entries.get(c.entry_id)
        res = anchor_for_entry(matter, entry, q.text) if entry else {"status": "anchor_failed", "reason": "no_ledger_entry"}
        if res["status"] != "anchored":
            items.append(item("red", "quotation", q.text, q.start, f"does not anchor in {c.entry_id} ({res.get('reason')})", c.entry_id))
            continue
        if entry.get("type") == "case":
            if not c.pin:
                items.append(item("yellow", "quotation", q.text, q.start,
                                  "quotation needs a pincite" + (f" (it starts on star page {res['page']})" if res.get("page") else ""),
                                  c.entry_id))
            elif res.get("page") and res["page"] not in pin_pages(c.pin):
                items.append(item("yellow", "quotation", q.text, q.start,
                                  f"pincite {c.pin}; the quotation starts on star page {res['page']}", c.entry_id))
    cited_ids = {c.entry_id for c in resolved if c.entry_id}
    for eid in sorted(cited_ids):
        e = entries.get(eid)
        if not e:
            continue
        if e.get("type") == "case" and label(e) == "Not validated":
            items.append(item("yellow", "label", eid, 0, "Not validated: run /validate --screen (or the heavyweight check for an anchor)", eid))
        mk = (e.get("treatment") or {}).get("manual_keycite") or {}
        if mk.get("required") and not mk.get("done"):
            items.append(item("yellow", "keycite", eid, 0, "manual KeyCite pending (/ledger keycite-list)", eid))
    for e in ledger["authorities"]:
        if e.get("type") == "secondary" and e.get("status") == "requested":
            items.append(item("yellow", "secondary_request", e["request_id"], 0, f"Westlaw request open: {(e.get('request') or {}).get('issue', '')}", e["id"]))
    return items, resolved


def toa(matter: Path, ledger: dict, cited_ids: set[str]) -> str:
    from bluebook_case import format_case

    mode = audience_mode(matter)
    groups: dict[str, list[str]] = {"Cases": [], "Constitutional Provisions and Statutes": [], "Regulations": [], "Secondary Sources": []}
    for e in ledger["authorities"]:
        if e["id"] not in cited_ids:
            continue
        cit = e.get("citation") or {}
        if e.get("type") == "case":
            groups["Cases"].append(f"{format_case(e, mode)['full']} [{label(e)}]")
        elif e.get("type") in ("statute", "constitution"):
            groups["Constitutional Provisions and Statutes"].append(cit.get("cite_as") or f"{cit.get('code')} § {cit.get('section')}")
        elif e.get("type") == "regulation":
            groups["Regulations"].append(cit.get("cite_as") or f"{cit.get('title')} {cit.get('code')} § {cit.get('section')}")
        elif e.get("type") == "secondary":
            groups["Secondary Sources"].append(f"{cit.get('bluebook')} [{e.get('disclosure')}]")
    lines = [f"# Table of authorities ({mode} form)", "", f"Generated {now_iso()} by cite_audit.py from the ledger.", ""]
    for g, rows in groups.items():
        if rows:
            lines += [f"## {g}", ""] + [f"- {r}" for r in sorted(rows, key=lambda r: r.lstrip('*').lower())] + [""]
    return "\n".join(lines)


def run(matter: Path, drafts: list[Path]) -> dict:
    ledger = load_ledger(matter)
    waived = {w.get("key") for w in ledger.get("waivers") or []}
    report = {"matter": matter.name, "generated_at": now_iso(), "drafts": [], "red": 0, "yellow": 0, "waived": 0}
    cited: set[str] = set()
    for d in drafts:
        text = d.read_text(encoding="utf-8")
        items, cites = audit_text(matter, text, ledger)
        for it in items:
            it["waived"] = it["key"] in waived
            if it["waived"]:
                report["waived"] += 1
            elif it["severity"] == "red":
                report["red"] += 1
            else:
                report["yellow"] += 1
        cited |= {c.entry_id for c in cites if c.entry_id}
        report["drafts"].append({"path": d.relative_to(matter).as_posix() if d.is_relative_to(matter) else str(d), "items": items,
                                 "citations": [{"kind": c.kind, "text": c.text, "start": c.start, "end": c.end,
                                                "entry_id": c.entry_id, "pin": c.pin} for c in cites]})
    audit = matter / "audit"
    audit.mkdir(exist_ok=True)
    (audit / "cite-check.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (audit / "toa.md").write_text(toa(matter, ledger, cited), encoding="utf-8", newline="\n")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("matter")
    ap.add_argument("drafts", nargs="*")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    matter = Path(a.matter).resolve()
    drafts = [Path(p).resolve() for p in a.drafts] or sorted((matter / "drafts").glob("**/*.md"))
    report = run(matter, drafts)
    if a.html:
        from audit_html import render

        render(matter, report)
    if not a.quiet:
        print(f"cite_audit: {len(drafts)} draft(s), {report['red']} red, {report['yellow']} yellow, {report['waived']} waived")
        for d in report["drafts"]:
            for it in d["items"]:
                if it["severity"] == "red" and not it["waived"]:
                    print(f"  RED {d['path']}: {it['text'][:80]!r}: {it['detail']}")
    return 1 if report["red"] else 0


if __name__ == "__main__":
    sys.exit(main())
