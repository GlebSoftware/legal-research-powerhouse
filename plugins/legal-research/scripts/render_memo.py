# /// script
# requires-python = ">=3.12"
# dependencies = ["reporters-db==3.2.67", "courts-db==0.10.27", "python-docx==1.1.2"]
# ///
"""Render a token draft into a finished memo (Phase 3; architecture ADR-7).

  render_memo.py <matter> <draft> [--mode ga|academic] [--no-docx]

The draft cites through tokens, [[src:<ledger-id> <pin>]], and writes the sentence punctuation itself. Each token
becomes, in order of appearance:
  first reference          the full citation (bluebook_case.py for cases, the ledger's cite_as for codes)
  same authority as the    *Id.* (or *Id.* at <pin>); lowercase after a signal ("See id. at 842")
  citation right before
  any later reference      the short form (case short name with "at <pin>"; the code section without the year)
A string citation (tokens joined by "; ") cuts the Id. chain. A token whose entry is missing, unread, or an
unreported secondary source stops the render: the draft goes back through the audit first.

Writes <matter>/final/<draft-stem>.md (tokens resolved, table of authorities after the title) and, unless
--no-docx, <matter>/final/<draft-stem>.docx with Word's own styles (Title, Heading 1 to 3, Normal, Quote,
List Bullet, List Number), Times New Roman 12 point, one-inch margins.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import get_entry, load_ledger  # noqa: E402
from bluebook_case import format_case  # noqa: E402

TOKEN_RE = re.compile(r"\[\[src:([A-Za-z0-9][\w.\-]*)(?:\s+([^\]]+?))?\]\]")
SIGNAL_RE = re.compile(r"(?:^|[\s(])(?:[Ss]ee(?: also| generally)?|[Bb]ut see|[Cc]f\.|[Bb]ut cf\.|[Aa]ccord|[Cc]ontra)\s*\*?$")
YEAR_PAREN_RE = re.compile(r"\s*\((?:[^()]*\s)?\d{4}\)\s*$")


class RenderError(Exception):
    pass


def norm_pin(pin: str | None) -> str | None:
    if not pin:
        return None
    p = pin.strip()
    p = re.sub(r"^(?:at|p\.|pp\.)\s*", "", p)
    return p or None


def _strip_period(s: str) -> str:
    return s[:-1] if s.endswith(".") and not s.endswith(("Id.", "Inc.", "Co.", "Corp.", "Ltd.")) else s


def cites_for(entry: dict, mode: str, pin: str | None) -> tuple[str, str, str]:
    """(full, short, kind) for one ledger entry at one pin."""
    if entry.get("status") != "retrieved" and not (entry.get("type") == "secondary" and entry.get("status") == "reported"):
        raise RenderError(f"{entry['id']} is {entry.get('status')}; only retrieved authorities (or reported secondary sources) render")
    kind = entry.get("type") or "other"
    cit = entry.get("citation") or {}
    if kind == "case":
        out = format_case(entry, mode=mode, pin=pin)
        return _strip_period(out["full"]), _strip_period(out["short"]), kind
    if kind == "secondary":
        full = cit.get("bluebook")
        if not full:
            raise RenderError(f"{entry['id']} has no reported citation")
        full = _strip_period(full)
        return (f"{full}, at {pin}" if pin else full), full, kind
    full = cit.get("cite_as") or entry["id"]
    short = YEAR_PAREN_RE.sub("", full)
    if pin:  # a subsection pin: O.C.G.A. § 51-12-9(a) (2025)
        m = YEAR_PAREN_RE.search(full)
        year = m.group(0) if m else ""
        full = f"{short}{pin if pin.startswith('(') else ' ' + pin}{year}"
        short = f"{short}{pin if pin.startswith('(') else ' ' + pin}"
    return full, short, kind


def resolve(text: str, ledger: dict, mode: str) -> tuple[str, list[dict]]:
    """Resolved text and the authorities in order of first reference."""
    tokens = list(TOKEN_RE.finditer(text))
    joined = [i > 0 and re.fullmatch(r"\s*;\s*", text[tokens[i - 1].end():t.start()]) is not None
              for i, t in enumerate(tokens)]
    in_string = [joined[i] or (i + 1 < len(tokens) and joined[i + 1]) for i in range(len(tokens))]
    seen: dict[str, dict] = {}
    last_id: str | None = None  # the authority of the citation right before, when it stood alone
    out: list[str] = []
    pos = 0
    for i, m in enumerate(tokens):
        eid, pin = m.group(1), norm_pin(m.group(2))
        entry = get_entry(ledger, eid)
        if entry is None:
            raise RenderError(f"token [[src:{eid}]] names no ledger entry")
        full, short, kind = cites_for(entry, mode, pin)
        before = text[pos:m.start()]
        if eid == last_id and not in_string[i]:
            word = "id." if SIGNAL_RE.search(before.rstrip()) else "Id."
            rendered = f"*{word}*" + (f" at {pin}" if pin and kind == "case" else (f" {pin}" if pin else ""))
        elif eid in seen:
            rendered = short
        else:
            rendered = full
            seen[eid] = {"id": eid, "kind": kind, "full": cites_for(entry, mode, None)[0] if pin else full}
        out += [before, rendered]
        pos = m.end()
        if re.sub(r"[*_]+$", "", rendered).endswith(".") and text[pos:pos + 1] == ".":
            pos += 1  # "*Id.*" or "Inc." already ends the sentence the draft closes with its own period
        last_id = None if in_string[i] else eid
    out.append(text[pos:])
    return "".join(out), list(seen.values())


def toa_block(authorities: list[dict]) -> str:
    groups = [("Cases", "case"), ("Constitutions, Statutes, and Regulations", None), ("Secondary Sources", "secondary")]
    lines = ["## Table of Authorities", ""]
    for title, kind in groups:
        rows = [a for a in authorities if (a["kind"] == kind if kind else a["kind"] not in ("case", "secondary"))]
        if not rows:
            continue
        lines += [f"### {title}", ""]
        lines += [f"- {a['full']}" for a in sorted(rows, key=lambda a: re.sub(r"[*_]", "", a["full"]).lower())]
        lines.append("")
    return "\n".join(lines)


def insert_toa(md: str, toa: str) -> str:
    """After the title (the first # heading) and the memo heading block (To:, From:, Date:, Re:) that follows it."""
    lines = md.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and re.match(r"^[A-Z][A-Za-z ]{0,20}:\s", lines[j]):
                while j < len(lines) and lines[j].strip():
                    j += 1
            else:
                j = i + 1
            return "\n".join(lines[:j] + ["", toa.rstrip(), ""] + lines[j:])
    return toa + "\n" + md


# ---------------------------------------------------------------- .docx


INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_)")


