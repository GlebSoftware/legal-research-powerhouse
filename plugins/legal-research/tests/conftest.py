import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))


def fixture(prefix: str) -> dict:
    matches = sorted(FIXTURES.glob(prefix + "*.json"))
    assert matches, prefix
    return json.loads(matches[0].read_text(encoding="utf-8"))


def gc_payload() -> dict:
    """PostToolUse payload for Georgia Commons, built from a raw MCP tools/call result."""
    raw = fixture("georgiacommons-code_lookup_section-raw")
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "mcp__georgiacommons__code_lookup_section",
        "tool_input": {"citation": "O.C.G.A. § 51-1-40"},
        "tool_response": raw["result"]["content"],
        "tool_use_id": "toolu_test_gc",
        "mcp_server": {"name": "georgiacommons", "source": "user"},
    }


def run_script(name: str, args: list[str], payload: dict | None, project: Path, env: dict | None = None):
    full_env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project), "PYTHONIOENCODING": "utf-8"}
    full_env.pop("ALR_MATTER", None)
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        input=json.dumps(payload).encode("utf-8") if payload is not None else None,
        capture_output=True, env=full_env, cwd=project, timeout=120,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "research").mkdir()
    return tmp_path
