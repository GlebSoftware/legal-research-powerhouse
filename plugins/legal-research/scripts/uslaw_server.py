# /// script
# requires-python = ">=3.12"
# ///
"""Start the uslaw-mcp server (stdio) from wherever the plugin was loaded.

Loaded from the repo (--plugin-dir), the server sits at <plugin>/../../servers/uslaw-mcp. An installed copy under
~/.claude/plugins/cache has no such sibling, so the launcher tries the session's project folder (CLAUDE_PROJECT_DIR,
then the working directory), then the folder the `alr` marketplace was added from. Writes nothing to stdout: stdout
belongs to the MCP protocol.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REL = Path("servers") / "uslaw-mcp"


def candidates() -> list[Path]:
    out = [Path(__file__).resolve().parents[3] / REL]
    for base in (os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd()):
        if base:
            out.append(Path(base) / REL)
    known = Path.home() / ".claude" / "plugins" / "known_marketplaces.json"
    try:
        loc = json.loads(known.read_text(encoding="utf-8")).get("alr", {}).get("installLocation")
        if loc:
            out.append(Path(loc) / REL)
    except (OSError, ValueError):
        pass
    return out


def main() -> int:
    for d in candidates():
        if (d / "pyproject.toml").is_file():
            return subprocess.call(["uv", "run", "--quiet", "--directory", str(d), "uslaw-mcp"])
    print("uslaw_server: servers/uslaw-mcp not found beside the plugin, in the project folder, or at the alr "
          "marketplace path", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
