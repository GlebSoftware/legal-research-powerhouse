# /// script
# requires-python = ">=3.12"
# dependencies = ["reporters-db==3.2.67", "courts-db==0.10.27"]
# ///
"""KeyCite and Shepard's checklist for the user's manual check (architecture ADR-5, section 4 step 8).

  keycite_checklist.py <matter>   writes audit/keycite-checklist.md and prints it

Every authority whose manual check is required and not done, sorted by weight: load-bearing (heavyweight-checked)
first, then cases the screen flagged, then by how often the drafts cite it, then by court level. Results go back
with `ledger.py mark <matter> <id> keycite=<result>`, which moves the item to Done. Claude never runs KeyCite or
Shepard's; Westlaw and Lexis are manual only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import load_ledger, now_iso  # noqa: E402

COURT_WEIGHT = {"scotus": 3, "colr": 2, "iac": 1}


def court_weight(court_id: str | None) -> int:
    if court_id == "scotus":
        return 3
    try:
        from courts_db import courts

        level = next((c.get("level") for c in courts if c["id"] == court_id), None)
    except Exception:
        level = None
    return COURT_WEIGHT.get(level or "", 0)


def cite_counts(matter: Path) -> dict[str, int]:
    p = matter / "audit" / "cite-check.json"
    counts: dict[str, int] = {}
    if p.is_file():
        for d in json.loads(p.read_text(encoding="utf-8")).get("drafts", []):
            for c in d.get("citations", []):
                if c.get("entry_id"):
                    counts[c["entry_id"]] = counts.get(c["entry_id"], 0) + 1
    return counts


# Westlaw's find-by-citation link, as Cornell LII's "Read It Online" tool builds it (law.cornell.edu/rio, fetched
# 2026-10-17); the mod's Authorities pane uses the same link for its Open in Westlaw button.
WESTLAW_FIND = "https://a.next.westlaw.com/Link/Document/FullText?findType=Y&cite="


def westlaw_url(e: dict) -> str | None:
    cit = e.get("citation") or {}
    if e.get("type") == "case":
        rep = next((r for r in cit.get("reporters") or []
                    if not re.search(r"LEXIS|WL|Fulton County|U\.S\.L\.W\.", str(r.get("reporter")))), None)
        cite = f"{rep['volume']} {rep['reporter']} {rep['page']}" if rep else None
    elif e.get("type") == "secondary":
        cite = None
    else:
        cite = re.sub(r"\s*\(\d{4}\)\s*$", "", cit.get("cite_as") or "") or None
    return WESTLAW_FIND + quote(cite, safe="") if cite else None


def describe(matter: Path, e: dict) -> str:
    cit = e.get("citation") or {}
    if e.get("type") == "case":
        from bluebook_case import format_case

        return format_case(e, "academic")["full"]
    return cit.get("cite_as") or cit.get("bluebook") or e["id"]


def build(matter: Path) -> str:
    ledger = load_ledger(matter)
    counts = cite_counts(matter)
    pending, done = [], []
    for e in ledger["authorities"]:
        if e.get("status") not in ("retrieved", "reported"):
            continue
        mk = (e.get("treatment") or {}).get("manual_keycite") or {}
        if not mk.get("required"):
            continue
        tr = e.get("treatment") or {}
        weight = (100 if tr.get("level") == "heavyweight" else 0) + (50 if tr.get("flags") else 0) \
            + 10 * counts.get(e["id"], 0) + court_weight((e.get("citation") or {}).get("court_id"))
        (done if mk.get("done") else pending).append((weight, e, mk))
    pending.sort(key=lambda t: (-t[0], t[1]["id"]))
    lines = [f"# KeyCite and Shepard's checklist: {matter.name}", "",
             f"Generated {now_iso()}. Run KeyCite (Westlaw) or Shepard's (Lexis) by hand on each authority, then record "
             f"the result: `uv run --script <plugin>/scripts/ledger.py mark \"{matter.as_posix()}\" <id> \"keycite=<flag and note>\"`.", ""]
    lines += ["## Pending", ""] if pending else ["## Pending", "", "None.", ""]
    for weight, e, _mk in pending:
        tr = e.get("treatment") or {}
        why = []
        if tr.get("level") == "heavyweight":
            why.append(f"load-bearing; verdict {tr.get('verdict')}")
        elif tr.get("level") == "lightweight":
            why.append("Screened (lightweight)")
        elif e.get("type") == "case":
            why.append("Not validated")
        else:
            why.append(f"{e.get('type')}; check currency and history")
        if tr.get("flags"):
            why.append(f"{len(tr['flags'])} screen flag(s)")
        if counts.get(e["id"]):
            why.append(f"cited {counts[e['id']]}x in drafts")
        link = westlaw_url(e)
        lines.append(f"- [ ] `{e['id']}` {describe(matter, e)} ({'; '.join(why)})" + (f" [Open in Westlaw]({link})" if link else ""))
    if done:
        lines += ["", "## Done", ""]
        for _w, e, mk in sorted(done, key=lambda t: t[1]["id"]):
            lines.append(f"- [x] `{e['id']}` {describe(matter, e)}: {mk.get('result')} ({mk.get('date')})")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    matter = Path(args[0]).resolve()
    text = build(matter)
    (matter / "audit").mkdir(exist_ok=True)
    (matter / "audit" / "keycite-checklist.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
