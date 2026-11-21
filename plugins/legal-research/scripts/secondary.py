"""Secondary-source relay (ADR-10, docs/05-secondary-sources.md): request, ingest, list, withdraw.

Claude never touches Westlaw, Lexis+, or Bloomberg Law. A request renders an SR block for the user to run by hand;
ingest records what he brings back, within the report-back limits.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path

from alr_common import (
    get_entry,
    index_ledger,
    ledger_lock,
    load_ledger,
    now_iso,
    parse_reporter_cite,
    case_key,
    ocga_key,
    save_ledger,
    sha256_text,
)

KINDS = {"restatement", "treatise", "encyclopedia", "alr", "law_review", "practice_guide", "other"}
SYSTEMS = {"westlaw-manual": "Westlaw", "lexis-manual": "Lexis+", "bloomberg-manual": "Bloomberg Law", "free": "free source"}
TC_ALLOWED = re.compile(r"^[\w\s()!*#%,.'/+\-]*$")
TC_FORBIDDEN = re.compile(r"&|\"|\bOR\b|\bor\b|\bAND\b|\band\b")
MAX_QUOTE_WORDS = 49
MAX_QUOTES = 5
MAX_SUMMARY_WORDS = 200

BRING_BACK = """Bring back (see section 4)
- Full citation: title, edition, volume, section, year, publisher
- Pinpoint: section, comment letter, or page
- Your own summary of what the source says for the proposition, two to six sentences
- The short quotations you will use in the memo, verbatim, each under 50 words
- Cases and statutes the source points to, as citations only
- KeyCite status of any case you will rely on
Do not paste: full sections or pages; West headnotes, key numbers, KeyCite flags, synopses, or other Thomson Reuters editorial text; bulk text from any screen."""


class RelayError(ValueError):
    pass


def norm(text: str) -> str:
    """Lowercase, NFKC, section signs and punctuation folded, whitespace collapsed."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = t.replace("§", " sec ").replace("&amp;", "&")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def next_request_id(ledger: dict) -> str:
    nums = [int(e["request_id"][3:]) for e in ledger["authorities"] if str(e.get("request_id", "")).startswith("SR-")]
    return f"SR-{(max(nums) + 1) if nums else 1:03d}"


def _source_text(matter: Path, entry: dict) -> str:
    texts = []
    for rel in [entry.get("local_path"), *(entry.get("files") or [])]:
        if rel and (matter / rel).is_file():
            texts.append((matter / rel).read_text(encoding="utf-8"))
    return "\n".join(texts)


def validate_request(matter: Path, ledger: dict, spec: dict) -> None:
    if ledger.get("closed_universe") and not spec.get("assignment_supplied"):
        raise RelayError("Closed-universe matter: no secondary-source request unless the assignment supplies the source "
                         "(set assignment_supplied only when it does).")
    for key in ("issue", "proposition", "free_sources_tried"):
        if not str(spec.get(key, "")).strip():
            raise RelayError(f"'{key}' is required.")
    triggers = spec.get("triggers") or []
    if not triggers or any(t not in range(1, 7) for t in triggers):
        raise RelayError("'triggers' must list one or more of 1 to 6 (docs/05-secondary-sources.md section 2).")
    if spec.get("secondary_kind", "other") not in KINDS:
        raise RelayError(f"'secondary_kind' must be one of {sorted(KINDS)}.")
    if spec.get("system", "westlaw-manual") not in SYSTEMS or spec.get("system") == "free":
        raise RelayError("'system' must be westlaw-manual, lexis-manual, or bloomberg-manual.")

    pointer_sections: set[str] = set()
    for kp in spec.get("known_pointers") or []:
        pointer, named_in = kp.get("pointer", ""), kp.get("named_in") or []
        if not pointer or not named_in:
            raise RelayError("Each known pointer needs 'pointer' and 'named_in' (ledger ids of retrieved primary sources).")
        found = False
        for eid in named_in:
            e = get_entry(ledger, eid)
            if e is None or e.get("status") != "retrieved" or e.get("type") == "secondary":
                raise RelayError(f"Known pointer '{pointer}': {eid} is not a retrieved primary source in the ledger.")
            if norm(pointer) in norm(_source_text(matter, e)):
                found = True
        if not found:
            raise RelayError(f"Known pointer '{pointer}' does not appear in the saved text of {', '.join(named_in)}. "
                             f"Mark it 'locate' instead.")
        pointer_sections.update(re.findall(r"§+\s*[\d.\-]*\d", pointer))

    def check_sections(text: str, where: str) -> None:
        for sec in re.findall(r"§+\s*[\d.\-]*\d", text):
            if sec not in pointer_sections:
                raise RelayError(f"{where} names '{sec}', which no known pointer supplies. Section numbers come only "
                                 f"from retrieved primary sources; write 'locate'.")

    for i, line in enumerate(spec.get("ranked_source_types") or [], 1):
        check_sections(line, f"Ranked source type {i}")
    for s in spec.get("searches") or []:
        method = s.get("method", "")
        if method not in ("Precision plain language", "Terms and Connectors", "Advanced Search", "Navigation"):
            raise RelayError(f"Search {s.get('label')}: method must be Precision plain language, Terms and Connectors, "
                             f"Advanced Search, or Navigation.")
        body = s.get("path") if method == "Navigation" else s.get("query")
        if not body:
            raise RelayError(f"Search {s.get('label')}: {'path' if method == 'Navigation' else 'query'} is required.")
        check_sections(body, f"Search {s.get('label')}")
        if method == "Terms and Connectors":
            if TC_FORBIDDEN.search(body) or not TC_ALLOWED.match(body):
                raise RelayError(f"Search {s.get('label')}: '&', AND, OR, and quoted phrases need Advanced Search "
                                 f"(references/westlaw-syntax.md); relabel it or rewrite it with connectors only.")


