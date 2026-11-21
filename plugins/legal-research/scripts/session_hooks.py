# /// script
# requires-python = ">=3.12"
# ///
"""Session lifecycle hooks.

  start    SessionStart: inject the active matter's ledger summary, the research protocol reminder, and the
           CourtListener quota read from /api/rest/v4/api-usage/ (that endpoint spends no API quota).
  changed  PostToolUse Edit|Write: append the edited path to .session/changed-files.
  stop     Stop: runs cite_audit.py on drafts this session wrote and blocks while unwaived red items remain;
           honors stop_hook_active so a continuation never loops.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import active_matter, load_ledger, now_iso, project_dir  # noqa: E402

USAGE_URL = "https://www.courtlistener.com/api/rest/v4/api-usage/"
LOW_WATER = 30


def read_env_file(project: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    path = project / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def quota_line(project: Path) -> str:
    token = os.environ.get("COURTLISTENER_API_TOKEN") or read_env_file(project).get("COURTLISTENER_API_TOKEN")
    if not token:
        return "CourtListener quota: unknown (COURTLISTENER_API_TOKEN missing from .env)."
    req = urllib.request.Request(USAGE_URL, headers={"Authorization": f"Token {token}", "User-Agent": "alr-session/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return f"CourtListener quota: usage endpoint returned HTTP {e.code}; check COURTLISTENER_API_TOKEN."
    except Exception as e:  # network down, timeout
        return f"CourtListener quota: unreachable ({type(e).__name__}: {getattr(e, 'reason', e)})."
    usage = data.get("current_usage") or []
    if isinstance(usage, dict):  # MCP get_api_usage shape: {"user": {"limits": [...]}}
        limits = (usage.get("user") or {}).get("limits") or []
    else:  # REST shape: flat list of limits tagged by scope
        limits = [lim for lim in usage if isinstance(lim, dict) and lim.get("scope") == "user"]
    parts, low = [], False
    for lim in limits:
        parts.append(f"{lim.get('remaining')}/{lim.get('limit')} per {lim.get('rate', '').split('/')[-1]}")
        if isinstance(lim.get("remaining"), int) and lim["remaining"] < LOW_WATER and lim.get("window_seconds", 0) >= 3600:
            low = True
    member = data.get("membership") or {}
    line = f"CourtListener quota: {', '.join(parts) or 'no limits reported'}; membership {member.get('level')} active={member.get('is_active')}."
    if low:
        line += f" WARNING: fewer than {LOW_WATER} requests remain in the window. Plan reads before searching."
    return line


def ledger_summary(project: Path) -> str:
    matter = active_matter(project)
    if matter is None or not (matter / "authorities.json").is_file():
        return "Active matter: none. Start one with /research; retrievals made now go to .session/inbox/."
    ledger = load_ledger(matter)
    rows = ledger["authorities"]
    retrieved = [e for e in rows if e["status"] == "retrieved"]
    keycite = [e for e in retrieved if ((e.get("treatment") or {}).get("manual_keycite") or {}).get("required")
               and not e["treatment"]["manual_keycite"].get("done")]
    try:
        rel = matter.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        rel = str(matter)
    return (f"Active matter: {rel} (closed_universe={ledger.get('closed_universe')}). Ledger: {len(rows)} entries, "
            f"{len(retrieved)} retrieved, {len(rows) - len(retrieved)} candidates, {len(keycite)} awaiting manual KeyCite.")


PROTOCOL = ("Legal research protocol is active: cite only authorities retrieved this session or in the ledger; read an "
            "opinion with read_document before stating its holding; label every case Verified (heavyweight), Screened "
            "(lightweight), or Not validated; request `fields` on every CourtListener call. The citation gate blocks "
            "draft writes whose citations are absent from the ledger. If CourtListener is disconnected, say "
            "\"CourtListener is disconnected, reconnect it before I proceed\" and stop.")


def cmd_start(payload: dict) -> int:
    project = project_dir(payload)
    if not (project / "research").is_dir():  # not a research workspace; the plugin is installed user-wide
        return 0
    context = "\n".join([PROTOCOL, ledger_summary(project), quota_line(project)])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
    return 0


def cmd_changed(payload: dict) -> int:
    project = project_dir(payload)
    fp = (payload.get("tool_input") or {}).get("file_path")
    if not fp:
        return 0
    path = Path(fp)
    try:
        rel = path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        rel = str(path)
    log = project / ".session" / "changed-files"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{now_iso()}\t{payload.get('tool_name')}\t{rel}\t{payload.get('session_id', '')}\n")
    return 0


def changed_drafts(project: Path, session_id: str) -> dict[Path, list[Path]]:
    """Draft files this session wrote, grouped by matter."""
    from alr_common import find_matter_for_path

    log = project / ".session" / "changed-files"
    out: dict[Path, list[Path]] = {}
    if not log.is_file():
        return out
    for line in log.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 4 or (session_id and parts[3] != session_id):
            continue
        path = (project / parts[2]).resolve()
        if "drafts" not in path.parts or not path.is_file() or path.suffix.lower() != ".md":
            continue
        matter = find_matter_for_path(path.parent)
        if matter is not None and path not in out.setdefault(matter, []):
            out[matter].append(path)
    return out


def uv_binary() -> str:
    import shutil

    return shutil.which("uv") or str(Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv"))


def cmd_stop(payload: dict) -> int:
    """Block stopping while a draft written this session carries unwaived red audit items (architecture 3.1)."""
    import subprocess

    if payload.get("stop_hook_active"):
        return 0
    project = project_dir(payload)
    if not (project / "research").is_dir():
        return 0
    script = Path(__file__).resolve().parent / "cite_audit.py"
    reasons = []
    for matter, drafts in changed_drafts(project, payload.get("session_id", "")).items():
        subprocess.run([uv_binary(), "run", "--quiet", "--script", str(script), str(matter), *map(str, drafts),
                        "--html", "--quiet"], capture_output=True, timeout=240)
        report_path = matter / "audit" / "cite-check.json"
        if not report_path.is_file():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for d in report.get("drafts", []):
            for it in d.get("items", []):
                if it["severity"] == "red" and not it.get("waived"):
                    reasons.append(f"{matter.name}/{d['path']}: {it['text'][:70]!r}: {it['detail']} (key: {it['key']})")
    if reasons:
        shown = "\n- ".join(reasons[:8])
        more = f"\n(and {len(reasons) - 8} more)" if len(reasons) > 8 else ""
        print(json.dumps({"decision": "block", "reason": (
            "The citation audit found unresolved red items in drafts written this session:\n- " + shown + more +
            "\nFix each (retrieve and read the authority, format with /bluebook, correct the quotation), or ask the user "
            "whether to record a waiver with: ledger.py waive <matter> \"<key>\" --reason \"...\". "
            "Details: audit/cite-check.html.")}))
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    raw = sys.stdin.buffer.read().decode("utf-8", "replace") if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    fn = {"start": cmd_start, "changed": cmd_changed, "stop": cmd_stop}.get(cmd)
    if fn is None:
        print(__doc__, file=sys.stderr)
        return 1
    try:
        return fn(payload)
    except Exception as exc:
        if cmd == "start":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                     "additionalContext": PROTOCOL + f"\n(session hook error: {exc})"}}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
