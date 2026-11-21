# /// script
# requires-python = ">=3.12"
# ///
"""Dump the raw hook stdin JSON to .session/hook-samples/ for field-name discovery.

Development aid for Phase 1. Always exits 0 and prints nothing, so it never alters a tool call.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"_unparsed": raw}
    event = payload.get("hook_event_name", "unknown")
    tool = re.sub(r"[^A-Za-z0-9_.-]", "_", str(payload.get("tool_name", "none")))[:80]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
    out = root / ".session" / "hook-samples"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{event}-{tool}-{stamp}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
