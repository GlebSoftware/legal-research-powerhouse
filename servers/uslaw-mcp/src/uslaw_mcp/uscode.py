"""Local U.S. Code mirror: USLM XML release-point zips from uscode.house.gov parsed into SQLite with FTS5.

Release points are named by the last public law they include (for example 119-121). Each section row records the
release point, so a citation can state the Code's currency exactly. The parser reads USLM `section` elements by
local name and identifier (/us/usc/t<title>/s<section>), without depending on the namespace version.
Status: parser checked against the USLM element names only; verify on the first real build (see the plan).
"""

from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .common import repo_root

BASE = "https://uscode.house.gov/download/releasepoints/us/pl"
IDENT_RE = re.compile(r"^/us/usc/t(\w+)/s([\w.\-]+)$")


def db_path() -> Path:
    p = repo_root() / "data" / "uscode" / "uscode.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect(path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(path or db_path())
    con.execute("CREATE TABLE IF NOT EXISTS sections (title TEXT, section TEXT, heading TEXT, text TEXT, "
                "release_point TEXT, identifier TEXT, status TEXT, PRIMARY KEY (title, section))")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(title, section, heading, text, "
                "content='sections', content_rowid='rowid')")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return con


def zip_url(release_point: str, title: str | None) -> str:
    congress, law = release_point.split("-")
    name = f"xml_usc{int(title):02d}@{release_point}.zip" if title else f"xml_uscAll@{release_point}.zip"
    return f"{BASE}/{congress}/{law}/{name}"


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_title_xml(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    rows = []
    for el in root.iter():
        if local(el.tag) != "section":
            continue
        m = IDENT_RE.match(el.get("identifier") or "")
        if not m:
            continue
        heading = next((("".join(c.itertext())).strip() for c in el if local(c.tag) == "heading"), "")
        parts = []
        for c in el:
            name = local(c.tag)
            if name in ("num", "heading"):
                continue
            if name in ("sourceCredit", "notes"):
                continue
            parts.append(" ".join("".join(c.itertext()).split()))
        rows.append({"title": m.group(1), "section": m.group(2), "heading": heading,
                     "text": "\n".join(p for p in parts if p), "identifier": el.get("identifier"),
                     "status": el.get("status") or "current"})
    return rows


def load_zip(con: sqlite3.Connection, zip_bytes: bytes, release_point: str) -> int:
    n = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            if not name.lower().endswith(".xml"):
                continue
            for r in parse_title_xml(z.read(name)):
                con.execute("INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?,?,?)",
                            (r["title"], r["section"], r["heading"], r["text"], release_point, r["identifier"], r["status"]))
                n += 1
    con.execute("INSERT INTO sections_fts(sections_fts) VALUES ('rebuild')")
    con.execute("INSERT OR REPLACE INTO meta VALUES ('release_point', ?)", (release_point,))
    con.commit()
    return n


def get_section(title: str, section: str, path: Path | None = None) -> dict | None:
    if not (path or db_path()).is_file():
        return None
    con = connect(path)
    row = con.execute("SELECT title, section, heading, text, release_point, identifier, status FROM sections "
                      "WHERE title = ? AND section = ?", (str(title), str(section))).fetchone()
    if not row:
        return None
    keys = ("title", "section", "heading", "text", "release_point", "identifier", "status")
    return dict(zip(keys, row))


def search(query: str, title: str | None = None, limit: int = 20, path: Path | None = None) -> list[dict]:
    if not (path or db_path()).is_file():
        return []
    con = connect(path)
    sql = ("SELECT s.title, s.section, s.heading, snippet(sections_fts, 3, '[', ']', ' … ', 24), s.release_point "
           "FROM sections_fts JOIN sections s ON s.rowid = sections_fts.rowid WHERE sections_fts MATCH ?")
    args: list = [query]
    if title:
        sql += " AND s.title = ?"
        args.append(str(title))
    sql += " ORDER BY rank LIMIT ?"
    args.append(limit)
    return [{"title": t, "section": s, "heading": h, "excerpt": x, "release_point": rp}
            for t, s, h, x, rp in con.execute(sql, args).fetchall()]
