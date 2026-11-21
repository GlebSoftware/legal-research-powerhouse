"""matter.py: the workbench's new-matter form, settings pickers, and matter list; jurisdictions.json contents."""

import json

import pytest

import build_jurisdictions as bj
import matter as mt
from conftest import PLUGIN, run_script

SEC_41 = ("The thirteen judicial circuits of the United States are constituted as follows: CircuitsComposition "
          "District of ColumbiaDistrict of Columbia. FirstMaine, Massachusetts, New Hampshire, Puerto Rico, Rhode Island. "
          "EleventhAlabama, Florida, Georgia. FederalAll Federal judicial districts.")


def test_new_matter_defaults_to_federal_and_becomes_active(project):
    r = run_script("matter.py", ["new", "Torts", "Proximate cause II", "--question", 'Does "but for" cause suffice?'],
                   None, project)
    assert r.returncode == 0, r.stderr.decode()
    m = project / "research" / "torts" / "proximate-cause-ii"
    meta, _ = mt.read_front(m / "question.md")
    assert meta["question"] == 'Does "but for" cause suffice?'
    assert meta["jurisdiction"] == "Federal (all federal courts)" and meta["jurisdiction_id"] == "federal"
    assert meta["closed_universe"] == "false"
    assert (m / "authorities.json").is_file() and (m / "plan.md").is_file() and (m / "drafts").is_dir()
    assert (project / ".session" / "active-matter").read_text(encoding="utf-8").strip() == "research/torts/proximate-cause-ii"


def test_jurisdiction_switch_keeps_the_question(project):
    mt.new(project, "torts", "dram shop", "When is a bar liable?")
    m = project / "research" / "torts" / "dram-shop"
    r = run_script("matter.py", ["set", "research/torts/dram-shop", "jurisdiction=Georgia"], None, project)
    assert r.returncode == 0, r.stderr.decode()
    meta, body = mt.read_front(m / "question.md")
    assert meta["jurisdiction"] == "Georgia" and meta["jurisdiction_id"] == "georgia"
    assert meta["question"] == "When is a bar liable?" and "Created from the workbench" in body
    mt.set_key(m, "jurisdiction", "federal")
    assert mt.read_front(m / "question.md")[0]["jurisdiction_id"] == "federal"


def test_errors_are_plain_sentences(project):
    mt.new(project, "torts", "dram shop", "When is a bar liable?")
    with pytest.raises(mt.MatterError, match="already exists"):
        mt.new(project, "torts", "dram shop", "Again?")
    with pytest.raises(mt.MatterError, match="No jurisdiction 'Narnia'"):
        mt.set_key(project / "research" / "torts" / "dram-shop", "jurisdiction", "Narnia")
    with pytest.raises(mt.MatterError, match="Write the research question first"):
        mt.new(project, "torts", "other", "  ")


def test_list_marks_the_active_matter(project):
    mt.new(project, "torts", "one", "Q1?")
    mt.new(project, "contracts", "two", "Q2?", jurisdiction="Georgia")
    rows = {r["name"]: r for r in mt.listing(project)}
    assert rows["two"]["active"] and not rows["one"]["active"]
    assert rows["two"]["jurisdiction"] == "Georgia"


def test_circuits_parse_from_28_usc_41():
    c = bj.circuits_from_41(SEC_41)
    assert c["Georgia"] == "ca11" and c["Maine"] == "ca1" and c["Washington D.C."] == "cadc"
    assert "Puerto Rico" not in c


def test_jurisdictions_file():
    data = json.loads((PLUGIN / "data" / "jurisdictions.json").read_text(encoding="utf-8"))
    j = {x["id"]: x for x in data["jurisdictions"]}
    assert data["default"] == "federal" and len(j) == 52
    assert j["federal"]["binding"][:2] == ["scotus", "ca1"] and "cafc" in j["federal"]["binding"]
    assert len(j["federal"]["federal"]) >= 90
    assert j["georgia"]["binding"] == ["ga", "gactapp"] and j["georgia"]["federal"][0] == "ca11"
    assert j["georgia"]["citation_mode"] == "ga" and j["new-york"]["citation_mode"] == "academic"
    assert all(x["binding"] for x in data["jurisdictions"])
