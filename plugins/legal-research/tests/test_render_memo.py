"""Token resolution and .docx output from real Test 2 ledger entries (research/torts/proximate-cause-georgia)."""

import json

import pytest

import render_memo as rm
from conftest import FIXTURES

LEDGER = json.loads((FIXTURES / "render-ledger.json").read_text(encoding="utf-8"))
GOLD_FULL = "*Goldstein, Garber & Salama, LLC v. J. B.*, 300 Ga. 840, 841, 797 S.E.2d 87 (2017)"


def test_first_reference_full_then_id_then_short():
    text = ("The rule insulates the defendant. [[src:cl-cluster-5749642 841]]. The exception turns on foreseeability. "
            "[[src:cl-cluster-5749642 842]]. Johnson applied it. [[src:cl-cluster-10367807 592]]. "
            "Goldstein controls. [[src:cl-cluster-5749642 843]].")
    out, auth = rm.resolve(text, LEDGER, "ga")
    assert GOLD_FULL + "." in out
    assert "*Id.* at 842." in out and "Id.*." not in out
    assert "*Johnson v. Avis Rent a Car Sys., LLC*, 311 Ga. 588, 592, 858 S.E.2d 23 (2021)." in out
    assert "*Goldstein, Garber & Salama*, 300 Ga. at 843." in out
    assert [a["id"] for a in auth] == ["cl-cluster-5749642", "cl-cluster-10367807"]
    assert auth[0]["full"] == "*Goldstein, Garber & Salama, LLC v. J. B.*, 300 Ga. 840, 797 S.E.2d 87 (2017)"


def test_id_is_lowercase_after_a_signal():
    out, _ = rm.resolve("A. [[src:cl-cluster-5749642 841]]. B. See [[src:cl-cluster-5749642 842]].", LEDGER, "ga")
    assert "See *id.* at 842." in out


def test_string_citation_cuts_the_id_chain():
    text = "A. [[src:cl-cluster-5749642 841]]; [[src:cl-cluster-10367807 592]]. B. [[src:cl-cluster-10367807 593]]."
    out, _ = rm.resolve(text, LEDGER, "ga")
    assert "*Id.*" not in out
    assert "*Johnson*, 311 Ga. at 593." in out


def test_statute_full_then_id_then_short():
    text = "A. [[src:gc-code-51-12-9]]. B. [[src:gc-code-51-12-9]]. C. [[src:cl-cluster-5749642 841]]. D. [[src:gc-code-51-12-9]]."
    out, auth = rm.resolve(text, LEDGER, "ga")
    assert "A. O.C.G.A. § 51-12-9 (2025)." in out
    assert "B. *Id.* C." in out
    assert "D. O.C.G.A. § 51-12-9." in out
    assert {a["kind"] for a in auth} == {"statute", "case"}


def test_unreported_secondary_source_stops_the_render():
    with pytest.raises(rm.RenderError, match="requested"):
        rm.resolve("A. [[src:sec-SR-001]].", LEDGER, "ga")


def test_unknown_token_stops_the_render():
    with pytest.raises(rm.RenderError, match="no ledger entry"):
        rm.resolve("A. [[src:cl-cluster-1]].", LEDGER, "ga")


def test_toa_and_docx(tmp_path):
    md = "# Memorandum\n\nTo: Professor\n\n## Discussion\n\nThe rule. [[src:cl-cluster-5749642 841]]. Remoteness. [[src:gc-code-51-12-9]].\n\n> Quoted text.\n\n- a point\n"
    out, auth = rm.resolve(md, LEDGER, "ga")
    final = rm.insert_toa(out, rm.toa_block(auth))
    assert final.index("To: Professor") < final.index("## Table of Authorities") < final.index("## Discussion")
    assert "### Cases" in final and "### Constitutions, Statutes, and Regulations" in final
    path = tmp_path / "memo.docx"
    rm.to_docx(final, path)
    from docx import Document

    doc = Document(str(path))
    styles = [p.style.name for p in doc.paragraphs]
    assert styles[0] == "Title" and "Heading 1" in styles and "Quote" in styles and "List Bullet" in styles
    italic = [r.text for p in doc.paragraphs for r in p.runs if r.italic]
    assert "Goldstein, Garber & Salama, LLC v. J. B." in italic
