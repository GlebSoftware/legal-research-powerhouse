"""Forward sweep and passages from real CourtListener results (Becks v. Pierce, 2026-10-16), screened offline."""

import json

import treatment_screen as ts
from conftest import FIXTURES, fixture, run_script
from test_ledger import MATTER, create, full_read_payload, ledger


def primed(project):
    create(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    run_script("ledger.py", ["ingest"], full_read_payload(), project)
    return project


def test_cites_search_records_citing_list_without_candidates(project):
    primed(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-courtlistener-search-cites-1266402"), project)
    rows = ledger(project)["authorities"]
    assert [e["id"] for e in rows] == ["cl-cluster-1266402"]  # no citing opinions ledgered as candidates
    assert rows[0]["treatment"]["citing_count"] == 7
    store = json.loads((project / MATTER / "sources" / "treatment" / "cl-cluster-1266402.citing.json").read_text(encoding="utf-8"))
    assert "10729389" in store["citing"] and store["citing"]["1223841"]["court_id"] == "gactapp"


def test_cites_search_with_no_citers_records_zero(project):
    """Real empty sweep shape (cites:(9971924), 2026-10-16): {"query_id": ..., "count": 0, "results": []}."""
    primed(project)
    p = fixture("PostToolUse-courtlistener-search-cites-1266402")
    p["tool_name"] = "mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"
    p["tool_response"] = [{"type": "text", "text": json.dumps({"query_id": "4e9a04c9", "count": 0, "results": []})}]
    run_script("ledger.py", ["ingest"], p, project)
    assert ledger(project)["authorities"][0]["treatment"]["citing_count"] == 0


def test_passages_filed_by_citation_markup(project):
    primed(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-courtlistener-search_document-becks"), project)
    lines = (project / MATTER / "sources" / "treatment" / "cl-cluster-1266402.passages.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(x) for x in lines]
    assert {r["citing_opinion_id"] for r in rows} == {11195974, 10804660, 10235693, 1405682, 1223841}
    assert all("<" not in r["text"] for r in rows)


def test_screen_writes_lightweight_treatment(project):
    primed(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-courtlistener-search-cites-1266402"), project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-courtlistener-search_document-becks"), project)
    r = run_script("treatment_screen.py", [str(project / MATTER), "cl-cluster-1266402", "--json"], None, project)
    assert r.returncode == 0, r.stderr.decode()
    out = json.loads(r.stdout)
    assert out["level"] == "lightweight" and out["citing_listed"] == 7 and out["sampled"] == 5
    assert out["most_recent_citing"] == "2025-10-31"
    assert "Capp v. Carlito's Mexican Bar & Grill 1, Inc." in out["invalidating_citers"]
    assert out["escalate"] is False  # no Tier A or B language near the mentions in these passages
    e = ledger(project)["authorities"][0]
    assert e["treatment"]["level"] == "lightweight" and e["treatment"]["sampled"] == 5
    show = run_script("ledger.py", ["show"], None, project).stdout.decode()
    assert "label=Screened" in show


def test_tier_a_language_escalates(project, tmp_path):
    primed(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-courtlistener-search-cites-1266402"), project)
    tdir = project / MATTER / "sources" / "treatment"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "cl-cluster-1266402.passages.jsonl").write_text(json.dumps({
        "citing_opinion_id": 11195974, "position": 1, "query": "Becks",
        "text": "To the extent Becks v. Pierce holds otherwise, it is overruled."}) + "\n", encoding="utf-8")
    r = run_script("treatment_screen.py", [str(project / MATTER), "cl-cluster-1266402", "--json"], None, project)
    out = json.loads(r.stdout)
    assert out["escalate"] is True and out["flags"][0]["tier"] == "A" and out["flags"][0]["phrase"] == "overruled"


PENNOYER = json.loads((FIXTURES / "pennoyer-screen.json").read_text(encoding="utf-8"))


def pennoyer_matter(tmp_path, passages=None):
    """A matter holding the Pennoyer ledger entry and its real citers and passages (2026-10-17)."""
    m = tmp_path / "research" / "civ-pro" / "pennoyer"
    (m / "sources" / "treatment").mkdir(parents=True)
    (m / "authorities.json").write_text(json.dumps({"schema_version": 1, "authorities": [
        {**PENNOYER["entry"], "treatment": {"level": "none"}}]}), encoding="utf-8")
    (m / "sources" / "treatment" / "cl-cluster-89656.citing.json").write_text(json.dumps({
        "target": "cl-cluster-89656", "citing": PENNOYER["citing"], "counts": {"9417104": 285, "89656": 1470},
        "count": 1755}), encoding="utf-8")
    (m / "sources" / "treatment" / "cl-cluster-89656.passages.jsonl").write_text(
        "".join(json.dumps(p) + "\n" for p in (passages or PENNOYER["passages"])), encoding="utf-8")
    return m


def test_supersession_language_escalates_pennoyer(tmp_path):
    m = pennoyer_matter(tmp_path)
    out = ts.screen(m, {**PENNOYER["entry"]})
    s = {(f["tier"], f["phrase"].lower(), f["citing_case"]) for f in out["flags"]}
    assert ("S", "evolved from", "World-Wide Volkswagen Corp. v. Woodson") in s
    assert ("S", "rigid", "World-Wide Volkswagen Corp. v. Woodson") in s
    assert ("S", "departure from", "Daimler AG v. Bauman") in s
    assert out["escalate"] is True and "Tier A/S/B" in out["summary"] and "S: " in out["summary"]
    assert "(of 1755 citing)" in out["summary"]


def test_spaced_reporter_cite_counts_as_a_mention():
    pats = ts.mention_patterns(PENNOYER["entry"])
    assert ts.mention_spans("as the Court held in 95 U. S. 714, 733", pats)
    assert ts.mention_spans("see 24 L.Ed. 565", pats)
    assert not ts.mention_spans("see 950 U.S. 714", pats)


def test_overruling_sentence_outside_the_window_is_flagged(tmp_path):
    filler = "The opinion turns to other questions of procedure and practice in the lower courts. " * 12
    text = (f"Service in the State remained the rule after 95 U. S. 714 for many years. {filler}"
            "To the extent that prior decisions are inconsistent with this standard, they are overruled.")
    m = pennoyer_matter(tmp_path, [{"citing_opinion_id": 109721, "position": 1, "query": "Pennoyer", "text": text}])
    out = ts.screen(m, {**PENNOYER["entry"]})
    hit = [f for f in out["flags"] if f["tier"] == "A"]
    assert hit and hit[0]["scope"] == "passage" and hit[0]["phrase"] == "overruled"


def test_filtered_sweeps_leave_the_citing_count_alone(tmp_path):
    m = tmp_path / "matter"
    ledger = {"authorities": [{**PENNOYER["entry"], "treatment": {}}]}
    base = {"type": "o", "order_by": "dateFiled desc"}
    ts.store_citing(m, ledger, {**base, "q": "cites:(9417104)"}, {"count": 285, "results": []})
    ts.store_citing(m, ledger, {**base, "q": "cites:(89656)"}, {"count": 1470, "results": []})
    ts.store_citing(m, ledger, {**base, "q": "cites:(89656) OR cites:(9417104)", "court": "scotus",
                                "order_by": "citeCount desc"}, {"count": 134, "results": []})
    tr = ledger["authorities"][0]["treatment"]
    assert tr["citing_count"] == 1755
    store = json.loads((m / "sources" / "treatment" / "cl-cluster-89656.citing.json").read_text(encoding="utf-8"))
    assert store["counts"] == {"9417104": 285, "89656": 1470}
    assert list(store["count_by_filter"].values()) == [134]
    ts.store_citing(m, ledger, {**base, "q": "cites:(89656)"}, {"count": 1471, "results": []})
    assert ledger["authorities"][0]["treatment"]["citing_count"] == 1756  # a later unfiltered sweep updates its record


def test_heavyweight_verdict_recorded(project):
    primed(project)
    r = run_script("ledger.py", ["treatment", MATTER, "cl-cluster-1266402", "--verdict", "VALID", "--confidence",
                                 "moderate", "--proposition", "knowledge that the patron will soon drive"], None, project)
    assert r.returncode == 0, r.stderr.decode()
    tr = ledger(project)["authorities"][0]["treatment"]
    assert tr["level"] == "heavyweight" and tr["verdict"] == "VALID"
    assert "label=Verified" in run_script("ledger.py", ["show"], None, project).stdout.decode()
