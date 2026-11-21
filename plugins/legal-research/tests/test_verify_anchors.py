import json

import verify_anchors as va
from conftest import FIXTURES

BECKS = json.loads(json.loads((FIXTURES / "PostToolUse-courtlistener-read_document-full-1266402.json")
                              .read_text(encoding="utf-8"))["tool_response"][0]["text"])["text"]


def test_exact_quote_reports_star_page():
    r = va.anchor(BECKS, "the Bar’s policy cannot supplant the statutory requirement that the defendant have knowledge "
                         "that the person will soon be driving when served his last drink")
    assert r["status"] == "anchored" and r["page"] == "234"


def test_quote_across_markup_and_curly_quotes():
    r = va.anchor(BECKS, "provider in the exercise of reasonable care should have known both that the recipient of the "
                         "alcohol was noticeably intoxicated and that the recipient would be driving soon")
    assert r["status"] == "anchored" and r["method"] == "normalized" and r["page"] == "233"


def test_bluebook_ellipsis():
    r = va.anchor(BECKS, "Rather, if a provider in the exercise of reasonable care should have known . . . that the "
                         "recipient would be driving soon")
    assert r["status"] == "anchored" and len(r["segments"]) == 2


def test_footnote_digits_do_not_break_a_quote():
    # Source: "...under the Dram Shop Act (the “Act”).<a class="footnote">1</a> Becks filed a motion..."
    r = va.anchor(BECKS, "under the Dram Shop Act (the “Act”). Becks filed a motion for summary judgment")
    assert r["status"] == "anchored"


def test_invented_quote_fails():
    r = va.anchor(BECKS, "the Bar must ask every patron how he plans to get home")
    assert r["status"] == "anchor_failed" and r["reason"] == "not_found"


def test_secondary_entry_anchors_to_reported_quotes(tmp_path):
    entry = {"type": "secondary", "status": "reported", "report": {"quotes": [{"text": "a short quotation the memo will use"}]}}
    assert va.anchor_for_entry(tmp_path, entry, "a short quotation the memo will use")["status"] == "anchored"
    assert va.anchor_for_entry(tmp_path, entry, "a quotation the user never brought back")["status"] == "anchor_failed"
    entry["status"] = "requested"
    assert va.anchor_for_entry(tmp_path, entry, "a short quotation the memo will use")["reason"] == "secondary_not_reported"


GOLDSTEIN = (FIXTURES / "goldstein-page-number-excerpt.html").read_text(encoding="utf-8")


def test_page_number_markup_and_opening_alteration():
    # Goldstein, Garber & Salama, LLC v. J. B., 300 Ga. 840 (2017): <page-number label="N"> markup, "[a] wrongdoer".
    r = va.anchor(GOLDSTEIN, "A wrongdoer is not responsible for a consequence which is merely possible, according to occasional experience")
    assert r["status"] == "anchored" and r["page"] == "842"
    assert any(w["code"] == "first_word_unmatched" for w in r["warnings"])
