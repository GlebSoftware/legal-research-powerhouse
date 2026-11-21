"""Parsers for the U.S. Code mirror and the Constitution Annotated tables, on minimal inputs of each format."""

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "servers" / "uslaw-mcp" / "src"))

import conan_tables  # noqa: E402
from uslaw_mcp import uscode  # noqa: E402

USLM = b"""<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0"><main><title identifier="/us/usc/t1">
<section identifier="/us/usc/t1/s1"><num value="1">\xc2\xa7 1.</num><heading>Words denoting number, gender, and so forth</heading>
<content><p>In determining the meaning of any Act of Congress, unless the context indicates otherwise words importing the singular include and apply to several persons.</p></content>
<sourceCredit>(July 30, 1947, ch. 388, 61 Stat. 633.)</sourceCredit></section>
<section identifier="/us/usc/t1/s2"><num value="2">\xc2\xa7 2.</num><heading>"County" as including "parish", and so forth</heading>
<content>The word "county" includes a parish, or any other equivalent subdivision of a State or Territory.</content></section>
</title></main></uscDoc>"""


def test_uscode_parse_load_and_search(tmp_path):
    rows = uscode.parse_title_xml(USLM)
    assert [(r["title"], r["section"]) for r in rows] == [("1", "1"), ("1", "2")]
    assert "61 Stat." not in rows[0]["text"] and "singular include" in rows[0]["text"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("usc01.xml", USLM)
    db = tmp_path / "u.db"
    con = uscode.connect(db)
    assert uscode.load_zip(con, buf.getvalue(), "119-121") == 2
    row = uscode.get_section("1", "2", db)
    assert row["release_point"] == "119-121" and row["heading"].startswith('"County"')
    hits = uscode.search("parish", path=db)
    assert hits and hits[0]["section"] == "2"


def test_zip_url():
    assert uscode.zip_url("119-121", "42").endswith("/119/121/xml_usc42@119-121.zip")
    assert uscode.zip_url("119-121", None).endswith("/119/121/xml_uscAll@119-121.zip")


def test_conan_table_parse():
    page = """<html><head><title>Table of Decisions Overruled</title></head><body><table>
    <tr><th>Overruled Decision</th><th>Overruling Decision</th></tr>
    <tr><td>Plessy v. Ferguson, 163 U.S. 537 (1896)</td><td>Brown v. Board of Education, 347 U.S. 483 (1954)</td></tr>
    </table></body></html>"""
    title, columns, rows = conan_tables.parse(page)
    assert title == "Table of Decisions Overruled" and columns == ["Overruled Decision", "Overruling Decision"]
    assert rows[0]["Overruling Decision"].startswith("Brown")


def test_conan_rejects_challenge_page():
    _t, _c, rows = conan_tables.parse("<html><title>Just a moment...</title><body>Checking</body></html>")
    assert rows == []
