# /// script
# requires-python = ">=3.12"
# dependencies = ["courts-db==0.10.27"]
# ///
"""Build data/jurisdictions.json: the jurisdiction picker's choices and the CourtListener court ids for each.

  uv run --script plugins/legal-research/scripts/build_jurisdictions.py [--uscode data/uscode/uscode.db]

Sources, both offline: courts-db 0.10.27 (Free Law Project; its ids are CourtListener's court ids) for every
current state appellate court and federal district court by location, and 28 U.S.C. § 41 from the local U.S. Code
mirror for the circuit that covers each state. Spends zero CourtListener quota. Rerun after a courts-db upgrade or
a new U.S. Code release point.

Each entry: id, label, binding (courts whose decisions bind in the jurisdiction), federal (the federal courts that
sit in it, for federal questions and diversity cases), statutes (where the codes come from), citation_mode.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
OUT = PLUGIN / "data" / "jurisdictions.json"
ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh"]
TERRITORIES = {"Puerto Rico", "Virgin Islands", "Guam", "District of the Canal Zone"}
STATUTES_FEDERAL = "uslaw-mcp: U.S. Code (local mirror), eCFR, Federal Register, GovInfo"
STATUTES_GEORGIA = "Georgia Commons: O.C.G.A. and the Georgia Constitution"
STATUTES_OTHER = "the state legislature's official code site, read with WebFetch, saved to sources/, ledgered with ledger.py upsert"


def circuits_from_41(text: str) -> dict[str, str]:
    """State -> circuit court id, from the composition table of 28 U.S.C. § 41."""
    body = text.split("Composition", 1)[-1]
    names = ["District of Columbia", *ORDINALS, "Federal"]
    pat = re.compile(rf"({'|'.join(map(re.escape, names))})(.+?)\.(?=\s*(?:{'|'.join(map(re.escape, names))})|\s*$)", re.S)
    out: dict[str, str] = {}
    for m in pat.finditer(body):
        name, members = m.group(1), m.group(2)
        if name == "Federal":
            continue
        cid = "cadc" if name == "District of Columbia" else f"ca{ORDINALS.index(name) + 1}"
        for member in (s.strip() for s in members.split(",")):
            if member and member not in TERRITORIES:
                out["Washington D.C." if member == "District of Columbia" else member] = cid
    return out


def current(c: dict) -> bool:
    return any(d.get("end") in (None, "") for d in (c.get("dates") or [{}]))


def dated(c: dict) -> bool:
    """courts-db leaves both dates empty on historical bodies (Saratoga Chancery Court, the Texas review tribunals)."""
    return any(d.get("start") for d in (c.get("dates") or [{}])) or c.get("level") in ("colr", "iac")


# courts-db's level and type fields are uneven (W.D.N.Y. is typed "appellate"), so courts are chosen by name and date.
DISTRICT_RE = re.compile(r"\bDistrict Court\b", re.I)
NOT_APPELLATE_RE = re.compile(r"Impeachment|Bankruptcy|Multidistrict", re.I)


def is_district(c: dict) -> bool:
    return DISTRICT_RE.search(c.get("name") or "") is not None and "Bankruptcy" not in (c.get("name") or "")


def build(courts: list[dict], circuits: dict[str, str]) -> dict:
    fed = [c for c in courts if c.get("system") == "federal" and current(c)]
    circuit_ids = sorted({c["id"] for c in fed if re.fullmatch(r"ca\d+|cadc|cafc", c["id"])},
                         key=lambda i: (len(i), i))
    districts = sorted(c["id"] for c in fed if is_district(c) and c.get("location") in circuits)
    corrected: list[str] = []
    entries = [{
        "id": "federal", "label": "Federal (all federal courts)", "binding": ["scotus", *circuit_ids],
        "federal": districts, "statutes": STATUTES_FEDERAL, "citation_mode": "academic",
    }]
    for state in sorted(circuits, key=lambda s: "District of Columbia" if s == "Washington D.C." else s):
        appellate = [c for c in courts if c.get("system") == "state" and c.get("location") == state and current(c)
                     and dated(c) and c.get("type") == "appellate" and not NOT_APPELLATE_RE.search(c.get("name") or "")]
        appellate.sort(key=lambda c: (c.get("level") != "colr", c["id"]))
        in_state = sorted(c["id"] for c in fed if c.get("location") == state and is_district(c))
        if not in_state:  # courts-db 0.10.27 ends the D.N.J. in 1801; keep the state's district courts regardless of date
            in_state = sorted(c["id"] for c in courts if c.get("system") == "federal" and c.get("location") == state
                              and is_district(c))
            corrected.extend(in_state)
        if state == "Washington D.C.":
            in_state = ["dcd"]
        label = "District of Columbia" if state == "Washington D.C." else state
        entries.append({
            "id": re.sub(r"[^a-z]+", "-", label.lower()).strip("-"), "label": label,
            "binding": [c["id"] for c in appellate], "federal": [circuits[state], *in_state],
            "statutes": STATUTES_GEORGIA if state == "Georgia" else STATUTES_OTHER,
            "citation_mode": "ga" if state == "Georgia" else "academic",
        })
    entries[0]["federal"] = sorted(set(entries[0]["federal"]) | set(corrected))
    return {"_about": "Built by scripts/build_jurisdictions.py from courts-db 0.10.27 and 28 U.S.C. § 41 "
                      "(local U.S. Code mirror). Court ids are CourtListener's.",
            "date_corrected": corrected, "default": "federal", "jurisdictions": entries}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uscode", default=str(REPO / "data" / "uscode" / "uscode.db"))
    a = ap.parse_args(argv)
    from courts_db import courts

    row = sqlite3.connect(a.uscode).execute("SELECT text FROM sections WHERE title='28' AND section='41'").fetchone()
    if not row:
        print(f"28 U.S.C. § 41 is not in {a.uscode}; build the U.S. Code mirror first", file=sys.stderr)
        return 1
    data = build(courts, circuits_from_41(row[0]))
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{OUT.relative_to(REPO).as_posix()}: {len(data['jurisdictions'])} jurisdictions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
