# /// script
# requires-python = ">=3.12"
# ///
"""Saved sources of a matter with hash verification (ADR-2: drafting reads from sources/, so the files must not drift).

  sources_status.py <matter> [--json]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def status(matter: Path) -> list[dict]:
    manifest = matter / "sources" / "manifest.jsonl"
    latest: dict[str, dict] = {}
    if manifest.is_file():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            latest[row["path"]] = row  # the newest line for a path is the one in force
    rows = []
    for rel, row in sorted(latest.items()):
        p = matter / rel
        if not p.is_file():
            state = "missing"
        else:
            state = "ok" if hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest() == row.get("sha256") else "CHANGED"
        rows.append({"id": row.get("id"), "path": rel, "system": row.get("system"), "retrieved_at": row.get("retrieved_at"),
                     "bytes": row.get("bytes"), "status": state})
    return rows


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    rows = status(Path(args[0]))
    if "--json" in args:
        print(json.dumps(rows, indent=1))
    else:
        print("| id | file | system | retrieved | bytes | hash |\n|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['id']} | {r['path']} | {r['system']} | {r['retrieved_at']} | {r['bytes']} | {r['status']} |")
        bad = [r for r in rows if r["status"] != "ok"]
        print(f"\n{len(rows)} sources, {len(bad)} changed or missing.")
    return 1 if any(r["status"] != "ok" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
