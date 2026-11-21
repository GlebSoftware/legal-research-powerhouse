"""Open in Westlaw links in the KeyCite checklist (Cornell LII's find-by-citation form)."""

import keycite_checklist as kc


def test_case_link_uses_the_first_reporter_cite():
    e = {"type": "case", "citation": {"reporters": [
        {"volume": "1877", "reporter": "U.S. LEXIS", "page": "2227"},
        {"volume": "95", "reporter": "U.S.", "page": "714"}]}}
    assert kc.westlaw_url(e) == "https://a.next.westlaw.com/Link/Document/FullText?findType=Y&cite=95%20U.S.%20714"


def test_statute_link_drops_the_year_and_secondary_gets_none():
    e = {"type": "statute", "citation": {"cite_as": "O.C.G.A. § 51-12-9 (2025)"}}
    assert kc.westlaw_url(e).endswith("cite=O.C.G.A.%20%C2%A7%2051-12-9")
    assert kc.westlaw_url({"type": "secondary", "citation": {}}) is None
    assert kc.westlaw_url({"type": "case", "citation": {"reporters": []}}) is None
