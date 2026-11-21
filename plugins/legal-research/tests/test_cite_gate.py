import json
from pathlib import Path

import pytest

from conftest import fixture, gc_payload, run_script
from test_ledger import MATTER, create, full_read_payload

FULL = "Becks v. Pierce, 282 Ga. App. 229, 638 S.E.2d 390 (2006)"


def write(project: Path, rel: str, content: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": str(project / rel), "content": content}}


def gate(project: Path, payload: dict) -> dict | None:
    r = run_script("cite_gate.py", [], payload, project)
    assert r.returncode == 0, r.stderr.decode()
    out = r.stdout.decode().strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


@pytest.fixture
def matter(project):
    create(project, "--closed-universe")
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    return project


def test_outside_research_passes(project):
    assert gate(project, write(project, "docs/x.md", "Smith v. Jones, 1 U.S. 1 (1790).")) is None


def test_notes_are_free(matter):
    assert gate(matter, write(matter, f"{MATTER}/notes/n.md", "Smith v. Jones says something")) is None


def test_bare_name_in_draft_denied(matter):
    out = gate(matter, write(matter, f"{MATTER}/drafts/memo.md", "Under Becks v. Pierce the bar wins."))
    assert out["permissionDecision"] == "deny"
    assert "Bare case name 'Becks v. Pierce'" in out["permissionDecisionReason"]


def test_candidate_not_yet_read_denied(matter):
    out = gate(matter, write(matter, f"{MATTER}/drafts/memo.md", f"See {FULL}."))
    assert out["permissionDecision"] == "deny" and "has not been read" in out["permissionDecisionReason"]


def test_retrieved_full_cite_allowed(matter):
    run_script("ledger.py", ["ingest"], full_read_payload(), matter)
    assert gate(matter, write(matter, f"{MATTER}/drafts/memo.md", f"See *{FULL}*. Becks v. Pierce controls.")) is None


def test_short_cite_and_id_allowed_after_read(matter):
    run_script("ledger.py", ["ingest"], full_read_payload(), matter)
    text = f"See {FULL}. The court reversed. Becks, 282 Ga. App. at 230. Id. at 231."
    assert gate(matter, write(matter, f"{MATTER}/drafts/memo.md", text)) is None


def test_unknown_case_denied(matter):
    out = gate(matter, write(matter, f"{MATTER}/drafts/memo.md",
                             "Griffin Motel Co. v. Strickland, 223 Ga. App. 812, 479 S.E.2d 401 (1996)."))
    assert "223 Ga. App. 812: no ledger entry" in out["permissionDecisionReason"]


def test_name_mismatch_denied(matter):
    run_script("ledger.py", ["ingest"], full_read_payload(), matter)
    out = gate(matter, write(matter, f"{MATTER}/drafts/memo.md", "Smith v. Jones, 638 S.E.2d 390 (Ga. Ct. App. 2006)."))
    assert "does not match" in out["permissionDecisionReason"]


def test_statute_requires_ledger(matter):
    out = gate(matter, write(matter, f"{MATTER}/drafts/memo.md", "O.C.G.A. § 51-1-40(b) governs."))
    assert "O.C.G.A. § 51-1-40(b): no ledger entry" in out["permissionDecisionReason"]
    run_script("ledger.py", ["ingest"], gc_payload(), matter)
    assert gate(matter, write(matter, f"{MATTER}/drafts/memo.md", "O.C.G.A. § 51-1-40(b) governs.")) is None


def test_federal_statute_denied_without_entry(matter):
    out = gate(matter, write(matter, f"{MATTER}/outline.md", "42 U.S.C. § 1983 applies."))
    assert "42 U.S.C." in out["permissionDecisionReason"]


def test_ledger_and_sources_locked(matter):
    out = gate(matter, write(matter, f"{MATTER}/authorities.json", "{}"))
    assert out["permissionDecision"] == "deny"
    out = gate(matter, write(matter, f"{MATTER}/sources/fake.xml", "<opinion/>"))
    assert out["permissionDecision"] == "deny"


def test_edit_checks_new_string_with_document_context(matter):
    run_script("ledger.py", ["ingest"], full_read_payload(), matter)
    draft = matter / MATTER / "drafts" / "memo.md"
    draft.write_text(f"See {FULL}.\n\nTODO\n", encoding="utf-8")
    edit = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": str(draft), "old_string": "TODO", "new_string": "Becks v. Pierce reversed.",
                           "replace_all": False}}
    assert gate(matter, edit) is None
    edit["tool_input"]["new_string"] = "Smith v. Jones went the other way."
    assert "Bare case name 'Smith v. Jones'" in gate(matter, edit)["permissionDecisionReason"]


def test_sampled_write_payload_outside_research_passes(project):
    assert gate(project, fixture("PreToolUse-Write")) is None


def test_token_for_unread_case_denied(matter):
    out = gate(matter, write(matter, f"{MATTER}/drafts/memo.md", "The bar wins. [[src:cl-cluster-1266402 234]]."))
    assert out["permissionDecision"] == "deny" and "has not been read" in out["permissionDecisionReason"]


def test_token_for_unknown_id_denied(matter):
    out = gate(matter, write(matter, f"{MATTER}/drafts/memo.md", "The bar wins. [[src:cl-cluster-1 2]]."))
    assert out["permissionDecision"] == "deny" and "no ledger entry with id cl-cluster-1" in out["permissionDecisionReason"]


def test_token_for_read_case_allowed_and_covers_the_bare_name(matter):
    run_script("ledger.py", ["ingest"], full_read_payload(), matter)
    text = "Becks v. Pierce controls. [[src:cl-cluster-1266402 234]]."
    assert gate(matter, write(matter, f"{MATTER}/drafts/memo.md", text)) is None
