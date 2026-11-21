"""Westlaw relay (ADR-10): request validation, report-back limits, ledger entries, and the gate rule."""

import json
from pathlib import Path

from conftest import fixture, run_script
from test_cite_gate import gate, write
from test_ledger import MATTER, create, full_read_payload, ledger

REST = "Restatement (Second) of Torts § 448"


def primed(project: Path, *flags: str) -> Path:
    create(project, *flags)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    run_script("ledger.py", ["ingest"], full_read_payload(), project)
    return project


def spec(**over) -> dict:
    base = {
        "issue": "Issue 1: knowledge that the patron will soon drive (Georgia)",
        "proposition": "what a provider must know about the patron's driving",
        "triggers": [2],
        "free_sources_tried": "CourtListener semantic and keyword rounds in ga and gactapp",
        "secondary_kind": "treatise",
        "ranked_source_types": ["Texts & Treatises: a torts treatise chapter on dram shop liability (locate)."],
        "searches": [
            {"label": "A", "method": "Precision plain language", "content": "Secondary Sources", "jurisdiction": "Georgia",
             "query": "dram shop liability knowledge patron will soon be driving"},
            {"label": "B", "method": "Terms and Connectors", "content": "Secondary Sources > Texts & Treatises",
             "query": "dram /s shop /p know! /p driv!"},
            {"label": "C", "method": "Navigation", "path": "Secondary Sources > Encyclopedias > American Jurisprudence (confirm on screen)"},
        ],
        "known_pointers": [],
    }
    base.update(over)
    return base


def request(project: Path, s: dict):
    return run_script("ledger.py", ["secondary", "request", MATTER, "-"], s, project)


def report(project: Path, rid: str, body: str):
    d = project / MATTER / "audit" / "secondary-reports"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}.md").write_text(body, encoding="utf-8")
    return run_script("ledger.py", ["secondary", "ingest", MATTER, rid], None, project)


GOOD_REPORT = f"""---
request_id: SR-001
system: westlaw-manual
secondary_kind: restatement
citation: "{REST} (Am. L. Inst. 1965)"
pin: "§ 448 cmt. b"
retrieved_at: 2026-10-16
keycite: "Becks: no negative history"
points_to:
  - "Becks v. Pierce, 282 Ga. App. 229, 638 S.E.2d 390 (2006)"
  - "Smith v. Jones, 1 Ga. 1 (1846)"
quotes:
  - text: "a short quotation the memo will use"
    pin: "cmt. b"
---

First sentence of the summary. Second sentence of the summary.
"""


def test_request_writes_block_and_entry(project):
    primed(project)
    r = request(project, spec())
    assert r.returncode == 0, r.stderr.decode()
    block = (project / MATTER / "audit" / "secondary-requests.md").read_text(encoding="utf-8")
    assert "## SR-001 · " in block and "Westlaw searches (paste as written)" in block
    assert "B. Terms and Connectors, content: Secondary Sources > Texts & Treatises\n   dram /s shop /p know! /p driv!" in block
    assert "Known pointers (from retrieved primary sources only): none. Everything else: locate." in block
    assert "Do not paste:" in block
    e = [a for a in ledger(project)["authorities"] if a["type"] == "secondary"][0]
    assert e["id"] == "sec-SR-001" and e["status"] == "requested" and e["request_id"] == "SR-001"


def test_closed_universe_refuses(project):
    primed(project, "--closed-universe")
    r = request(project, spec())
    assert r.returncode == 2 and b"Closed-universe" in r.stderr


def test_pointer_must_appear_in_retrieved_source(project):
    primed(project)
    bad = spec(known_pointers=[{"pointer": REST, "named_in": ["cl-cluster-1266402"]}])
    r = request(project, bad)
    assert r.returncode == 2 and b"does not appear in the saved text" in r.stderr
    good = spec(known_pointers=[{"pointer": "OCGA § 51-1-40", "named_in": ["cl-cluster-1266402"]}],
                ranked_source_types=["Annotations construing § 51-1-40 (locate)."])
    r = request(project, good)
    assert r.returncode == 0, r.stderr.decode()


def test_section_number_without_pointer_refused(project):
    primed(project)
    r = request(project, spec(ranked_source_types=[f"{REST}, comments."]))
    assert r.returncode == 2 and b"no known pointer supplies" in r.stderr


def test_terms_and_connectors_rejects_or_and_phrases(project):
    primed(project)
    s = spec()
    s["searches"][1]["query"] = '("dram shop" OR liquor) /p driv!'
    r = request(project, s)
    assert r.returncode == 2 and b"Advanced Search" in r.stderr
    s["searches"][1]["method"] = "Advanced Search"
    assert request(project, s).returncode == 0


def test_ingest_enforces_limits_and_records_report(project):
    primed(project)
    request(project, spec())
    long_quote = GOOD_REPORT.replace("a short quotation the memo will use", " ".join(["word"] * 55))
    r = report(project, "SR-001", long_quote)
    assert r.returncode == 2 and b"under 50" in r.stderr
    one_sentence = GOOD_REPORT.replace("First sentence of the summary. Second sentence of the summary.", "Only one.")
    r = report(project, "SR-001", one_sentence)
    assert r.returncode == 2 and b"two to six" in r.stderr
    r = report(project, "SR-001", GOOD_REPORT)
    assert r.returncode == 0, r.stderr.decode()
    assert b"Smith v. Jones" in r.stdout  # unresolved pointer is listed for re-pulling
    e = [a for a in ledger(project)["authorities"] if a["type"] == "secondary"][0]
    assert e["status"] == "reported" and e["verification"]["existence"] == "manual"
    assert e["disclosure"] == "Manual (Westlaw), reported 2026-10-16"
    assert e["report"]["points_to"] == ["cl-cluster-1266402"]
    assert len(e["report"]["quotes"][0]["sha256"]) == 64


def test_gate_requires_reported_secondary(project):
    primed(project)
    draft = f"{MATTER}/drafts/memo.md"
    out = gate(project, write(project, draft, f"See {REST} cmt. b (Am. L. Inst. 1965)."))
    assert "no reported secondary-source entry" in out["permissionDecisionReason"]
    request(project, spec())
    assert gate(project, write(project, f"{MATTER}/audit/secondary-reports/SR-001.md", GOOD_REPORT)) is None
    report(project, "SR-001", GOOD_REPORT)
    assert gate(project, write(project, draft, f"See {REST} cmt. b (Am. L. Inst. 1965).")) is None
    out = gate(project, write(project, draft, "See 57A Am. Jur. 2d Negligence § 620 (2024)."))
    assert "no reported secondary-source entry" in out["permissionDecisionReason"]
    out = gate(project, write(project, draft, "See Annotation, 12 A.L.R.4th 123 (1982)."))
    assert "Westlaw relay" in out["permissionDecisionReason"]


def test_list_and_withdraw(project):
    primed(project)
    request(project, spec())
    out = run_script("ledger.py", ["secondary", "list", MATTER], None, project).stdout.decode()
    assert "SR-001 [requested]" in out
    assert run_script("ledger.py", ["secondary", "withdraw", MATTER, "SR-001"], None, project).returncode == 0
    assert json.loads((project / MATTER / "authorities.json").read_text(encoding="utf-8"))["authorities"][-1]["status"] == "withdrawn"
