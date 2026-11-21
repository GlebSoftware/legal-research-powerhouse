"""bluebook_case.py against real CourtListener cluster records (fixtures/bluebook_clusters.json, retrieved 2026-10-16)."""

import json

import pytest

import bluebook_case as bc
from conftest import FIXTURES

CLUSTERS = {e["source"]["cluster_id"]: e for e in json.loads((FIXTURES / "bluebook_clusters.json").read_text(encoding="utf-8"))}

GEORGIA = {  # cluster: (academic, Georgia filing)
    1233119: ("*Lau's Corp. v. Haskins*, 405 S.E.2d 474 (Ga. 1991).", "*Lau's Corp. v. Haskins*, 261 Ga. 491, 405 S.E.2d 474 (1991)."),
    1292587: ("*Robinson v. Kroger Co.*, 493 S.E.2d 403 (Ga. 1997).", "*Robinson v. Kroger Co.*, 268 Ga. 735, 493 S.E.2d 403 (1997)."),
    2392116: ("*Cowart v. Widener*, 697 S.E.2d 779 (Ga. 2010).", "*Cowart v. Widener*, 287 Ga. 622, 697 S.E.2d 779 (2010)."),
    1287925: ("*Cameron v. Lang*, 549 S.E.2d 341 (Ga. 2001).", "*Cameron v. Lang*, 274 Ga. 122, 549 S.E.2d 341 (2001)."),
    1346679: ("*State v. Jackson*, 697 S.E.2d 757 (Ga. 2010).", "*State v. Jackson*, 287 Ga. 646, 697 S.E.2d 757 (2010)."),
    1292540: ("*Desai v. Silver Dollar City, Inc.*, 493 S.E.2d 540 (Ga. Ct. App. 1997).",
              "*Desai v. Silver Dollar City, Inc.*, 229 Ga. App. 160, 493 S.E.2d 540 (1997)."),
    1317228: ("*Hodge v. SADA Enters., Inc.*, 458 S.E.2d 876 (Ga. Ct. App. 1995).",
              "*Hodge v. SADA Enters., Inc.*, 217 Ga. App. 688, 458 S.E.2d 876 (1995)."),
    2753057: ("*Holcomb v. Long*, 765 S.E.2d 687 (Ga. Ct. App. 2014).", "*Holcomb v. Long*, 329 Ga. App. 515, 765 S.E.2d 687 (2014)."),
    1262558: ("*Strickland v. DeKalb Hosp. Auth.*, 397 S.E.2d 576 (Ga. Ct. App. 1990).",
              "*Strickland v. DeKalb Hosp. Auth.*, 197 Ga. App. 63, 397 S.E.2d 576 (1990)."),
    1409267: ("*Mattox v. Metro. Atlanta Rapid Transit Auth.*, 409 S.E.2d 267 (Ga. Ct. App. 1991).",
              "*Mattox v. Metro. Atlanta Rapid Transit Auth.*, 200 Ga. App. 697, 409 S.E.2d 267 (1991)."),
}

FEDERAL = {
    145875: "*Ashcroft v. Iqbal*, 556 U.S. 662 (2009).",
    1087956: "*Farmer v. Brennan*, 511 U.S. 825 (1994).",
    117864: "*Heck v. Humphrey*, 512 U.S. 477 (1994).",
    145918: "*Pearson v. Callahan*, 555 U.S. 223 (2009).",
    145738: "*Scott v. Harris*, 550 U.S. 372 (2007).",
    2815299: "*Weiland v. Palm Beach Cnty. Sheriff's Off.*, 792 F.3d 1313 (11th Cir. 2015).",
    75789: "*Lee v. Ferraro*, 284 F.3d 1188 (11th Cir. 2002).",
    149841: "*Randall v. Scott*, 610 F.3d 701 (11th Cir. 2010).",
    2471309: "*Anderson v. Dunbar Armored, Inc.*, 678 F. Supp. 2d 1280 (N.D. Ga. 2009).",
    7320030: "*Williams ex rel. Williams v. Fulton Cnty. Sch. Dist.*, 181 F. Supp. 3d 1089 (N.D. Ga. 2016).",
}


@pytest.mark.parametrize("cluster", sorted(GEORGIA))
def test_georgia_both_modes(cluster):
    academic, filing = GEORGIA[cluster]
    assert bc.format_case(CLUSTERS[cluster], "academic")["full"] == academic
    assert bc.format_case(CLUSTERS[cluster], "ga")["full"] == filing


@pytest.mark.parametrize("cluster", sorted(FEDERAL))
def test_federal_same_in_both_modes(cluster):
    assert bc.format_case(CLUSTERS[cluster], "academic")["full"] == FEDERAL[cluster]
    assert bc.format_case(CLUSTERS[cluster], "ga")["full"] == FEDERAL[cluster]


def test_given_names_are_flagged():
    flags = bc.format_case(CLUSTERS[2815299], "academic")["flags"]
    assert any("Christopher J. Weiland" in f for f in flags)


def test_slip_form_for_a_case_without_reporter_cites():
    out = bc.format_case(CLUSTERS[10975757], "ga")
    assert out["full"] == "*Lafargue v. State*, No. S26A0676 (Ga. June 16, 2026)."
    assert any("slip form" in f for f in out["flags"])


BECKS = {"id": "cl-cluster-1266402", "type": "case", "status": "retrieved", "pagination": True,
         "citation": {"case_name": "Becks v. Pierce", "court_id": "gactapp", "date_filed": "2006-11-02",
                      "reporters": [{"volume": "638", "reporter": "S.E.2d", "page": "390", "type": 3},
                                    {"volume": "282", "reporter": "Ga. App.", "page": "229", "type": 2},
                                    {"volume": "2006", "reporter": "Fulton County D. Rep.", "page": "3412", "type": 2}]}}


def test_georgia_filing_pin_on_official_reporter():
    out = bc.format_case(BECKS, "ga", pin="234", pin_reporter="Ga. App.")
    assert out["full"] == "*Becks v. Pierce*, 282 Ga. App. 229, 234, 638 S.E.2d 390 (2006)."
    assert out["short"] == "*Becks*, 282 Ga. App. at 234."
    assert any("S.E.2d pin missing" in f for f in out["flags"])


def test_academic_refuses_a_pin_from_the_other_reporter():
    out = bc.format_case(BECKS, "academic", pin="234", pin_reporter="Ga. App.")
    assert out["full"] == "*Becks v. Pierce*, 638 S.E.2d 390 (Ga. Ct. App. 2006)."
    assert any("Ga. App. page" in f for f in out["flags"])


def test_short_form_skips_generic_party():
    out = bc.format_case(CLUSTERS[1346679], "academic", pin="760")
    assert out["short"] == "*Jackson*, 697 S.E.2d at 760."


# Captions from the Test 2 ledger (research/torts/proximate-cause-georgia), as CourtListener stores them.
def test_party_named_by_initials_keeps_the_initials():
    name, flags = bc.case_name("Goldstein, Garber & Salama, LLC v. J. B.")
    assert name == "Goldstein, Garber & Salama, LLC v. J. B." and not flags


def test_capitals_caption_is_title_cased_and_flagged():
    name, flags = bc.case_name("JOHNSON v. AVIS RENT a CAR SYSTEM, LLC (Two Cases)")
    assert name == "Johnson v. Avis Rent a Car Sys., LLC"
    assert any("capitals" in f for f in flags)


def test_dba_alternative_name_is_omitted():
    name, _ = bc.case_name("SECUREALERT, INC. D/B/A TRACK GROUP, INC. v. CANDACE BOGGS")
    assert name == "Securealert, Inc. v. Boggs"
