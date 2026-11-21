"""uslaw-mcp results reach the ledger through ingest, and the gate then accepts the federal citation."""

from conftest import fixture, run_script
from test_cite_gate import gate, write
from test_ledger import MATTER, create, ledger


def test_ecfr_section_ingests_without_resaving(project):
    create(project)
    r = run_script("ledger.py", ["ingest"], fixture("PostToolUse-uslaw-ecfr_section"), project)
    assert r.returncode == 0
    [e] = ledger(project)["authorities"]
    assert e["id"] == "ecfr-15-744.11" and e["type"] == "regulation" and e["status"] == "retrieved"
    assert e["citation"]["code"] == "C.F.R." and e["citation"]["title"] == "15" and e["citation"]["section"] == "744.11"
    assert e["citation"]["version"] and e["verification"]["existence"] == "verified"
    assert e["local_path"] == "sources/ecfr-15-744.11.txt" and len(e["sha256"]) == 64
    assert not (project / MATTER / "sources" / "ecfr-15-744.11.txt").exists()  # the server saves; ingest only records


def test_gate_accepts_cfr_after_ingest(project):
    create(project)
    draft = f"{MATTER}/drafts/memo.md"
    out = gate(project, write(project, draft, "See 15 C.F.R. § 744.11(b) (2026)."))
    assert "no ledger entry" in out["permissionDecisionReason"]
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-uslaw-ecfr_section"), project)
    assert gate(project, write(project, draft, "See 15 C.F.R. § 744.11(b) (2026).")) is None


def test_gate_matches_federal_register_cites(project):
    create(project)
    entry = {"id": "fr-2026-17231", "type": "regulation", "status": "retrieved",
             "source": {"system": "federalregister"}, "citation": {"code": "Fed. Reg.", "title": "91", "section": "54658"},
             "verification": {"existence": "verified"}}
    r = run_script("ledger.py", ["upsert", MATTER, "-"], entry, project)
    assert r.returncode == 0, r.stderr.decode()
    draft = f"{MATTER}/drafts/memo.md"
    assert gate(project, write(project, draft, "Revisions to the Entity List, 91 Fed. Reg. 54658 (Aug. 24, 2026).")) is None
    out = gate(project, write(project, draft, "91 Fed. Reg. 99999 (2026)."))
    assert "no ledger entry" in out["permissionDecisionReason"]