def render_block(rid: str, spec: dict) -> str:
    trig = " and ".join(str(t) for t in spec["triggers"])
    lines = [f"## {rid} · {date.today().isoformat()} · {spec['issue']}", "",
             f"Proposition needed: {spec['proposition']}",
             f"Trigger: {trig}. Free sources tried: {spec['free_sources_tried']}", "", "Ranked source types"]
    lines += [f"{i}. {t}" for i, t in enumerate(spec.get("ranked_source_types") or [], 1)]
    lines += ["", "Westlaw searches (paste as written)" if spec.get("system", "westlaw-manual") == "westlaw-manual"
              else f"{SYSTEMS[spec['system']]} searches (paste as written; confirm syntax on screen)"]
    for s in spec.get("searches") or []:
        if s["method"] == "Navigation":
            lines.append(f"{s['label']}. Navigation: {s['path']}")
            continue
        head = f"{s['label']}. {s['method']}, content: {s.get('content', 'Secondary Sources')}"
        if s.get("jurisdiction"):
            head += f", jurisdiction: {s['jurisdiction']}"
        lines += [head, f"   {s['query']}"]
    pointers = spec.get("known_pointers") or []
    if pointers:
        listed = "; ".join(f"{p['pointer']} (quoted in {', '.join(p['named_in'])})" for p in pointers)
        lines += ["", f"Known pointers (from retrieved primary sources only): {listed}. Everything else: locate."]
    else:
        lines += ["", "Known pointers (from retrieved primary sources only): none. Everything else: locate."]
    lines += ["", BRING_BACK, ""]
    return "\n".join(lines)


def request(matter: Path, spec: dict) -> str:
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        validate_request(matter, ledger, spec)
        rid = next_request_id(ledger)
        block = render_block(rid, spec)
        out = matter / "audit" / "secondary-requests.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if out.exists() else "# Secondary-source requests\n\nRun each search by hand. Report back with `/secondary ingest <id>`.\n\n"
        with out.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(prefix + block + "\n")
        ledger["authorities"].append({
            "id": f"sec-{rid}",
            "type": "secondary",
            "secondary_kind": spec.get("secondary_kind", "other"),
            "request_id": rid,
            "status": "requested",
            "source": {"system": spec.get("system", "westlaw-manual"), "retrieved_by": None, "retrieved_at": None,
                       "westlaw_citation": None, "tool": "secondary-request"},
            "first_seen_at": now_iso(),
            "citation": {"bluebook": None, "pin": None},
            "verification": {"existence": "unverified", "method": None, "checked_at": None},
            "request": spec,
            "disclosure": None,
            "propositions": [],
            "quote_checks": [],
        })
        save_ledger(matter, ledger)
    return rid


