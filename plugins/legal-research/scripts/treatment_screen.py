# /// script
# requires-python = ">=3.12"
# ///
"""Lightweight treatment screen (architecture section 5, steps 1 to 3 and 6) from results the session already
received. Spends zero CourtListener quota: ingest stores the forward sweep and the passages, this scores them.

Storage, called by ledger.py ingest:
  cites:(<opinion_id>) searches  -> sources/treatment/<entry-id>.citing.json (merged by cluster). An unfiltered
                                    sweep sets that opinion record's count; citing_count is the sum over the
                                    entry's opinion records (a citer of both the lead and the combined record counts
                                    twice). A sweep with a court or date filter, or more query terms, lands under
                                    count_by_filter and leaves citing_count alone.
  search_document passages       -> sources/treatment/<entry-id>.passages.jsonl, filed under every ledger case
                                    whose cluster id appears in the passage's citation markup (data-id="...")

Screen:  treatment_screen.py <matter> <entry-id> [--json]
  A mention is the case name, the first party's name, or a reporter cite with or without spaces ("95 U. S. 714").
  Tier A (within 500 characters of a mention): overrul, abrogat, "no longer good law", disapprov, "we recede from",
  superseded, "is no longer viable after"; also any sentence anywhere in a passage that mentions the case and holds
  overrul, abrogat, or disapprov (marked scope "passage"). Tier S (supersession without the word overruled):
  "evolved from", abandon, "departure from", rigid, "no longer", repudiat, discard, erode or erosion, "has not
  survived", "cannot be reconciled", shibboleth, anachronism, obsolete, outmoded. Tier B: questioned, limited,
  "decline(d) to follow", "declined to extend", distinguish. Tier C (direct history): reversed, vacated, remanded,
  "cert. granted". A passage from a dissent or concurrence is marked: separate writings do not overrule. The screen
  adjudicates nothing: any Tier A, S, or B flag means escalate to the heavyweight validity check. Writes
  treatment.level = "lightweight" to the ledger.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import get_entry, ledger_lock, load_ledger, now_iso, save_ledger  # noqa: E402

CITES_RE = re.compile(r"cites:\s*\(\s*(\d+)\s*\)")
DATA_ID_RE = re.compile(r'data-id="(\d+)"')
WINDOW = 500
TIERS = {
    "A": [r"overrul\w*", r"abrogat\w*", r"no longer good law", r"disapprov\w*", r"we recede from", r"supersed\w*",
          r"is no longer viable after"],
    # Doctrinal supersession: the Court retires a rule without saying "overruled" (Pennoyer v. Neff, 2026-10-17).
    "S": [r"evolved from", r"\babandon\w*", r"departure from", r"\brigid(?:ly|ity)?\b",
          r"\bno longer\b(?! good law| viable)", r"\brepudiat\w*", r"\bdiscard\w*", r"\beroded?\b|\berosion\b",
          r"has not survived", r"cannot be reconciled", r"\bshibboleth\b", r"\banachronis\w*", r"\bobsolete\b",
          r"\boutmoded\b"],
    "B": [r"question(?:ed|s|ing)?\b", r"\blimit(?:ed|ing)\b", r"declin(?:e|es|ed|ing) to follow", r"declined to extend",
          r"distinguish\w*"],
    "C": [r"\breversed\b", r"\bvacated\b", r"\bremanded\b", r"cert\. granted"],
}
ESCALATE = "ASB"
STRONG_RE = re.compile(r"overrul\w*|abrogat\w*|disapprov\w*", re.I)
# A sentence ends at . ; ! or ? before a capital, an opening bracket or quote, or the end of the passage. Periods
# inside reporter abbreviations ("U. S.") split early, which only shortens the sentence the scan reads.
SENTENCE_RE = re.compile(r"[^.;!?]+(?:[.;!?]+(?=\s+[A-Z(\"“\[]|\s*$)|$)")
SEPARATE = {"dissent", "concurrence", "concurrence-opinion", "in-part-opinion", "040dissent", "030concurrence",
            "035concurrenceinpart", "050addendum"}
# Courts whose decisions can overrule a case from the target court (architecture section 5, step 1).
INVALIDATING = {"gactapp": {"gactapp", "ga"}, "ga": {"ga"}, "scotus": {"scotus"}}


def treatment_dir(matter: Path) -> Path:
    d = matter / "sources" / "treatment"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_case(ledger: dict, *, cluster_id: int | None = None, opinion_id: int | None = None) -> dict | None:
    for e in ledger["authorities"]:
        src = e.get("source") or {}
        if e.get("type") != "case" or src.get("system") != "courtlistener":
            continue
        if cluster_id and src.get("cluster_id") == cluster_id:
            return e
        if opinion_id and (opinion_id == src.get("opinion_id") or opinion_id in (src.get("opinion_ids") or [])
                           or opinion_id == src.get("cluster_id")):
            return e
    return None


def cites_target(tool_input: dict) -> int | None:
    m = CITES_RE.search(str(tool_input.get("q") or ""))
    return int(m.group(1)) if m else None


FILTER_KEYS = ("court", "filed_after", "filed_before", "cited_gt", "cited_lt")


def sweep_filter(tool_input: dict, target_op: int) -> str | None:
    """None for an unfiltered sweep (the query is exactly cites:(<id>) and no court or date filter); else a key."""
    q = re.sub(r"\s+", " ", str(tool_input.get("q") or "")).strip()
    filters = {k: tool_input.get(k) for k in FILTER_KEYS if tool_input.get(k)}
    if not filters and re.fullmatch(rf"cites:\s*\(\s*{target_op}\s*\)", q):
        return None
    return json.dumps({"q": q, **filters}, sort_keys=True)


def store_citing(matter: Path, ledger: dict, tool_input: dict, data: dict) -> list[str]:
    """A cites:(id) search: record the citing list for the target instead of ledgering every citer."""
    target_op = cites_target(tool_input)
    target = find_case(ledger, opinion_id=target_op) if target_op else None
    if target is None:
        return []
    path = treatment_dir(matter) / f"{target['id']}.citing.json"
    store = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"target": target["id"], "citing": {}}
    for hit in data.get("results") or []:
        cid = hit.get("cluster_id")
        if isinstance(cid, int):
            store["citing"][str(cid)] = {k: hit.get(k) for k in ("caseName", "court_id", "dateFiled", "citeCount",
                                                               "citation", "opinion_id", "cluster_opinions")}
    key = sweep_filter(tool_input, target_op)
    if key is None:
        store.setdefault("counts", {})[str(target_op)] = data.get("count")
    else:
        store.setdefault("count_by_filter", {})[key] = data.get("count")
    counts = [c for c in (store.get("counts") or {}).values() if isinstance(c, int)]
    store.update({"count": sum(counts) if counts else None, "query": tool_input.get("q"),
                  "order_by": tool_input.get("order_by"), "updated_at": now_iso()})
    path.write_text(json.dumps(store, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    tr = target.setdefault("treatment", {})
    tr["citing_count"] = store["count"]
    tr["citing_listed"] = len(store["citing"])
    return [target["id"]]


def plain(snippet: str) -> str:
    """Passage text: snippets arrive cut mid-tag at both ends ("...pan class=...>", "<pre class=\"in...")."""
    t = re.sub(r"^\.\.\.", "", snippet.strip())
    t = re.sub(r"\.\.\.$", "", t)
    first_lt, first_gt = t.find("<"), t.find(">")
    if first_gt != -1 and (first_lt == -1 or first_gt < first_lt):
        t = t[first_gt + 1:]
    t = re.sub(r"<[^>]*$", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t).replace("\f", " ")
    return re.sub(r"\s+", " ", t).strip(" .")


def store_passages(matter: Path, ledger: dict, tool_input: dict, data) -> list[str]:
    """search_document results: file each passage under every ledger case its citation markup names."""
    docs = data.get("results") if isinstance(data, dict) else data
    touched: set[str] = set()
    for doc in docs if isinstance(docs, list) else []:
        if not isinstance(doc, dict) or doc.get("error"):
            continue
        for snip in doc.get("snippets") or []:
            raw = snip.get("text") or ""
            targets = {int(x) for x in DATA_ID_RE.findall(raw)}
            for cid in targets:
                # data-id carries the cited opinion id; it equals the cluster id only for older clusters.
                e = find_case(ledger, opinion_id=cid)
                if e is None or doc.get("doc_id") in (e["source"].get("opinion_ids") or []):
                    continue
                line = {"citing_opinion_id": doc.get("doc_id"), "position": snip.get("position"),
                        "query": tool_input.get("query"), "text": plain(raw), "retrieved_at": now_iso()}
                with (treatment_dir(matter) / f"{e['id']}.passages.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(line, ensure_ascii=False) + "\n")
                touched.add(e["id"])
    return sorted(touched)


# ---------------------------------------------------------------- the screen


def merged_passages(path: Path) -> dict[int, str]:
    """One text per citing opinion: overlapping snippets (search_document returns one per match) merged."""
    by_op: dict[int, list[tuple[int, str]]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            by_op.setdefault(row["citing_opinion_id"], []).append((row.get("position") or 0, row["text"]))
    merged = {}
    for op, rows in by_op.items():
        texts: list[str] = []
        for _pos, text in sorted(rows):
            if not any(text in t or t in text for t in texts):
                texts.append(text)
        merged[op] = " … ".join(texts)
    return merged


def reporter_pattern(volume: str, reporter: str) -> str:
    """'95' and 'U.S.' match "95 U.S.", "95 U. S.", and "95 U.S"; spaces inside the reporter are optional."""
    parts = [r"\.\s*" if ch == "." else r"\s*" if ch == " " else re.escape(ch) for ch in reporter.strip()]
    return rf"\b{re.escape(volume)}\s+{''.join(parts)}"


def mention_patterns(entry: dict) -> list[str]:
    cit = entry.get("citation") or {}
    name = cit.get("case_name") or ""
    out = [re.escape(n) for n in (name, name.split(" v. ")[0]) if n]
    out += [reporter_pattern(str(r["volume"]), str(r["reporter"])) for r in cit.get("reporters") or []
            if r.get("volume") and r.get("reporter")]
    return out


def mention_spans(text: str, patterns: list[str]) -> list[int]:
    return sorted({m.start() for p in patterns for m in re.finditer(p, text, re.I)})


def mention_windows(text: str, patterns: list[str]) -> list[str]:
    hits = mention_spans(text, patterns)
    if not hits:
        return [text]
    return [text[max(0, h - WINDOW): h + WINDOW] for h in hits]


def screen(matter: Path, entry: dict) -> dict:
    tdir = matter / "sources" / "treatment"
    citing_path = tdir / f"{entry['id']}.citing.json"
    citing = json.loads(citing_path.read_text(encoding="utf-8"))["citing"] if citing_path.is_file() else {}
    by_opinion = {}
    for cid, row in citing.items():
        for op in [row.get("opinion_id")] + [o.get("id") for o in row.get("cluster_opinions") or []]:
            if op:
                by_opinion[op] = {**row, "cluster_id": int(cid),
                                  "opinion_type": next((o.get("type") for o in row.get("cluster_opinions") or []
                                                        if o.get("id") == op), None)}
    passages = merged_passages(tdir / f"{entry['id']}.passages.jsonl")
    cit = entry.get("citation") or {}
    patterns = mention_patterns(entry)
    flags = []

    def flag(tier: str, phrase: str, op: int, passage: str, scope: str) -> None:
        meta = by_opinion.get(op, {})
        flags.append({"tier": tier, "phrase": phrase, "citing_opinion_id": op, "citing_cluster": meta.get("cluster_id"),
                      "citing_case": meta.get("caseName"), "court_id": meta.get("court_id"), "date": meta.get("dateFiled"),
                      "separate_opinion": (meta.get("opinion_type") or "") in SEPARATE, "scope": scope,
                      "passage": passage.strip()})

    for op, text in passages.items():
        for window in mention_windows(text, patterns):
            for tier, pats in TIERS.items():
                for pat in pats:
                    for m in re.finditer(pat, window, re.I):
                        flag(tier, m.group(0), op, window[max(0, m.start() - 160): m.end() + 160], "window")
        # An overruling clause can sit a footnote away from the case name; read every sentence of a passage that
        # mentions the case at all.
        if mention_spans(text, patterns):
            for sent in SENTENCE_RE.finditer(text):
                m = STRONG_RE.search(sent.group(0))
                if m:
                    flag("A", m.group(0), op, sent.group(0)[:400], "passage")
    seen, unique = set(), []
    for f in flags:
        key = (f["tier"], f["phrase"].lower(), f["citing_opinion_id"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    court = cit.get("court_id") or ""
    invalidating = INVALIDATING.get(court, {court, "scotus"} if court.startswith(("ca", "scotus")) else {court})
    dates = sorted((r.get("dateFiled") or "") for r in citing.values() if r.get("dateFiled"))
    loud = [f for f in unique if f["tier"] in ESCALATE and not f["separate_opinion"]]
    by_tier = {t: sum(1 for f in loud if f["tier"] == t) for t in ESCALATE if any(f["tier"] == t for f in loud)}
    store = json.loads(citing_path.read_text(encoding="utf-8")) if citing_path.is_file() else {}
    return {
        "level": "lightweight",
        "screened_at": now_iso(),
        "citing_count": store.get("count"),
        "citing_counts_by_record": store.get("counts") or {},
        "citing_listed": len(citing),
        "sampled": len(passages),
        "invalidating_citers": sorted({r["caseName"] for r in citing.values() if r.get("court_id") in invalidating}),
        "most_recent_citing": dates[-1] if dates else None,
        "flags": unique,
        "escalate": bool(loud),
        "summary": (f"Screened (lightweight): {len(passages)} of {len(citing)} listed citing opinions read in passage"
                    + (f" (of {store['count']} citing)" if store.get("count") else "") + "; "
                    + (f"{len(loud)} Tier A/S/B signal(s) ({', '.join(f'{t}: {n}' for t, n in by_tier.items())}), "
                       "escalate to the heavyweight check." if loud else "no Tier A, S, or B signals in the passages read.")
                    + " A clean screen is not a finding of validity."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("matter")
    ap.add_argument("entry_id")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    matter = Path(a.matter)
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        e = get_entry(ledger, a.entry_id)
        if e is None or e.get("type") != "case":
            print(f"No case entry {a.entry_id}", file=sys.stderr)
            return 2
        result = screen(matter, e)
        tr = e.setdefault("treatment", {})
        if tr.get("level") != "heavyweight":
            tr["level"] = "lightweight"
        tr["screen"] = result
        tr["citing_count"] = result["citing_count"]
        tr["sampled"] = result["sampled"]
        tr["flags"] = result["flags"]
        save_ledger(matter, ledger)
    if a.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
    else:
        print(result["summary"])
        for f in result["flags"]:
            print(f"- Tier {f['tier']} '{f['phrase']}' in {f['citing_case']} ({f['court_id']} {(f['date'] or '')[:4]})"
                  f"{' [separate opinion]' if f['separate_opinion'] else ''}: …{f['passage']}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
