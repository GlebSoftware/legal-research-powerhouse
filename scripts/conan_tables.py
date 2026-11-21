"""Constitution Annotated tables to JSON for the uslaw-mcp conan_* tools (architecture section 5, step 6).

constitution.congress.gov serves the tables behind a bot challenge, and GovInfo carries no CONAN collection, so
the tables arrive by hand: the user opens each page in their browser and downloads its CSV export (or saves the page as
HTML only) to data/conan/raw/. The CSV wins when both exist. Then:

  uv run python scripts/conan_tables.py

Pages: https://constitution.congress.gov/resources/decisions-overruled/ -> data/conan/raw/decisions-overruled.csv
       https://constitution.congress.gov/resources/unconstitutional-laws/ -> data/conan/raw/unconstitutional-laws.csv
Writes data/conan/<name>.json: {title, source_url, saved_at, columns, rows}. Refresh monthly.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "decisions-overruled": "https://constitution.congress.gov/resources/decisions-overruled/",
    "unconstitutional-laws": "https://constitution.congress.gov/resources/unconstitutional-laws/",
}


class Tables(HTMLParser):
    """Every <table> as a list of rows of cell texts; header cells marked."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[tuple[bool, list[str]]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._header_row = False
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row, self._header_row = [], False
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._header_row = self._header_row or tag == "th"
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            if any(self._row):
                self.tables[-1].append((self._header_row, self._row))
            self._row = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._in_title:
            self.title += data


def parse(html_text: str) -> tuple[str, list[str], list[dict]]:
    p = Tables()
    p.feed(html_text)
    columns: list[str] = []
    rows: list[dict] = []
    for table in p.tables:
        for is_header, cells in table:
            if is_header and not columns:
                columns = cells
            elif not is_header:
                cols = columns or [f"col{i + 1}" for i in range(len(cells))]
                rows.append({cols[i] if i < len(cols) else f"col{i + 1}": c for i, c in enumerate(cells)})
    return p.title.strip(), columns, rows


TITLES = {
    "decisions-overruled": "Table of Supreme Court Decisions Overruled by Subsequent Decisions",
    "unconstitutional-laws": "Table of Laws Held Unconstitutional in Whole or in Part by the Supreme Court",
}


def parse_csv(text: str) -> tuple[list[str], list[dict]]:
    """The page's own CSV export: a header row, then one row per entry. A blank first header is the row number."""
    reader = csv.reader(io.StringIO(text))
    header = [re.sub(r"\s+", " ", h.replace("\xa0", " ")).strip() for h in next(reader, [])]
    columns = [h or "Number" for h in header]
    rows = [{columns[i] if i < len(columns) else f"col{i + 1}": re.sub(r"\s+", " ", c).strip() for i, c in enumerate(cells)}
            for cells in reader if any(c.strip() for c in cells)]
    return columns, rows


def main() -> int:
    raw = ROOT / "data" / "conan" / "raw"
    done = 0
    for name, url in PAGES.items():
        src_csv, src = raw / f"{name}.csv", raw / f"{name}.html"
        if src_csv.is_file():  # the CSV export button on each table page
            src = src_csv
            columns, rows = parse_csv(src.read_text(encoding="utf-8-sig", errors="replace"))
            title = TITLES[name]
        elif src.is_file():
            title, columns, rows = parse(src.read_text(encoding="utf-8", errors="replace"))
        else:
            print(f"missing {src_csv}: download the CSV from {url} by hand", file=sys.stderr)
            continue
        if not rows:
            print(f"{src}: no table rows found; the saved page may be the bot-challenge page", file=sys.stderr)
            continue
        saved = datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out = {"title": title, "source_url": url, "saved_at": saved, "columns": columns, "rows": rows}
        (ROOT / "data" / "conan" / f"{name}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n",
                                                             encoding="utf-8", newline="\n")
        print(f"{name}: {len(rows)} rows, columns {columns}")
        done += 1
    return 0 if done == len(PAGES) else 1


if __name__ == "__main__":
    sys.exit(main())
