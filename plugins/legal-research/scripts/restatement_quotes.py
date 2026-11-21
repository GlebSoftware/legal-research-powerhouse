# /// script
# requires-python = ">=3.12"
# ///
"""Restatement text as Georgia courts quoted it, from the matter's saved opinions (Phase 3, free Restatement path).

  restatement_quotes.py <matter> <section> [--subject Torts] [--series Second] [--json]

Finds every citation of the Restatement section in the saved text of the matter's retrieved cases, in the forms
courts write it ("Restatement (Second) of Torts § 448 (1965)", "Restatement, Torts, 2d, § 319", "Restatement 2d of
Torts § 448"), and pairs it with the quotation that sits against it: a quotation ending just before the citation, or
one opening just after it (the parenthetical form). Each quotation is anchored in the opinion with its star page.

Writes notes/restatement-<series>-<subject>-<section>.md. The quoted text supports a sentence like "The Court of
Appeals, quoting Restatement (Second) of Torts § 448, stated ...", cited to the opinion; the Restatement itself
enters the ledger only through the Westlaw relay (/secondary). Spends zero CourtListener quota: run the full-text
search for the section in the session first and read the opinions it returns.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import load_ledger  # noqa: E402
from verify_anchors import anchor, entry_text  # noqa: E402

SERIES = {"Second": ("second", "2d"), "Third": ("third", "3d"), "First": ("first",)}
NEAR = 40  # characters between a quotation and its citation
QUOTE_OPEN, QUOTE_CLOSE = "“\"", "”\""


def plain(raw: str) -> str:
    """Opinion text without markup; star-page markers drop out (anchor() reports the page from the raw text)."""
    t = re.sub(r'<span\b[^>]*class="star-pagination"[^>]*>.*?</span>|<page-number\b[^>]*>.*?</page-number>', " ", raw, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def mentions(text: str, section: str, subject: str, series: str):
    """Spans of citations of the section: Restatement ... <series> ... <subject> ... § <section> [(year)] [, cmt. x]."""
    alts = SERIES.get(series, (series.lower(),))
    pat = re.compile(rf"Restatement([^§]{{0,60}}?)§+\s*{re.escape(section)}(?![\dA-Za-z])"
                     rf"(?:,?\s*(?:cmt\.|comment\.?)\s*[a-z]\b)?(?:\s*\(\d{{4}}\))?")
    for m in pat.finditer(text):
        mid = m.group(1).lower()
        if subject.lower() in mid and any(a in mid for a in alts):
            yield m.start(), m.end()


MIN_WORDS = 6  # shorter quoted strings are defined terms ("Section 324A"), as in cite_extract.py


def quote_near(text: str, start: int, end: int) -> str | None:
    """The quotation against a citation: a parenthetical opening just after it, else one closing just before it
    with nothing between but the citation's own punctuation (no "; " or ")" from another authority)."""
    after = text[end:end + NEAR]
    opens = [after.find(c) for c in QUOTE_OPEN if after.find(c) != -1]
    if opens:
        o = end + min(opens)
        ends = [text.find(c, o + 1) for c in QUOTE_CLOSE if text.find(c, o + 1) != -1]
        if ends and len(text[o + 1:min(ends)].split()) >= MIN_WORDS:
            return text[o + 1:min(ends)].strip()
    window = text[max(0, start - NEAR):start]
    close = max(window.rfind(c) for c in QUOTE_CLOSE)
    if close != -1 and not re.search(r"[;)]", window[close + 1:]):
        close_abs = max(0, start - NEAR) + close
        open_abs = max(text.rfind(c, 0, close_abs) for c in QUOTE_OPEN)
        if open_abs != -1 and len(text[open_abs + 1:close_abs].split()) >= MIN_WORDS:
            return text[open_abs + 1:close_abs].strip()
    return None


def collect(matter: Path, ledger: dict, section: str, subject: str, series: str) -> list[dict]:
    rows = []
    for e in ledger["authorities"]:
        if e.get("type") != "case" or e.get("status") != "retrieved":
            continue
        raw = entry_text(matter, e)
        if not raw:
            continue
        text = plain(raw)
        for s, t in mentions(text, section, subject, series):
            q = quote_near(text, s, t)
            row = {"id": e["id"], "case": (e.get("citation") or {}).get("case_name"), "citation": text[s:t].strip(),
                   "quote": q, "page": None, "anchored": None}
            if q:
                res = anchor(raw, q.rstrip(" .,;:"))
                row["anchored"] = res["status"] == "anchored"
                row["page"] = res.get("page")
            rows.append(row)
    return rows


def render(rows: list[dict], section: str, subject: str, series: str) -> str:
    title = f"Restatement ({series}) of {subject} § {section}: quotations in the matter's saved opinions"
    lines = [f"# {title}", ""]
    if not rows:
        return "\n".join(lines + ["No saved opinion cites this section. Run the full-text search first, read the hits,",
                                  "then run this script again.", ""])
    for r in rows:
        where = f"star page {r['page']}" if r["page"] else "no star page"
        lines.append(f"- `{r['id']}` {r['case']}: {r['citation']}")
        if r["quote"]:
            lines.append(f"  - quoted ({'anchored' if r['anchored'] else 'NOT anchored'}, {where}): \"{r['quote']}\"")
        else:
            lines.append("  - cited without a quotation")
    return "\n".join(lines + [""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("matter")
    ap.add_argument("section")
    ap.add_argument("--subject", default="Torts")
    ap.add_argument("--series", default="Second", choices=sorted(SERIES))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    matter = Path(a.matter)
    rows = collect(matter, load_ledger(matter), a.section, a.subject, a.series)
    out = matter / "notes" / f"restatement-{a.series.lower()}-{a.subject.lower()}-{a.section}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rows, a.section, a.subject, a.series), encoding="utf-8", newline="\n")
    print(json.dumps(rows, indent=1, ensure_ascii=False) if a.json else f"{out.as_posix()}: {len(rows)} citation(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
