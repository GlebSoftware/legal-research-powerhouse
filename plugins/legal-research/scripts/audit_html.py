"""Static review page for a citation audit: audit/cite-check.html (architecture section 6, step 7; ADR-6).

Each draft is shown with its citations highlighted by status; beside it, the items list and the table of
authorities. Self-contained HTML (no scripts, no external resources), opened in the browser by /cite-check.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

CSS = """
:root { --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a64; --line:#e3e0d8; --red:#b42318; --red-bg:#fde8e6;
        --yellow:#8a5a00; --yellow-bg:#fdf3d7; --green:#1f6f43; --green-bg:#e3f4ea; }
@media (prefers-color-scheme: dark) { :root { --bg:#161614; --fg:#ecebe6; --muted:#a3a29b; --line:#33322e;
        --red:#ff8a80; --red-bg:#3a1714; --yellow:#f3c565; --yellow-bg:#352a10; --green:#7ad6a0; --green-bg:#11291c; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 Georgia, 'Times New Roman', serif; }
header { padding:20px 24px; border-bottom:1px solid var(--line); }
h1 { font-size:20px; margin:0 0 4px; } .muted { color:var(--muted); font-size:13px; }
.counts span { display:inline-block; margin-right:14px; font:600 13px system-ui, sans-serif; }
main { display:grid; grid-template-columns:minmax(0,3fr) minmax(280px,2fr); gap:24px; padding:20px 24px; }
@media (max-width: 900px) { main { grid-template-columns:1fr; } }
.draft { white-space:pre-wrap; border:1px solid var(--line); padding:16px; border-radius:6px; }
mark { padding:0 2px; border-radius:3px; background:var(--green-bg); color:inherit; border-bottom:2px solid var(--green); }
mark.red { background:var(--red-bg); border-bottom-color:var(--red); }
mark.yellow { background:var(--yellow-bg); border-bottom-color:var(--yellow); }
section h2 { font:600 15px system-ui, sans-serif; margin:20px 0 8px; }
ul.items { list-style:none; padding:0; margin:0; font:13px/1.45 system-ui, sans-serif; }
ul.items li { border-left:3px solid var(--line); padding:6px 10px; margin-bottom:6px; }
ul.items li.red { border-color:var(--red); } ul.items li.yellow { border-color:var(--yellow); }
ul.items li.waived { opacity:.55; } code { font-size:12px; }
.toa { font-size:14px; } .toa li { margin-bottom:4px; }
"""


def highlight(text: str, citations: list[dict], items: list[dict]) -> str:
    red_starts = {i["start"] for i in items if i["severity"] == "red" and not i.get("waived")}
    yellow_starts = {i["start"] for i in items if i["severity"] == "yellow" and not i.get("waived") and i["start"]}
    spans = sorted({(c["start"], c["end"]) for c in citations})
    out, pos = [], 0
    for s, e in spans:
        if s < pos:
            continue
        cls = "red" if s in red_starts else "yellow" if s in yellow_starts else ""
        out.append(html.escape(text[pos:s]))
        out.append(f'<mark class="{cls}">{html.escape(text[s:e])}</mark>')
        pos = e
    out.append(html.escape(text[pos:]))
    return "".join(out)


def markdown_list(md: str) -> str:
    rows = []
    for line in md.splitlines():
        if line.startswith("## "):
            rows.append(f"<h3>{html.escape(line[3:])}</h3>")
        elif line.startswith("- "):
            body = html.escape(line[2:])
            parts = body.split("*")
            body = "".join(f"<i>{p}</i>" if i % 2 else p for i, p in enumerate(parts))
            rows.append(f"<li>{body}</li>")
    return "<ul class='toa'>" + "".join(rows) + "</ul>"


def render(matter: Path, report: dict) -> Path:
    toa_md = (matter / "audit" / "toa.md").read_text(encoding="utf-8") if (matter / "audit" / "toa.md").is_file() else ""
    blocks = []
    for d in report["drafts"]:
        text = (matter / d["path"]).read_text(encoding="utf-8") if (matter / d["path"]).is_file() else ""
        lis = "".join(
            f"<li class='{i['severity']}{' waived' if i.get('waived') else ''}'><b>{i['severity'].upper()}</b> "
            f"{html.escape(i['kind'])}: <code>{html.escape(i['text'][:120])}</code><br>{html.escape(i['detail'])}"
            f"{' (waived)' if i.get('waived') else ''}</li>" for i in d["items"]) or "<li>No items.</li>"
        blocks.append(f"<section><h2>{html.escape(d['path'])}</h2><div class='draft'>{highlight(text, d['citations'], d['items'])}</div>"
                      f"<h2>Items</h2><ul class='items'>{lis}</ul></section>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cite check · {html.escape(report['matter'])}</title><style>{CSS}</style></head><body>
<header><h1>Cite check: {html.escape(report['matter'])}</h1>
<div class="muted">Generated {html.escape(report['generated_at'])} by cite_audit.py. Green: verified against the ledger. Yellow: fix before graded use. Red: blocks the session's Stop hook.</div>
<div class="counts"><span style="color:var(--red)">{report['red']} red</span><span style="color:var(--yellow)">{report['yellow']} yellow</span><span>{report['waived']} waived</span></div></header>
<main><div>{''.join(blocks) or '<p>No drafts.</p>'}</div><aside><section><h2>Table of authorities</h2>{markdown_list(toa_md)}</section></aside></main>
</body></html>"""
    out = matter / "audit" / "cite-check.html"
    out.write_text(page, encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    m = Path(sys.argv[1])
    print(render(m, json.loads((m / "audit" / "cite-check.json").read_text(encoding="utf-8"))))
