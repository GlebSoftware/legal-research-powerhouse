# /// script
# requires-python = ">=3.12"
# dependencies = ["eyecite==2.7.8"]
# ///
"""PreToolUse citation gate for Write and Edit (architecture section 3.1).

Scope, relative to a matter under research/:
  drafts/**                    every full case or statute citation must resolve to a ledger entry that is
                               verified (and, for cases, retrieved); bare "X v. Y" names need a full citation
  notes/**, plan.md, question.md   allowed without checks
  authorities.json, sources/**     denied: only the ledger script and retrieval tools write these
  audit/secondary-reports/**    allowed: the user's Westlaw report-backs, recorded verbatim (ADR-10)
  any other file in the matter  full citations checked, bare names allowed
Secondary sources (Restatements, Am. Jur., C.J.S., A.L.R., law reviews) pass only when a ledger entry with
type "secondary" and status "reported" matches them.
Files outside research/ pass untouched.

Denials print the PreToolUse JSON with permissionDecision "deny"; Claude reads the reason and retries.
Inside drafts/ an internal error also denies, so a crash never lets an unchecked citation through.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import (  # noqa: E402
    LEDGER_NAME,
    case_key,
    cfr_key,
    fr_key,
    find_matter_for_path,
    index_ledger,
    load_ledger,
    name_tokens,
    ocga_key,
    project_dir,
    usc_key,
    volume_key,
)

FREE_FILES = {"plan.md", "question.md"}
FREE_DIRS = {"notes"}
FREE_PREFIXES = {("audit", "secondary-reports")}
LOCKED_DIRS = {"sources"}

OCGA_RE = re.compile(r"\bO\.\s?C\.\s?G\.\s?A\.\s*(?:§§?|[Ss]ec(?:tion|\.)?)\s*(\d+-\d+-\d+(?:\.\d+)?(?:\([a-zA-Z0-9]+\))*)")
SIGNALS = {"see", "also", "cf", "but", "compare", "accord", "contra", "eg", "in", "the", "under", "and", "with",
           "following", "citing", "quoting", "accordingly", "thus", "here", "as", "like", "unlike", "while"}
NAME_WORD = r"(?:[A-Z][\w.&'’\-]*|of|the|and|&|de|la|ex rel\.|for)"
SEC_PATTERNS = [
    re.compile(r"Restatement\s+\((?:First|Second|Third|Fourth)\)\s+of\s+[A-Z][A-Za-z,&' ]*?\s*§+\s*[\d.]*\d"),
    re.compile(r"\b\d+[A-Z]?\s+Am\.\s?Jur\.\s?(?:2d|3d)?\s+[A-Z][A-Za-z,&' ]*?\s*§+\s*\d+"),
    re.compile(r"\b\d+[A-Z]?\s+C\.\s?J\.\s?S\.\s+[A-Z][A-Za-z,&' ]*?\s*§+\s*\d+"),
]
TOKEN_RE = re.compile(r"\[\[src:([A-Za-z0-9][\w.\-]*)(?:\s+([^\]]+?))?\]\]")  # same as cite_extract.py
BARE_RE = re.compile(rf"\b([A-Z][\w.&'’\-]*(?:\s+{NAME_WORD}){{0,8}})\s+v\.\s+([A-Z][\w.&'’\-]*(?:,?\s+{NAME_WORD}){{0,8}})")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def clean(text: str) -> str:
    """Drop Markdown emphasis so *Becks v. Pierce* reads as a plain name."""
    return re.sub(r"[*_]", "", text)


def resolve_text(payload: dict, path: Path) -> tuple[str, str]:
    """(new text to check, full resulting document for antecedent lookups)."""
    ti = payload.get("tool_input") or {}
    if payload.get("tool_name") == "Write":
        content = ti.get("content") or ""
        return content, content
    edits = ti.get("edits") or [{"old_string": ti.get("old_string", ""), "new_string": ti.get("new_string", ""),
                                 "replace_all": ti.get("replace_all", False)}]
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    new_parts = []
    for ed in edits:
        old, new = ed.get("old_string", ""), ed.get("new_string", "")
        new_parts.append(new)
        if old:
            current = current.replace(old, new) if ed.get("replace_all") else current.replace(old, new, 1)
    return "\n".join(new_parts), current


def classify_path(path: Path, project: Path) -> tuple[str, Path | None]:
    """('outside'|'free'|'locked'|'drafts'|'matter', matter)."""
    try:
        rel = path.resolve().relative_to(project.resolve())
    except ValueError:
        return "outside", None
    if not rel.parts or rel.parts[0] != "research":
        return "outside", None
    matter = find_matter_for_path(path.parent)
    if matter is None and "drafts" in rel.parts:
        matter = project.joinpath(*rel.parts[: rel.parts.index("drafts")])
    if matter is None:
        return "outside", None
    inner = path.resolve().relative_to(matter.resolve()).parts
    if inner == (LEDGER_NAME,) or (inner and inner[0] in LOCKED_DIRS):
        return "locked", matter
    if (len(inner) == 1 and inner[0] in FREE_FILES) or (inner and inner[0] in FREE_DIRS)             or tuple(inner[:2]) in FREE_PREFIXES:
        return "free", matter
    if inner and inner[0] == "drafts":
        return "drafts", matter
    return "matter", matter


def citable(entry: dict) -> str | None:
    """None when the entry may be cited; otherwise the reason it may not."""
    if entry.get("type") == "case" and entry.get("status") != "retrieved":
        return f"{entry['id']} has not been read: run read_document on it before citing"
    if entry["verification"].get("existence") != "verified":
        return f"ledger entry {entry['id']} is not verified (existence={entry['verification'].get('existence')})"
    return None


def secondary_problem(shown: str, ledger: dict) -> str | None:
    """None when a reported secondary entry matches the citation; otherwise the reason."""
    from secondary import norm

    key = norm(shown)
    matches = [e for e in ledger["authorities"] if e.get("type") == "secondary"
               and key and key in norm(" ".join(filter(None, [(e.get("citation") or {}).get("bluebook"),
                                                              (e.get("source") or {}).get("westlaw_citation")])))]
    if any(e.get("status") == "reported" for e in matches):
        return None
    if matches:
        return (f"{shown}: {matches[0]['request_id']} is {matches[0]['status']}; it passes once "
                f"/secondary ingest records the user's report.")
    return (f"{shown}: no reported secondary-source entry. Secondary sources enter only through "
            f"/secondary request and /secondary ingest (the Westlaw relay).")


def names_match(text_name: str, entry: dict) -> bool:
    wanted = name_tokens(text_name) - SIGNALS
    have = name_tokens(" ".join(filter(None, [entry["citation"].get("case_name"),
                                              entry["citation"].get("case_name_full")])))
    return bool(wanted) and bool(wanted & have)


def check(text: str, document: str, ledger: dict, drafts: bool) -> list[str]:
    from eyecite import get_citations
    from eyecite.models import FullCaseCitation, FullJournalCitation, FullLawCitation, ShortCaseCitation

    idx = index_ledger(ledger)
    problems: list[str] = []
    text, document = clean(text), clean(document)
    cites = get_citations(text)
    full_case_spans: list[tuple[int, int, set[str]]] = []

    for c in cites:
        g, m = c.groups, c.metadata
        shown = c.matched_text()
        if isinstance(c, FullJournalCitation) or (isinstance(c, FullCaseCitation)
                                                   and g.get("reporter", "").startswith("A.L.R.")):
            why = secondary_problem(shown, ledger)
            if why:
                problems.append(why)
            continue
        if isinstance(c, FullCaseCitation):
            hits = idx.get(case_key(g["volume"], g["reporter"], g["page"]), [])
            party = " ".join(filter(None, [m.plaintiff, m.defendant]))
            full_case_spans.append((c.span()[0], c.span()[1], name_tokens(party)))
            if not hits:
                problems.append(f"{shown}: no ledger entry. Retrieve it with /find-case and read it first.")
                continue
            entry = hits[0]
            why = citable(entry)
            if why:
                problems.append(f"{shown}: {why}.")
            elif party and not names_match(party, entry):
                problems.append(f"{shown}: the ledger records this reporter cite as "
                                f"{entry['citation'].get('case_name')}, which does not match '{party}'.")
        elif isinstance(c, ShortCaseCitation):
            hits = idx.get(volume_key(g["volume"], g["reporter"]), [])
            if not hits:
                problems.append(f"{shown}: short cite with no ledger entry for {g['volume']} {g['reporter']}.")
            elif citable(hits[0]):
                problems.append(f"{shown}: {citable(hits[0])}.")
        elif isinstance(c, FullLawCitation):
            rep = (g.get("reporter") or "").lower()
            if rep == "ga. code ann.":
                key = ocga_key(g["section"])
            elif rep == "u.s.c." and g.get("title"):
                key = usc_key(g["title"], g["section"])
            elif rep == "c.f.r." and (g.get("chapter") or g.get("title")):
                key = cfr_key(g.get("chapter") or g.get("title"), g["section"])
            elif rep in ("fed. reg.", "fr") and g.get("volume") and g.get("page"):
                key = fr_key(g["volume"], g["page"])
            else:
                problems.append(f"{shown}: statute or rule citation of a kind the ledger cannot verify yet.")
                continue
            hits = idx.get(key, [])
            if not hits:
                problems.append(f"{shown}: no ledger entry. Retrieve it with /find-statute (uslaw-mcp for federal "
                                f"sources) first.")
            elif citable(hits[0]):
                problems.append(f"{shown}: {citable(hits[0])}.")

    for pattern in SEC_PATTERNS:
        for mo in pattern.finditer(text):
            why = secondary_problem(mo.group(0), ledger)
            if why:
                problems.append(why)

    for mo in OCGA_RE.finditer(text):
        hits = idx.get(ocga_key(mo.group(1)), [])
        if not hits:
            problems.append(f"{mo.group(0)}: no ledger entry. Retrieve the section with /find-statute first.")
        elif citable(hits[0]):
            problems.append(f"{mo.group(0)}: {citable(hits[0])}.")

    for mo in TOKEN_RE.finditer(text):  # [[src:<id> <pin>]] tokens of the memo-draft skill
        entry = next((e for e in ledger["authorities"] if e["id"] == mo.group(1)), None)
        if entry is None:
            problems.append(f"{mo.group(0)}: no ledger entry with id {mo.group(1)}.")
        elif entry.get("type") == "secondary":
            if entry.get("status") != "reported":
                problems.append(f"{mo.group(0)}: {entry.get('request_id')} is {entry.get('status')}; it passes once "
                                f"/secondary ingest records the user's report.")
        elif citable(entry):
            problems.append(f"{mo.group(0)}: {citable(entry)}.")

    if drafts:
        problems += bare_names(text, document, full_case_spans, ledger)
    return list(dict.fromkeys(problems))


CONNECTORS = {"of", "the", "and", "&", "de", "la", "for"}


def trim_party(party: str, leading: bool) -> str:
    """Strip signal words before the first party and connector words after the second."""
    words = party.strip(" ,").split()
    if leading:
        while len(words) > 1 and re.sub(r"[^a-z]", "", words[0].lower()) in SIGNALS | CONNECTORS:
            words.pop(0)
    while len(words) > 1 and words[-1].lower() in CONNECTORS:
        words.pop()
    return " ".join(words).strip(" ,")


def bare_names(text: str, document: str, spans, ledger: dict) -> list[str]:
    """Each "X v. Y" must sit just before its full citation, or have a verified full cite elsewhere in the draft."""
    from eyecite import get_citations
    from eyecite.models import FullCaseCitation

    idx = index_ledger(ledger)
    cited_in_doc: list[dict] = []
    for c in get_citations(document):
        if isinstance(c, FullCaseCitation):
            g = c.groups
            for e in idx.get(case_key(g["volume"], g["reporter"], g["page"]), []):
                if not citable(e):
                    cited_in_doc.append(e)
    by_id = {e["id"]: e for e in ledger["authorities"]}
    for mo in TOKEN_RE.finditer(document):
        e = by_id.get(mo.group(1))
        if e is not None and e.get("type") == "case" and not citable(e):
            cited_in_doc.append(e)
    out = []
    for mo in BARE_RE.finditer(text):
        name = f"{trim_party(mo.group(1), leading=True)} v. {trim_party(mo.group(2), leading=False)}"
        toks = name_tokens(name) - SIGNALS
        attached = any(0 <= start - mo.end() <= 40 and toks & ptoks for start, _end, ptoks in spans)
        if attached or any(names_match(name, e) for e in cited_in_doc):
            continue
        out.append(f"Bare case name '{name}' has no full citation. Resolve it with /find-case and format it "
                   f"with /bluebook before writing it into a draft.")
    return out


def main() -> int:
    logging.disable(logging.CRITICAL)
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0
    project = project_dir(payload)
    path = Path((payload.get("tool_input") or {}).get("file_path", ""))
    if not path.is_absolute():
        path = project / path
    kind, matter = classify_path(path, project)
    if kind in ("outside", "free"):
        return 0
    if kind == "locked":
        deny(f"{path.name}: the ledger and sources/ are written only by ledger.py and the retrieval hooks. "
             f"Use /ledger to change an entry.")
        return 0
    try:
        text, document = resolve_text(payload, path)
        problems = check(text, document, load_ledger(matter), drafts=(kind == "drafts"))
    except Exception as exc:  # fail closed
        deny(f"Citation gate error ({type(exc).__name__}: {exc}). The write is blocked until the gate runs cleanly.")
        return 0
    if problems:
        deny("Citation gate blocked this write to "
             f"{path.relative_to(matter).as_posix()} in matter {matter.name}:\n- " + "\n- ".join(problems))
    return 0


if __name__ == "__main__":
    sys.exit(main())
