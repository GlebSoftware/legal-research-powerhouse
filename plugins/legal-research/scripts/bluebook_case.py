# /// script
# requires-python = ">=3.12"
# dependencies = ["reporters-db==3.2.67", "courts-db==0.10.27"]
# ///
"""Bluebook case citations from ledger data (architecture ADR-7).

Builds the full citation and the short form for one ledger entry in one of two modes:
  academic   regional reporter for state cases (Indigo T3), court and year in the parenthetical
  ga         Georgia filing: official Georgia reporter first with the S.E. parallel (Sup. Ct. R. 22(2),
             Ct. App. R. 24(d); see skills/citation-format/references/georgia-court-rules.md)
Federal cases take the same form in both modes. A case with no reporter cite gets the slip form
(case name, docket number, court, exact date). Everything comes from the entry: nothing from memory.

Usage: bluebook_case.py <matter> <entry-id> [--mode academic|ga] [--pin N] [--pin-reporter "Ga. App."] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "case_name_abbreviations.json"
MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
GEORGIA_COURTS = {"ga", "gactapp"}
SCOTUS_ORDER = ["U.S.", "S. Ct.", "L. Ed. 2d", "L. Ed."]
CORP_WORDS = {"Inc.", "Co.", "Corp.", "Ltd.", "LLC", "L.L.C.", "LLP", "L.P.", "N.A."}


@lru_cache(maxsize=1)
def abbreviations() -> dict:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    table = {**data["indigo-list"], **data["additions"]}
    return {"table": table, "generic": set(data["generic_parties"]), "values": set(table.values())}


@lru_cache(maxsize=1)
def reporter_kinds() -> dict[str, str]:
    """Edition abbreviation -> 'federal' | 'state' | 'state_regional' | other cite_type, from reporters-db."""
    from reporters_db import REPORTERS

    kinds: dict[str, str] = {}
    for root, entries in REPORTERS.items():
        for e in entries:
            for edition in (e.get("editions") or {}):
                kinds.setdefault(edition, e.get("cite_type", "unknown"))
            for variation, canonical in (e.get("variations") or {}).items():
                kinds.setdefault(variation, e.get("cite_type", "unknown"))
    return kinds


@lru_cache(maxsize=1)
def courts_index() -> dict[str, dict]:
    from courts_db import courts

    return {c["id"]: c for c in courts}


def kind_of(rep: dict) -> str | None:
    """Reporter class: CourtListener's type when present (1 federal, 2 state, 3 regional), else reporters-db."""
    t = rep.get("type")
    if t in (1, 5):
        return "federal"
    if t == 2:
        kind = reporter_kinds().get(rep["reporter"])
        return "state" if kind in (None, "state") else kind
    if t == 3:
        return "state_regional"
    kind = reporter_kinds().get(rep["reporter"])
    if "LEXIS" in rep["reporter"] or rep["reporter"] == "WL":
        return None
    return kind if kind in ("federal", "state", "state_regional") else None


def cite_str(rep: dict, pin: str | None = None) -> str:
    return f"{rep['volume']} {rep['reporter']} {rep['page']}" + (f", {pin}" if pin else "")


# ---------------------------------------------------------------- case names


def _abbreviate_words(party: str) -> str:
    table = abbreviations()["table"]
    out = []
    for tok in party.split(" "):
        core = tok.rstrip(",")
        tail = tok[len(core):]
        out.append(table.get(core, core) + tail)
    return " ".join(out)


def _individual(party: str) -> tuple[str, bool]:
    """(surname, was_changed) when the party reads as a person's full name; else (party, False)."""
    ab = abbreviations()
    toks = party.split()
    if not 2 <= len(toks) <= 4 or any(t.rstrip(",") in ab["table"] or t.rstrip(",") in ab["values"]
                                       or t.rstrip(",") in CORP_WORDS or t in ab["generic"] for t in toks):
        return party, False
    suffix = toks[-1] if toks[-1].rstrip(".") in ("Jr", "Sr", "II", "III", "IV") else None
    names = toks[:-1] if suffix else toks
    if all(re.fullmatch(r"[A-Z]\.", t.rstrip(",")) for t in names):  # a party named by initials (a minor): keep all
        return party, False
    if not all(re.fullmatch(r"[A-Z][a-z'’]+|[A-Z]\.", t.rstrip(",")) for t in names):
        return party, False
    return names[-1].rstrip(","), True


SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to"}
KEEP_CAPS = {"LLC", "L.L.C.", "LLP", "L.L.P.", "LP", "L.P.", "P.C.", "PC", "N.A.", "USA", "U.S.", "II", "III", "IV"}


def _title_case(name: str) -> str:
    """CourtListener's newer clusters carry the caption in capitals ('JOHNSON v. AVIS RENT a CAR SYSTEM, LLC')."""
    out = []
    for i, tok in enumerate(name.split(" ")):
        core = tok.rstrip(",")
        tail = tok[len(core):]
        if core in KEEP_CAPS or core == "v.":
            out.append(tok)
        elif i and core.lower() in SMALL_WORDS:
            out.append(core.lower() + tail)
        else:
            out.append("-".join(w[:1].upper() + w[1:].lower() for w in core.split("-")) + tail)
    return " ".join(out)


def case_name(raw: str) -> tuple[str, list[str]]:
    """Citation-clause case name and flags."""
    flags: list[str] = []
    name = re.sub(r"\s+", " ", raw).strip()
    name = re.sub(r"\s*\((?:Two|Three|Four|\d+) Cases\)$", "", name)  # consolidated-appeal tag, not part of the name
    letters = [c for c in name if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        name = _title_case(name)
        flags.append("caption arrived in capitals: confirm the capitalization of each party name")
    # Bluebook R10.2.1(b): omit an alternative name given after "d/b/a".
    name = re.sub(r",?\s+d/b/a\s+.*?(?=\s+v\.\s|$)", "", name, flags=re.I)
    m = re.match(r"^(?:In the Matter of|Matter of|In re:?)\s+(.*)$", name, re.I)
    if m:
        person, changed = _individual(re.sub(r",?\s+(Jr|Sr)\.?$", "", m.group(1)))
        if changed:
            flags.append(f"given names dropped from '{m.group(1)}': confirm the surname")
        return f"In re {_abbreviate_words(person)}", flags
    parties = name.split(" v. ")
    out = []
    for p in parties:
        person, changed = _individual(p)
        if changed:
            flags.append(f"given names dropped from '{p}': confirm the surname")
        q = _abbreviate_words(person)
        if re.search(r"\b(Co\.|Corp\.|Ltd\.|Ass'n|Bros\.)", q.replace(", Inc.", "")) and q.endswith(", Inc."):
            q = q[: -len(", Inc.")]
        out.append(q)
    return " v. ".join(out), flags


def short_party(full_name: str) -> str:
    if full_name.startswith("In re "):
        return full_name
    parties = full_name.split(" v. ")
    generic = abbreviations()["generic"]
    first = parties[0]
    if (first in generic or first.startswith(("City of", "State of", "County of"))) and len(parties) > 1:
        first = parties[1]
    return re.sub(r",? (Inc\.|Ltd\.|LLC|L\.L\.C\.)$", "", first)


# ---------------------------------------------------------------- dates and courts


def exact_date(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def court_string(court_id: str | None) -> str | None:
    c = courts_index().get(court_id or "")
    return c.get("citation_string") if c else None


def official_identifies_court(rep: dict, court_id: str) -> bool:
    """An official state reporter that names the court (Ga. for ga, Ga. App. for gactapp) drops it."""
    cs = court_string(court_id) or ""
    c = courts_index().get(court_id, {})
    if c.get("level") == "colr":
        return rep["reporter"] == cs
    state = cs.split(" ")[0]
    return c.get("level") == "iac" and rep["reporter"].startswith(f"{state} App")


# ---------------------------------------------------------------- the citation


def format_case(entry: dict, mode: str = "academic", pin: str | None = None, pin_reporter: str | None = None,
                textual: bool = False) -> dict:
    cit = entry.get("citation") or {}
    flags: list[str] = []
    name, name_flags = case_name(cit.get("case_name") or cit.get("case_name_full") or "")
    flags += name_flags
    if textual:
        flags.append("textual sentence: spell out abbreviations other than &, Ass'n, Bros., Co., Corp., Inc., Ltd., No.")
    court_id = cit.get("court_id") or ""
    year = (cit.get("date_filed") or "")[:4]
    reps = [r for r in cit.get("reporters") or [] if kind_of(r)]
    by_kind: dict[str, list[dict]] = {}
    for r in reps:
        by_kind.setdefault(kind_of(r), []).append(r)

    chosen: list[dict] = []
    if court_id == "scotus":
        for abbr in SCOTUS_ORDER:
            hit = next((r for r in reps if r["reporter"] == abbr), None)
            if hit:
                chosen = [hit]
                break
    elif by_kind.get("federal"):
        chosen = [by_kind["federal"][0]]
    else:
        official, regional = (by_kind.get("state") or [None])[0], (by_kind.get("state_regional") or [None])[0]
        if mode == "ga" and court_id in GEORGIA_COURTS and official:
            chosen = [official] + ([regional] if regional else [])
            if not regional:
                flags.append("S.E. parallel missing: complete by hand")
        else:
            chosen = [regional or official] if (regional or official) else []

    if not chosen:  # slip form
        docket = cit.get("docket_number")
        cs = court_string(court_id) or court_id
        when = exact_date(cit["date_filed"]) if cit.get("date_filed") else "date unknown"
        if not docket:
            flags.append("docket number missing")
        flags.append("reporter cite missing: slip form; complete by hand")
        full = f"*{name}*, No. {docket or '___'} ({'' if court_id == 'scotus' else cs + ' '}{when})"
        short = f"*{short_party(name)}*, No. {docket or '___'}"
        return {"full": full + ".", "short": short + ".", "flags": flags, "mode": mode, "reporters": []}

    # pin goes on the reporter it belongs to (the star pagination's), else the first
    target = pin_reporter or chosen[0]["reporter"]
    pins = {r["reporter"]: (pin if r["reporter"] == target else None) for r in chosen}
    if pin and target not in pins:
        flags.append(f"pin {pin} is a {target} page and this form cites {chosen[0]['reporter']}: confirm the pin by hand")
    if not pin:
        flags.append("pincite missing")
    if mode == "ga" and len(chosen) == 2 and pin and target == chosen[0]["reporter"]:
        flags.append(f"{chosen[1]['reporter']} pin missing: add it by hand if the court expects parallel pins")

    first = chosen[0]
    if court_id == "scotus":
        paren = year
    elif kind_of(first) == "state" and official_identifies_court(first, court_id):
        paren = year
    else:
        paren = f"{court_string(court_id) or court_id} {year}".strip()
    body = ", ".join(cite_str(r, pins.get(r["reporter"])) for r in chosen)
    full = f"*{name}*, {body} ({paren})."
    short_rep = next((r for r in chosen if pins.get(r["reporter"])), first)
    short = f"*{short_party(name)}*, {short_rep['volume']} {short_rep['reporter']} at {pins.get(short_rep['reporter']) or '___'}."
    return {"full": full, "short": short, "flags": flags, "mode": mode,
            "reporters": [cite_str(r) for r in chosen]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("matter")
    ap.add_argument("entry_id")
    ap.add_argument("--mode", choices=["academic", "ga"], default="academic")
    ap.add_argument("--pin")
    ap.add_argument("--pin-reporter")
    ap.add_argument("--textual", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    ledger = json.loads((Path(a.matter) / "authorities.json").read_text(encoding="utf-8"))
    entry = next((e for e in ledger["authorities"] if e["id"] == a.entry_id), None)
    if entry is None or entry.get("type") != "case":
        print(f"No case entry {a.entry_id}", file=sys.stderr)
        return 2
    if entry.get("status") != "retrieved" or (entry.get("verification") or {}).get("existence") != "verified":
        print(f"{a.entry_id} is not retrieved and verified; run /find-case first", file=sys.stderr)
        return 2
    out = format_case(entry, a.mode, a.pin, a.pin_reporter, a.textual)
    print(json.dumps(out, ensure_ascii=False, indent=1) if a.json else
          f"full: {out['full']}\nshort: {out['short']}\nflags: {', '.join(out['flags']) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
