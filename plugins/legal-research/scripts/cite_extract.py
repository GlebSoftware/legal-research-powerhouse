# /// script
# requires-python = ">=3.12"
# dependencies = ["eyecite==2.7.8"]
# ///
"""Citation extraction for the audit: eyecite plus the gate's patterns, with spans, ledger ids, and pincites.

The patterns live in cite_gate.py so the gate and the audit read citations the same way. This module adds what
the audit needs and the gate does not: character spans, pincites, [[src:<id> <pin>]] tokens, and quotations.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import case_key, cfr_key, fr_key, index_ledger, ocga_key, usc_key, volume_key  # noqa: E402
from cite_gate import BARE_RE, OCGA_RE, SEC_PATTERNS, SIGNALS, citable, names_match, trim_party  # noqa: E402

TOKEN_RE = re.compile(r"\[\[src:([A-Za-z0-9][\w.\-]*)(?:\s+([^\]]+?))?\]\]")
QUOTE_RE = re.compile(r"[“\"]([^“”\"]+)[”\"]")  # pair every mark; quotations() drops the short ones
MIN_QUOTE_WORDS = 6


@dataclass
class Cite:
    kind: str  # case | short_case | id | statute | regulation | secondary | bare_name | token
    text: str
    start: int
    end: int
    entry_id: str | None = None
    pin: str | None = None
    problem: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Quote:
    text: str
    start: int
    end: int


def _secondary_entry(ledger: dict, shown: str) -> tuple[str | None, str | None]:
    from secondary import norm

    key = norm(shown)
    for e in ledger["authorities"]:
        if e.get("type") != "secondary":
            continue
        hay = norm(" ".join(filter(None, [(e.get("citation") or {}).get("bluebook"), (e.get("source") or {}).get("westlaw_citation")])))
        if key and key in hay:
            return e["id"], None if e.get("status") == "reported" else f"{e.get('request_id')} is {e.get('status')}"
    return None, "no reported secondary-source entry"


def extract(text: str, ledger: dict) -> list[Cite]:
    from eyecite import get_citations
    from eyecite.models import (FullCaseCitation, FullJournalCitation, FullLawCitation, IdCitation,
                                ShortCaseCitation)

    logging.disable(logging.CRITICAL)
    clean = re.sub(r"[*_]", " ", text)  # same length as text, so spans line up
    idx = index_ledger(ledger)
    out: list[Cite] = []
    for m in TOKEN_RE.finditer(text):
        e = next((x for x in ledger["authorities"] if x["id"] == m.group(1)), None)
        problem = "no ledger entry" if e is None else citable(e) if e.get("type") != "secondary" else (
            None if e.get("status") == "reported" else f"{e.get('request_id')} is {e.get('status')}")
        out.append(Cite("token", m.group(0), m.start(), m.end(), m.group(1), m.group(2), problem))
    for c in get_citations(clean):
        g, md = c.groups, c.metadata
        s, e_ = c.span()
        shown = text[s:e_]
        pin = getattr(md, "pin_cite", None)
        pin = re.sub(r"^,\s*|^at\s+", "", pin).strip() if pin else None
        if isinstance(c, FullJournalCitation) or (isinstance(c, FullCaseCitation) and g.get("reporter", "").startswith("A.L.R.")):
            eid, problem = _secondary_entry(ledger, shown)
            out.append(Cite("secondary", shown, s, e_, eid, pin, problem))
        elif isinstance(c, FullCaseCitation):
            hits = idx.get(case_key(g["volume"], g["reporter"], g["page"]), [])
            party = " ".join(filter(None, [md.plaintiff, md.defendant]))
            if not hits:
                out.append(Cite("case", shown, s, e_, None, pin, "no ledger entry", {"party": party}))
                continue
            entry = hits[0]
            problem = citable(entry)
            if not problem and party and not names_match(party, entry):
                problem = f"ledger records this reporter cite as {entry['citation'].get('case_name')}"
            out.append(Cite("case", shown, s, e_, entry["id"], pin, problem, {"party": party}))
        elif isinstance(c, ShortCaseCitation):
            hits = idx.get(volume_key(g["volume"], g["reporter"]), [])
            out.append(Cite("short_case", shown, s, e_, hits[0]["id"] if hits else None, pin or g.get("page"),
                            None if hits and not citable(hits[0]) else ("no ledger entry" if not hits else citable(hits[0]))))
        elif isinstance(c, IdCitation):
            out.append(Cite("id", shown, s, e_, None, pin))
        elif isinstance(c, FullLawCitation):
            rep = (g.get("reporter") or "").lower()
            key = (ocga_key(g["section"]) if rep == "ga. code ann." else
                   usc_key(g["title"], g["section"]) if rep == "u.s.c." and g.get("title") else
                   cfr_key(g.get("chapter") or g.get("title"), g["section"]) if rep == "c.f.r." and (g.get("chapter") or g.get("title")) else
                   fr_key(g["volume"], g["page"]) if rep in ("fed. reg.", "fr") and g.get("volume") else None)
            hits = idx.get(key, []) if key else []
            kind = "regulation" if rep in ("c.f.r.", "fed. reg.", "fr") else "statute"
            problem = "unsupported citation form" if key is None else ("no ledger entry" if not hits else citable(hits[0]))
            out.append(Cite(kind, shown, s, e_, hits[0]["id"] if hits else None, pin, problem))
    for m in OCGA_RE.finditer(clean):
        hits = idx.get(ocga_key(m.group(1)), [])
        out.append(Cite("statute", text[m.start():m.end()], m.start(), m.end(), hits[0]["id"] if hits else None,
                        None, "no ledger entry" if not hits else citable(hits[0])))
    for pattern in SEC_PATTERNS:
        for m in pattern.finditer(clean):
            eid, problem = _secondary_entry(ledger, m.group(0))
            out.append(Cite("secondary", text[m.start():m.end()], m.start(), m.end(), eid, None, problem))
    spans = [(c.start, c.end, c) for c in out if c.kind == "case"]
    for m in BARE_RE.finditer(clean):
        name = f"{trim_party(m.group(1), leading=True)} v. {trim_party(m.group(2), leading=False)}"
        toks = {t.lower() for t in re.findall(r"[A-Za-z]+", name)} - SIGNALS
        if any(0 <= s - m.end() <= 40 for s, _e, _c in spans):
            continue
        cited = next((c for c in out if c.kind == "case" and c.entry_id and not c.problem
                      and toks & {t.lower() for t in re.findall(r"[A-Za-z]+", c.extra.get("party", ""))}), None)
        out.append(Cite("bare_name", name, m.start(), m.end(), cited.entry_id if cited else None, None,
                        None if cited else "bare case name with no full citation in the draft"))
    return sorted(out, key=lambda c: c.start)


def quotations(text: str) -> list[Quote]:
    # American style puts the period or comma inside the closing mark; the source sentence may run on.
    out = [Quote(m.group(1).rstrip(" .,;:"), m.start(1), m.end(1)) for m in QUOTE_RE.finditer(text)
           if len(m.group(1).split()) >= MIN_QUOTE_WORDS]
    for m in re.finditer(r"(?m)^(?:> ?.*(?:\n|$))+", text):
        body = re.sub(r"(?m)^> ?", "", m.group(0)).strip()
        if len(body.split()) >= MIN_QUOTE_WORDS and not any(q.start >= m.start() and q.end <= m.end() for q in out):
            out.append(Quote(body, m.start(), m.end()))
    return sorted(out, key=lambda q: q.start)