def add_runs(par, text: str) -> None:
    for piece in INLINE_RE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**"):
            par.add_run(piece[2:-2]).bold = True
        elif (piece.startswith("*") and piece.endswith("*")) or (piece.startswith("_") and piece.endswith("_")):
            par.add_run(piece[1:-1]).italic = True
        else:
            par.add_run(piece)


def to_docx(md: str, path: Path) -> None:
    from docx import Document
    from docx.shared import Inches, Pt

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Inches(1)
    for name in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3", "Quote", "List Bullet", "List Number"):
        st = doc.styles[name]
        st.font.name = "Times New Roman"
        if name in ("Normal", "Quote", "List Bullet", "List Number"):
            st.font.size = Pt(12)
    para: list[str] = []

    def flush():
        if para:
            add_runs(doc.add_paragraph(style="Normal"), " ".join(s.strip() for s in para))
            para.clear()

    for line in md.split("\n"):
        s = line.rstrip()
        if not s.strip():
            flush()
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            flush()
            level = len(m.group(1))
            if level == 1:
                add_runs(doc.add_paragraph(style="Title"), m.group(2))
            else:
                add_runs(doc.add_heading(level=level - 1), m.group(2))
            continue
        if s.startswith(">"):
            flush()
            add_runs(doc.add_paragraph(style="Quote"), s.lstrip("> ").strip())
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", s)
        if m:
            flush()
            add_runs(doc.add_paragraph(style="List Bullet"), m.group(1))
            continue
        m = re.match(r"^\s*\d+\.\s+(.*)$", s)
        if m:
            flush()
            add_runs(doc.add_paragraph(style="List Number"), m.group(1))
            continue
        para.append(s)
    flush()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("matter")
    ap.add_argument("draft")
    ap.add_argument("--mode", choices=["ga", "academic"], default="ga")
    ap.add_argument("--no-docx", action="store_true")
    a = ap.parse_args(argv)
    matter = Path(a.matter)
    draft = Path(a.draft)
    if not draft.is_absolute() and not draft.is_file():
        draft = matter / a.draft
    try:
        resolved, authorities = resolve(draft.read_text(encoding="utf-8"), load_ledger(matter), a.mode)
    except RenderError as exc:
        print(f"render_memo: {exc}", file=sys.stderr)
        return 1
    md = insert_toa(resolved, toa_block(authorities))
    out = matter / "final" / f"{draft.stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8", newline="\n")
    print(f"{out.as_posix()}: {len(authorities)} authorities")
    if not a.no_docx:
        docx_path = out.with_suffix(".docx")
        to_docx(md, docx_path)
        print(docx_path.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
