"""Build the local U.S. Code mirror from a uscode.house.gov release point (architecture section 3.2).

  uv run --directory servers/uslaw-mcp python ../../scripts/uscode_mirror.py build --release 119-121 [--titles 1,42]
  uv run --directory servers/uslaw-mcp python ../../scripts/uscode_mirror.py status

`build` downloads the USLM XML zip for each title (or the whole Code, about 109 MB, when no titles are given) and
loads every section into data/uscode/uscode.db with its release point. It downloads files, so it runs only when
the user asks for it. The uslaw-mcp tools uscode_section and uscode_search read the database.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from uslaw_mcp import uscode
from uslaw_mcp.common import USER_AGENT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--release", required=True, help="release point, e.g. 119-121")
    b.add_argument("--titles", help="comma-separated title numbers; omitted, the whole Code")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    con = uscode.connect()
    if a.cmd == "status":
        rp = con.execute("SELECT value FROM meta WHERE key='release_point'").fetchone()
        n = con.execute("SELECT count(*), count(DISTINCT title) FROM sections").fetchone()
        print(f"release point: {rp[0] if rp else 'none'}; {n[0]} sections in {n[1]} titles; {uscode.db_path()}")
        return 0
    titles = [t.strip() for t in a.titles.split(",")] if a.titles else [None]
    with httpx.Client(timeout=300, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
        for t in titles:
            url = uscode.zip_url(a.release, t)
            print(f"downloading {url}")
            r = c.get(url)
            r.raise_for_status()
            n = uscode.load_zip(con, r.content, a.release)
            print(f"  loaded {n} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
