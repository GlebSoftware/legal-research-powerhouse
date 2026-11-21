"""Restatement quotations from real saved-opinion excerpts (Test 2 matter, 2026-10-16): SecureAlert (parenthetical
after the cite), Bradley Center ("Restatement, Torts, 2d" with the quotation before it and a star page inside it),
and Cowart (a 1900 case's quotation sits before the cite and must not pair with it)."""

import json

import restatement_quotes as rq
from conftest import FIXTURES

EXCERPTS = json.loads((FIXTURES / "restatement-excerpts.json").read_text(encoding="utf-8"))


def matter(tmp_path):
    (tmp_path / "sources").mkdir()
    entries = []
    for cid, ex in EXCERPTS.items():
        (tmp_path / "sources" / ex["file"]).write_text(ex["text"], encoding="utf-8")
        entries.append({"id": cid, "type": "case", "status": "retrieved", "local_path": f"sources/{ex['file']}",
                        "citation": {"case_name": cid}})
    return tmp_path, {"authorities": entries}


def test_parenthetical_quote_after_the_cite(tmp_path):
    m, ledger = matter(tmp_path)
    [row] = rq.collect(m, ledger, "448", "Torts", "Second")
    assert row["id"] == "cl-cluster-4503650" and row["anchored"]
    assert row["quote"].startswith("The act of a third person in committing an intentional tort or crime is a superseding cause")


def test_quote_before_the_cite_across_a_star_page(tmp_path):
    m, ledger = matter(tmp_path)
    rows = [r for r in rq.collect(m, ledger, "319", "Torts", "Second") if r["id"] == "cl-cluster-1339729"]
    assert rows and rows[0]["anchored"]
    assert rows[0]["quote"].startswith("One who takes charge of a third person whom he knows or should know")
    assert "*202" not in rows[0]["quote"]


def test_other_authority_quote_is_not_paired(tmp_path):
    m, ledger = matter(tmp_path)
    [row] = rq.collect(m, ledger, "314", "Torts", "Second")
    assert row["quote"].startswith("The fact that the actor realizes or should realize")


def test_series_and_section_must_match(tmp_path):
    m, ledger = matter(tmp_path)
    assert rq.collect(m, ledger, "448", "Torts", "Third") == []
    assert rq.collect(m, ledger, "44", "Torts", "Second") == []