def parse_report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if path.suffix == ".json":
        return json.loads(text)
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise RelayError(f"{path.name}: expected YAML front matter between --- lines (references/report-template.md).")
    import yaml  # lazy: only the relay needs it

    meta = yaml.safe_load(m.group(1)) or {}
    meta["summary"] = m.group(2).strip()
    return meta


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def resolve_pointer(ledger: dict, cite: str) -> str | None:
    idx = index_ledger(ledger)
    for chunk in re.split(r",\s*", cite):
        p = parse_reporter_cite(re.sub(r"\(.*?\)", "", chunk).strip())
        if p:
            hits = idx.get(case_key(p["volume"], p["reporter"], p["page"]))
            if hits:
                return hits[0]["id"]
    m = re.search(r"(?:O\.C\.G\.A\.|Ga\. Code Ann\.)\s*§+\s*([\d\-.]+)", cite)
    if m:
        hits = idx.get(ocga_key(m.group(1)))
        if hits:
            return hits[0]["id"]
    return None


def ingest(matter: Path, request_id: str, report: dict) -> dict:
    for key in ("citation", "pin"):
        if not str(report.get(key, "")).strip():
            raise RelayError(f"Report needs '{key}'.")
    quotes = report.get("quotes") or []
    if len(quotes) > MAX_QUOTES:
        raise RelayError(f"At most {MAX_QUOTES} quotations; bring back only the ones the memo will use.")
    for q in quotes:
        words = len(str(q.get("text", "")).split())
        if not words:
            raise RelayError("Empty quotation.")
        if words > MAX_QUOTE_WORDS:
            raise RelayError(f"A quotation has {words} words; each must be under 50 (references/report-template.md).")
    summary = str(report.get("summary", "")).strip()
    n = _sentences(summary)
    if n < 2 or n > 6 or len(summary.split()) > MAX_SUMMARY_WORDS:
        raise RelayError(f"The summary has {n} sentences and {len(summary.split())} words; it must be two to six "
                         f"sentences and at most {MAX_SUMMARY_WORDS} words, in the user's own words.")
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        e = get_entry(ledger, f"sec-{request_id}")
        if e is None or e.get("status") not in ("requested", "reported"):
            raise RelayError(f"No open request {request_id}.")
        system = report.get("system") or e["source"]["system"]
        resolved, unresolved = [], []
        for cite in report.get("points_to") or []:
            rid = resolve_pointer(ledger, str(cite))
            (resolved if rid else unresolved).append(rid or str(cite))
        reported_on = str(report.get("retrieved_at") or now_iso()[:10])[:10]
        e.update({
            "status": "reported",
            "secondary_kind": report.get("secondary_kind") or e.get("secondary_kind", "other"),
            "retrieved_at": now_iso(),
            "citation": {"bluebook": str(report["citation"]).strip(), "pin": str(report["pin"]).strip()},
            "report": {"summary": summary,
                       "quotes": [{"text": str(q["text"]), "pin": q.get("pin"), "sha256": sha256_text(str(q["text"]))}
                                  for q in quotes],
                       "points_to": resolved, "points_to_unresolved": unresolved,
                       "keycite": report.get("keycite")},
            "verification": {"existence": "manual", "method": f"user-{system.split('-')[0]}", "checked_at": now_iso()},
            "disclosure": f"Manual ({SYSTEMS.get(system, system)}), reported {reported_on}",
        })
        e["source"].update({"system": system, "retrieved_by": "user", "retrieved_at": reported_on,
                            "westlaw_citation": str(report["citation"]).strip() if system == "westlaw-manual" else None})
        save_ledger(matter, ledger)
    return e


def withdraw(matter: Path, request_id: str) -> None:
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        e = get_entry(ledger, f"sec-{request_id}")
        if e is None:
            raise RelayError(f"No request {request_id}.")
        e["status"] = "withdrawn"
        save_ledger(matter, ledger)


def listing(ledger: dict) -> list[str]:
    rows = []
    for e in ledger["authorities"]:
        if e.get("type") != "secondary":
            continue
        req = e.get("request") or {}
        if e["status"] == "reported":
            extra = f"{e['citation'].get('bluebook')} [{e.get('disclosure')}]"
            if (e.get("report") or {}).get("points_to_unresolved"):
                extra += f"; re-pull: {'; '.join(e['report']['points_to_unresolved'])}"
        else:
            extra = req.get("issue", "")
        rows.append(f"- {e['request_id']} [{e['status']}] {extra}")
    return rows
