import json
from pathlib import Path

import jsonschema

from conftest import PLUGIN, fixture, gc_payload, run_script

SCHEMA = json.loads((PLUGIN / "schemas" / "authority.schema.json").read_text(encoding="utf-8"))
MATTER = "research/legal-writing/closed-memo-dram-shop"


def ledger(project: Path) -> dict:
    data = json.loads((project / MATTER / "authorities.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, SCHEMA)
    return data


def create(project: Path, *extra: str):
    r = run_script("ledger.py", ["create", MATTER, *extra], None, project)
    assert r.returncode == 0, r.stderr.decode()


def full_read_payload() -> dict:
    """The full read_document result for Becks v. Pierce captured in the live Test 1 run."""
    return fixture("PostToolUse-courtlistener-read_document-full-1266402")


def test_create_sets_layout_and_active_matter(project):
    create(project, "--closed-universe")
    m = project / MATTER
    assert all((m / d).is_dir() for d in ("sources", "notes", "drafts", "audit"))
    assert ledger(project)["closed_universe"] is True
    assert (project / ".session" / "active-matter").read_text().strip() == MATTER


def test_search_hit_creates_candidate(project):
    create(project)
    r = run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    assert r.returncode == 0 and r.stdout == b""
    [e] = ledger(project)["authorities"]
    assert e["id"] == "cl-cluster-1266402"
    assert e["status"] == "candidate" and e["verification"]["existence"] == "listed"
    assert e["citation"]["case_name"] == "Becks v. Pierce"
    assert {"volume": "638", "reporter": "S.E.2d", "page": "390", "type": None} in e["citation"]["reporters"]
    assert {"volume": "282", "reporter": "Ga. App.", "page": "229", "type": None} in e["citation"]["reporters"]
    assert "2006 Ga. App. LEXIS 1360" in e["citation"]["other_cites"]
    assert e["source"]["opinion_ids"] == [1266402]


def test_full_read_saves_source_and_verifies(project):
    create(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    run_script("ledger.py", ["ingest"], full_read_payload(), project)
    [e] = ledger(project)["authorities"]
    assert e["status"] == "retrieved" and e["verification"]["existence"] == "verified"
    assert e["citation"]["case_name"] == "Becks v. Pierce"
    saved = project / MATTER / e["local_path"]
    assert saved.suffix == ".xml" and "Dram Shop Act" in saved.read_text(encoding="utf-8")
    assert e["pagination"] is True
    manifest = (project / MATTER / "sources" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(manifest[-1])["sha256"] == e["sha256"]


def test_full_read_in_hosted_server_shape_is_saved(project):
    """The hosted server returns cluster_id and opinion_id with no doc_type or doc_id."""
    create(project)
    payload = full_read_payload()
    body = json.loads(payload["tool_response"][0]["text"])
    body = {"cluster_id": 1266402, "opinion_id": body.pop("doc_id"),
            **{k: v for k, v in body.items() if k != "doc_type"}}
    payload["tool_response"][0]["text"] = json.dumps(body)
    r = run_script("ledger.py", ["ingest"], payload, project)
    assert r.returncode == 0, r.stderr.decode()
    [e] = ledger(project)["authorities"]
    assert e["status"] == "retrieved" and e["verification"]["existence"] == "verified"
    assert "Dram Shop Act" in (project / MATTER / e["local_path"]).read_text(encoding="utf-8")
    assert 1266402 in e["source"]["opinion_ids"]


def test_hosted_read_by_opinion_id_promotes_the_search_entry(project):
    """A read by opinion_id returns only opinion_id, total_chars, and text; it still promotes the ledger entry."""
    create(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    payload = full_read_payload()
    body = json.loads(payload["tool_response"][0]["text"])
    payload["tool_input"] = {"opinion_id": 1266402}
    payload["tool_response"][0]["text"] = json.dumps(
        {"opinion_id": 1266402, "total_chars": body["total_chars"], "text": body["text"]})
    r = run_script("ledger.py", ["ingest"], payload, project)
    assert r.returncode == 0, r.stderr.decode()
    [e] = ledger(project)["authorities"]
    assert e["id"] == "cl-cluster-1266402" and e["status"] == "retrieved"


def test_chunked_read_waits_for_all_chunks(project):
    create(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__read_document"), project)
    [e] = ledger(project)["authorities"]
    assert e["status"] == "candidate"
    assert e["partial_read"]["chunks_present"] == 1 and e["partial_read"]["total_chunks"] == 10


def test_georgia_commons_section(project):
    create(project)
    run_script("ledger.py", ["ingest"], gc_payload(), project)
    [e] = ledger(project)["authorities"]
    assert e["id"] == "gc-code-51-1-40" and e["type"] == "statute"
    assert e["citation"]["code"] == "O.C.G.A." and e["citation"]["section"] == "51-1-40"
    assert e["citation"]["heading"] == "Liability for acts of intoxicated persons."
    assert e["verification"]["existence"] == "verified"
    assert (project / MATTER / e["local_path"]).read_text(encoding="utf-8").startswith("---")


def test_verify_quote_recorded(project):
    create(project)
    run_script("ledger.py", ["ingest"], gc_payload(), project)
    vq = {"hook_event_name": "PostToolUse", "tool_name": "mcp__georgiacommons__verify_quote",
          "tool_input": {"id": "51-1-40", "quote": "rather than the"},
          "tool_response": [{"type": "text", "text": json.dumps({"id": "51-1-40", "verified": True, "occurrences": 1})}],
          "mcp_server": {"name": "georgiacommons", "source": "user"}}
    run_script("ledger.py", ["ingest"], vq, project)
    [e] = ledger(project)["authorities"]
    assert e["quote_checks"][0]["verified"] is True
    # Live shape from Test 1: the id comes back collection-prefixed.
    vq["tool_response"] = [{"type": "text", "text": json.dumps({"id": "code:51-1-40", "url": "https://georgiacommons.org/code/51-1-40",
                                                                "verified": True, "occurrences": 1, "source_field": "text", "chars": 114})}]
    run_script("ledger.py", ["ingest"], vq, project)
    [e] = ledger(project)["authorities"]
    assert len(e["quote_checks"]) == 2 and e["quote_checks"][1]["occurrences"] == 1


def test_no_active_matter_goes_to_inbox(project):
    run_script("ledger.py", ["ingest"], gc_payload(), project)
    assert (project / ".session" / "inbox" / "authorities.json").is_file()


def test_projects_without_research_dir_are_ignored(tmp_path):
    r = run_script("ledger.py", ["ingest"], gc_payload(), tmp_path)
    assert r.returncode == 0 and not (tmp_path / ".session").exists()
    r = run_script("session_hooks.py", ["start"], {}, tmp_path)
    assert r.returncode == 0 and r.stdout == b""


def test_non_mcp_and_garbage_are_ignored(project):
    create(project)
    r = run_script("ledger.py", ["ingest"], fixture("PostToolUse-Write"), project)
    assert r.returncode == 0
    r = run_script("ledger.py", ["ingest"], {"hook_event_name": "PostToolUse", "tool_name": "mcp__x__y",
                                             "tool_response": "not json"}, project)
    assert r.returncode == 0
    assert ledger(project)["authorities"] == []


def test_mark_keycite_and_list(project):
    create(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    run_script("ledger.py", ["ingest"], full_read_payload(), project)
    out = run_script("ledger.py", ["keycite-list"], None, project).stdout.decode()
    assert "cl-cluster-1266402" in out
    r = run_script("ledger.py", ["mark", MATTER, "cl-cluster-1266402", "keycite=green flag, no negative history"], None, project)
    assert r.returncode == 0, r.stderr.decode()
    mk = ledger(project)["authorities"][0]["treatment"]["manual_keycite"]
    assert mk["done"] is True and mk["result"].startswith("green")


def test_cluster_record_types_reporters_and_keeps_read_method(project):
    create(project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__search"), project)
    run_script("ledger.py", ["ingest"], full_read_payload(), project)
    run_script("ledger.py", ["ingest"], fixture("PostToolUse-courtlistener-get_endpoint_item-clusters"), project)
    [e] = ledger(project)["authorities"]
    reps = {(r["volume"], r["reporter"], r["page"]): r["type"] for r in e["citation"]["reporters"]}
    assert reps[("638", "S.E.2d", "390")] == 3 and reps[("282", "Ga. App.", "229")] == 2
    assert not any("LEXIS" in r for _v, r, _p in reps)
    assert e["citation"]["other_cites"] == ["2006 Ga. App. LEXIS 1360"]
    assert e["verification"]["method"] == "read_document"


def test_spilled_result_is_read_from_the_saved_file(project, tmp_path):
    """Results over the tool-output limit reach the hook as a pointer to the harness's tool-results file."""
    create(project)
    data = json.loads(full_read_payload()["tool_response"][0]["text"])
    spill = tmp_path / ".claude" / "projects" / "p" / "s" / "tool-results" / "mcp-x-read_document-1.txt"
    spill.parent.mkdir(parents=True)
    spill.write_text(json.dumps(data), encoding="utf-8")
    p = full_read_payload()
    p["tool_response"] = [{"type": "text", "text": f"Output too large (59.9KB). Full output saved to: {spill}"}]
    run_script("ledger.py", ["ingest"], p, project)
    [e] = ledger(project)["authorities"]
    assert e["status"] == "retrieved" and e["local_path"].startswith("sources/cl-cluster-1266402")


def test_spilled_content_blocks_are_unwrapped(project, tmp_path):
    """A .json spill holds the MCP content blocks; the hook reads the text inside them."""
    create(project)
    blocks = full_read_payload()["tool_response"]
    spill = tmp_path / ".claude" / "projects" / "p" / "s" / "tool-results" / "toolu_x.json"
    spill.parent.mkdir(parents=True)
    spill.write_text(json.dumps(blocks), encoding="utf-8")
    p = full_read_payload()
    p["tool_response"] = [{"type": "text", "text": f"<persisted-output>\nOutput too large (53.2KB). Full output saved to: {spill}\n"}]
    run_script("ledger.py", ["ingest"], p, project)
    [e] = ledger(project)["authorities"]
    assert e["status"] == "retrieved" and e["local_path"].startswith("sources/cl-cluster-1266402")


def test_pointer_outside_the_harness_folder_is_not_read(project, tmp_path):
    """A tool result naming some other tool-results file gets no special treatment."""
    create(project)
    data = json.loads(full_read_payload()["tool_response"][0]["text"])
    other = tmp_path / "elsewhere" / "tool-results" / "planted.txt"
    other.parent.mkdir(parents=True)
    other.write_text(json.dumps(data), encoding="utf-8")
    p = full_read_payload()
    p["tool_response"] = [{"type": "text", "text": f"Full output saved to: {other}"}]
    run_script("ledger.py", ["ingest"], p, project)
    assert not [e for e in ledger(project)["authorities"] if e["status"] == "retrieved"]
