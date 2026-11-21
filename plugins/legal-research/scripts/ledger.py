# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6"]
# ///
"""Authority Ledger for a research matter (architecture ADR-4).

Subcommands:
  create <matter> [--closed-universe]   make the matter layout and ledger, set it active
  use <matter>                          set the active matter (.session/active-matter)
  show [<matter>] [--json]              summary table of the ledger
  upsert <matter> <entry.json|->        merge one entry
  keycite-list [<matter>]               authorities still needing a manual KeyCite or Shepard's check
  mark <matter> <id> key=value ...      record manual results: keycite=<result>, note=<text>
  ingest                                PostToolUse hook: read the hook JSON on stdin, upsert entries,
                                        save retrieved text to sources/. Spends zero API quota.
  secondary request <matter> <spec.json|->      Westlaw relay (ADR-10): validate and render an SR block
  secondary ingest <matter> <SR-id> <report>    record what the user brought back (.md or .json)
  secondary list [<matter>] | withdraw <matter> <SR-id>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alr_common import (  # noqa: E402
    active_matter,
    ensure_matter,
    get_entry,
    inbox,
    ledger_lock,
    load_ledger,
    now_iso,
    parse_reporter_cite,
    project_dir,
    save_ledger,
    sha256_text,
    upsert,
)

# CourtListener tool short names (the part after the last "__"). The connector prefix varies by
# surface: mcp__<uuid>__search in the desktop app, mcp__claude_ai_CourtListener__search in the CLI.
CL_TOOLS = {"search", "get_more_results", "read_document", "get_endpoint_item", "call_endpoint",
            "analyze_citations", "resume_citation_analysis", "search_document"}
GC_TOOLS = {"code_lookup_section", "code_lookup_sections", "code_get_chapter", "constitution_lookup",
            "opinions_lookup", "opinions_get_text", "verify_quote", "fetch", "search", "code_search",
            "opinions_search"}
GC_TYPES = {"code": "statute", "constitution": "constitution", "opinions": "case"}
USLAW_DOC_TOOLS = {"ecfr_section", "fr_document", "govinfo_package", "uscode_section", "jm_section"}
USLAW_TOOLS = USLAW_DOC_TOOLS | {"ecfr_versions", "ecfr_search", "fr_search", "govinfo_search", "congress_bill",
                                 "congress_law", "crs_report", "regs_search", "regs_docket", "uscode_search",
                                 "conan_unconstitutional_laws", "conan_overruled_decisions"}


# ---------------------------------------------------------------- tool result decoding


def response_text(tool_response) -> str:
    """MCP results arrive as [{"type": "text", "text": "..."}]; join the text blocks."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        if "content" in tool_response:
            return response_text(tool_response["content"])
        return json.dumps(tool_response)
    if isinstance(tool_response, list):
        return "\n".join(b.get("text", "") for b in tool_response if isinstance(b, dict) and b.get("type") == "text")
    return ""


def try_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


# Only files the harness wrote: <home>/.claude/projects/<project>/<session>/tool-results/<name>.txt
SPILL_RE = re.compile(r"([A-Za-z]:[\\/][^\n\"<>|]*?[\\/]\.claude[\\/]projects[\\/][^\n\"<>|]*?tool-results[\\/][^\s\"<>|\\/]+\.(?:txt|json))")


def unspill(text: str) -> str:
    """A result over the tool-output limit reaches the hook as a pointer to the file the harness saved it in."""
    if text.lstrip().startswith(("{", "[", "---")):
        return text
    m = SPILL_RE.search(text)
    if m:
        p = Path(m.group(1))
        if p.is_file() and p.stat().st_size < 50_000_000:
            saved = p.read_text(encoding="utf-8", errors="replace")
            # A .json spill holds the MCP content blocks ([{"type": "text", "text": ...}]); return their text.
            blocks = try_json(saved)
            if isinstance(blocks, list) and blocks and all(isinstance(b, dict) and b.get("type") == "text" for b in blocks):
                return "".join(str(b.get("text") or "") for b in blocks)
            return saved
    return text


def short_name(tool_name: str) -> str:
    return tool_name.rsplit("__", 1)[-1]


def server_hint(payload: dict) -> str:
    server = (payload.get("mcp_server") or {}).get("name") or ""
    parts = payload.get("tool_name", "").split("__")
    if len(parts) >= 3:
        server += " " + parts[1]
    return server.lower()


# ---------------------------------------------------------------- source files


def ext_for(text: str) -> str:
    head = text.lstrip()[:100].lower()
    if head.startswith("<?xml"):
        return ".xml"
    if head.startswith("<"):
        return ".html"
    if head.startswith("---"):
        return ".md"
    return ".txt"


def save_source(matter: Path, name: str, text: str, meta: dict) -> tuple[str, str]:
    sources = matter / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    rel = f"sources/{name}{ext_for(text)}"
    (matter / rel).write_text(text, encoding="utf-8", newline="\n")
    digest = sha256_text(text)
    line = {"path": rel, "sha256": digest, "bytes": len(text.encode("utf-8")), "retrieved_at": now_iso(), **meta}
    with (sources / "manifest.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    return rel, digest


# ---------------------------------------------------------------- CourtListener


def cl_new_entry(cluster_id: int | None, opinion_id: int | None, tool: str) -> dict:
    ident = f"cl-cluster-{cluster_id}" if cluster_id else f"cl-opinion-{opinion_id}"
    return {
        "id": ident,
        "type": "case",
        "status": "candidate",
        "source": {"system": "courtlistener", "cluster_id": cluster_id, "opinion_id": opinion_id,
                   "opinion_ids": [], "url": None, "tool": tool},
        "first_seen_at": now_iso(),
        "retrieved_at": None,
        "sha256": None,
        "local_path": None,
        "pagination": None,
        "citation": {"reporters": [], "other_cites": []},
        "verification": {"existence": "listed", "name_match": None, "method": tool, "checked_at": now_iso()},
        "treatment": {"level": "none", "verdict": None, "confidence": None,
                      "manual_keycite": {"required": True, "done": False, "result": None, "date": None}},
        "propositions": [],
        "quote_checks": [],
    }


def cl_find(ledger: dict, cluster_id: int | None, opinion_id: int | None) -> dict | None:
    if cluster_id:
        e = get_entry(ledger, f"cl-cluster-{cluster_id}")
        if e:
            return e
    if opinion_id:
        for e in ledger["authorities"]:
            src = e.get("source", {})
            if src.get("system") == "courtlistener" and (
                    opinion_id in (src.get("opinion_ids") or []) or src.get("opinion_id") == opinion_id):
                return e
    return None


def cl_get_or_create(ledger: dict, cluster_id: int | None, opinion_id: int | None, tool: str) -> dict:
    e = cl_find(ledger, cluster_id, opinion_id)
    if e is None:
        e = cl_new_entry(cluster_id, opinion_id, tool)
        ledger["authorities"].append(e)
    elif cluster_id and e["id"].startswith("cl-opinion-"):
        e["id"] = f"cl-cluster-{cluster_id}"
        e["source"]["cluster_id"] = cluster_id
    return e


def add_cites(entry: dict, cites: list) -> None:
    cit = entry["citation"]
    have = {(r["volume"], r["reporter"], r["page"]) for r in cit.get("reporters", [])}
    for c in cites:
        if isinstance(c, dict) and c.get("reporter"):
            parsed = {"volume": str(c.get("volume")), "reporter": c["reporter"], "page": str(c.get("page")),
                      "type": c.get("type")}
            text = f"{parsed['volume']} {parsed['reporter']} {parsed['page']}"
        elif isinstance(c, str):
            parsed, text = parse_reporter_cite(c), c
            if parsed is not None:
                parsed["type"] = None
        else:
            continue
        if parsed is None or "LEXIS" in parsed["reporter"] or parsed["reporter"] == "WL":
            if text not in cit.setdefault("other_cites", []):
                cit["other_cites"].append(text)
            continue
        key = (parsed["volume"], parsed["reporter"], parsed["page"])
        if key in have:
            for r in cit["reporters"]:
                if (r["volume"], r["reporter"], r["page"]) == key and parsed.get("type") is not None:
                    r["type"] = parsed["type"]
        else:
            cit.setdefault("reporters", []).append(parsed)
            have.add(key)


def add_opinion_ids(entry: dict, ids) -> None:
    lst = entry["source"].setdefault("opinion_ids", [])
    for i in ids:
        if isinstance(i, int) and i not in lst:
            lst.append(i)
    if entry["source"].get("opinion_id") is None and lst:
        entry["source"]["opinion_id"] = lst[0]


def cl_ingest_search_hit(ledger: dict, hit: dict, tool: str) -> str | None:
    cid = hit.get("cluster_id")
    if not isinstance(cid, int):
        return None
    e = cl_get_or_create(ledger, cid, hit.get("opinion_id"), tool)
    cit = e["citation"]
    name = hit.get("caseName") or hit.get("case_name")
    if name:
        cit["case_name"] = name
    if hit.get("caseNameFull"):
        cit["case_name_full"] = hit["caseNameFull"]
    for src_key, dst_key in (("court_id", "court_id"), ("dateFiled", "date_filed"), ("docketNumber", "docket_number"),
                             ("court_citation_string", "court_string")):
        if hit.get(src_key):
            cit[dst_key] = hit[src_key]
    add_cites(e, hit.get("citation") or [])
    ops = [o.get("id") for o in hit.get("cluster_opinions") or [] if isinstance(o, dict)]
    ops += [o.get("id") for o in hit.get("opinions") or [] if isinstance(o, dict)]
    if isinstance(hit.get("opinion_id"), int):
        ops.insert(0, hit["opinion_id"])
    add_opinion_ids(e, ops)
    if hit.get("absolute_url"):
        e["source"]["url"] = "https://www.courtlistener.com" + hit["absolute_url"]
    return e["id"]


def cl_ingest_cluster_record(ledger: dict, rec: dict, tool: str) -> str | None:
    """REST cluster object from get_endpoint_item / call_endpoint: carries typed citations."""
    cid = rec.get("id")
    if not isinstance(cid, int):
        return None
    e = cl_get_or_create(ledger, cid, None, tool)
    cit = e["citation"]
    for src_key, dst_key in (("case_name", "case_name"), ("case_name_full", "case_name_full"),
                             ("date_filed", "date_filed")):
        if rec.get(src_key):
            cit[dst_key] = rec[src_key]
    add_cites(e, rec.get("citations") or [])
    sub = []
    for s in rec.get("sub_opinions") or []:
        m = re.search(r"/opinions/(\d+)/", str(s))
        if m:
            sub.append(int(m.group(1)))
        elif isinstance(s, int):
            sub.append(s)
    add_opinion_ids(e, sub)
    if e["verification"].get("existence") != "verified":
        e["verification"].update({"existence": "verified", "method": f"{tool}:cluster", "checked_at": now_iso()})
    if rec.get("absolute_url"):
        e["source"]["url"] = "https://www.courtlistener.com" + rec["absolute_url"]
    return e["id"]


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def cl_store_full_text(matter: Path, ledger: dict, tool_input: dict, data: dict, text: str, tool: str,
                       tool_use_id: str | None) -> str | None:
    doc_id = data.get("doc_id")
    cluster_id = tool_input.get("cluster_id")
    opinion_id = tool_input.get("opinion_id") or doc_id
    e = cl_get_or_create(ledger, cluster_id, opinion_id, tool)
    add_opinion_ids(e, [doc_id] + [o.get("id") for o in data.get("cluster_opinions") or [] if isinstance(o, dict)])
    stem = e["id"] if doc_id in (None, e["source"].get("opinion_id")) else f"{e['id']}-op-{doc_id}"
    rel, digest = save_source(matter, stem, text, {"id": e["id"], "tool": tool, "tool_use_id": tool_use_id,
                                                    "doc_id": doc_id, "system": "courtlistener"})
    if stem == e["id"] or not e.get("local_path"):
        e["local_path"] = rel
        e["sha256"] = digest
    e.setdefault("files", [])
    if rel not in e["files"]:
        e["files"].append(rel)
    e["status"] = "retrieved"
    e["retrieved_at"] = now_iso()
    e["pagination"] = "star-pagination" in text or "<page-number" in text
    e["opinions_meta"] = data.get("cluster_opinions") or []
    e["verification"].update({"existence": "verified", "method": tool, "checked_at": now_iso()})
    return e["id"]


def cl_ingest_read(matter: Path, ledger: dict, payload: dict, data: dict, tool: str) -> list[str]:
    # The hosted CourtListener server returns opinion_id and no doc_type or doc_id (seen 2026-10-26);
    # the packaged server returns doc_type and doc_id. Normalize to the packaged shape.
    if "doc_type" not in data and isinstance(data.get("opinion_id"), int):
        data = {**data, "doc_type": "opinion", "doc_id": data["opinion_id"]}
    if data.get("doc_type") != "opinion" or not isinstance(data.get("text"), str):
        return []
    tool_input = payload.get("tool_input") or {}
    tool_use_id = payload.get("tool_use_id")
    if data.get("chunk_index") is None and "total_chunks" not in data:
        return [i for i in [cl_store_full_text(matter, ledger, tool_input, data, data["text"], tool, tool_use_id)] if i]
    # Chunked read: keep each chunk; assemble once every chunk of this chunk_size is present.
    doc_id, size, total = data.get("doc_id"), data.get("chunk_size"), data.get("total_chunks")
    chunk_dir = matter / "sources" / ".chunks" / f"cl-op-{doc_id}-{size}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks = data["text"] if isinstance(data["text"], list) else [data["text"]]
    indexes = data["chunk_index"] if isinstance(data["chunk_index"], list) else [data["chunk_index"]]
    for idx, chunk in zip(indexes, chunks):
        (chunk_dir / f"{int(idx):05d}.txt").write_text(chunk, encoding="utf-8", newline="\n")
    e = cl_get_or_create(ledger, tool_input.get("cluster_id"), tool_input.get("opinion_id") or doc_id, tool)
    add_opinion_ids(e, [doc_id])
    present = sorted(chunk_dir.glob("*.txt"))
    if isinstance(total, int) and len(present) >= total:
        full = "".join(p.read_text(encoding="utf-8") for p in present[:total])
        return [i for i in [cl_store_full_text(matter, ledger, tool_input, data, full, tool, tool_use_id)] if i]
    e["partial_read"] = {"doc_id": doc_id, "chunk_size": size, "chunks_present": len(present), "total_chunks": total}
    return [e["id"]]


def ingest_courtlistener(matter: Path, ledger: dict, payload: dict, data, tool: str) -> list[str]:
    touched: list[str] = []
    if tool == "read_document" and isinstance(data, dict):
        return cl_ingest_read(matter, ledger, payload, data, tool)
    tool_input = payload.get("tool_input") or {}
    if tool == "search_document":
        import treatment_screen

        return treatment_screen.store_passages(matter, ledger, tool_input, data)
    if tool in ("search", "get_more_results") and isinstance(data, dict) and "cites:" in str(tool_input.get("q") or ""):
        import treatment_screen

        return treatment_screen.store_citing(matter, ledger, tool_input, data)
    if tool in ("search", "get_more_results") and isinstance(data, dict):
        for hit in data.get("results") or []:
            if isinstance(hit, dict):
                i = cl_ingest_search_hit(ledger, hit, tool)
                if i:
                    touched.append(i)
        return touched
    for obj in walk(data):
        if isinstance(obj.get("citations"), list) and (obj.get("case_name") or obj.get("case_name_full")) \
                and isinstance(obj.get("id"), int):
            i = cl_ingest_cluster_record(ledger, obj, tool)
        elif isinstance(obj.get("cluster_id"), int) and (obj.get("caseName") or obj.get("case_name")):
            i = cl_ingest_search_hit(ledger, obj, tool)
        else:
            i = None
        if i and i not in touched:
            touched.append(i)
    return touched


# ---------------------------------------------------------------- Georgia Commons

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.S | re.M)
_GA_REPORTER_RE = re.compile(r"(\d+)\s+(Ga\. App\.|Ga\.|S\.E\.2d|S\.E\.3d|S\.E\.)\s+(\d+)")


def parse_front_matter_docs(text: str) -> list[tuple[dict, str]]:
    text = text.replace("\r\n", "\n")
    docs = []
    matches = list(_FM_RE.finditer(text))
    for n, m in enumerate(matches):
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        end = matches[n + 1].start() if n + 1 < len(matches) else len(text)
        docs.append((meta, text[m.start():end]))
    return docs


def gc_entry_id(collection: str, gc_id: str) -> str:
    return "gc-" + re.sub(r"[^a-z0-9.]+", "-", f"{collection}-{gc_id}".lower()).strip("-")


def ingest_gc_doc(matter: Path, ledger: dict, meta: dict, body: str, tool: str, tool_use_id: str | None) -> str | None:
    collection, gc_id = meta.get("collection"), meta.get("id")
    if not collection or not gc_id or collection not in GC_TYPES:
        return None
    eid = gc_entry_id(collection, gc_id)
    rel, digest = save_source(matter, eid, body, {"id": eid, "tool": tool, "tool_use_id": tool_use_id,
                                                  "system": "georgiacommons", "corpus_version": meta.get("corpus_version")})
    title = meta.get("title", "")
    citation = {"cite_as": meta.get("cite_as"), "current_through": meta.get("current_through"),
                "corpus_version": meta.get("corpus_version"), "version": meta.get("version"),
                "in_force": {"true": True, "false": False}.get(meta.get("in_force", "").lower())}
    if collection == "code":
        heading = re.sub(r"^O\.C\.G\.A\.\s*§+\s*[\d.\-]+\.\s*", "", title)
        citation.update({"code": "O.C.G.A.", "section": gc_id, "heading": heading or None})
    elif collection == "opinions":
        citation["case_name"] = title or None
        citation["reporters"] = [{"volume": a, "reporter": b, "page": c, "type": None}
                                 for a, b, c in _GA_REPORTER_RE.findall(meta.get("cite_as") or "")]
        citation["date_filed"] = meta.get("date")
    else:
        citation.update({"heading": title or None})
    entry = {
        "id": eid,
        "type": GC_TYPES[collection],
        "status": "retrieved",
        "source": {"system": "georgiacommons", "gc_id": gc_id, "gc_collection": collection,
                   "url": meta.get("canonical_url"), "tool": tool},
        "retrieved_at": now_iso(),
        "sha256": digest,
        "local_path": rel,
        "citation": citation,
        "verification": {"existence": "verified", "name_match": None, "method": f"georgiacommons:{tool}",
                         "checked_at": now_iso()},
    }
    if get_entry(ledger, eid) is None:
        entry.update({"first_seen_at": now_iso(), "propositions": [], "quote_checks": [],
                      "treatment": {"level": "none", "verdict": None, "confidence": None,
                                    "manual_keycite": {"required": True, "done": False,
                                                       "result": None, "date": None}}})
    upsert(ledger, entry)
    return eid


def ingest_georgiacommons(matter: Path, ledger: dict, payload: dict, text: str, data, tool: str) -> list[str]:
    tool_input = payload.get("tool_input") or {}
    if tool == "verify_quote" and isinstance(data, dict):
        # verify_quote answers with a collection-prefixed id ("code:51-1-40"); front matter carries "51-1-40".
        raw_id = str(data.get("id") or tool_input.get("id") or "")
        gc_id = raw_id.split(":", 1)[1] if ":" in raw_id else raw_id
        for e in ledger["authorities"]:
            src = e.get("source", {})
            if src.get("gc_id") == gc_id and (":" not in raw_id or raw_id.split(":", 1)[0] == src.get("gc_collection")):
                e.setdefault("quote_checks", []).append({
                    "quote": tool_input.get("quote", ""), "verified": bool(data.get("verified")),
                    "occurrences": data.get("occurrences"), "method": "georgiacommons:verify_quote",
                    "checked_at": now_iso()})
                return [e["id"]]
        return []
    touched = []
    for meta, body in parse_front_matter_docs(text):
        i = ingest_gc_doc(matter, ledger, meta, body, tool, payload.get("tool_use_id"))
        if i:
            touched.append(i)
    return touched


# ---------------------------------------------------------------- uslaw-mcp


def ingest_uslaw(ledger: dict, data: dict, tool: str) -> list[str]:
    """uslaw-mcp document tools save the text themselves and return a ledger_hint; record it."""
    hint = data.get("ledger_hint") if isinstance(data, dict) else None
    if tool not in USLAW_DOC_TOOLS or not isinstance(hint, dict) or not hint.get("id"):
        return []
    eid = hint["id"]
    kind = hint.get("type", "regulation")
    entry = {
        "id": eid,
        "type": kind,
        "status": "retrieved",
        "source": {"system": data.get("system"), "url": data.get("source_url"), "tool": tool},
        "retrieved_at": data.get("retrieved_at") or now_iso(),
        "sha256": data.get("sha256"),
        "local_path": data.get("local_path"),
        "citation": hint.get("citation") or {},
        "verification": {"existence": "verified", "name_match": None, "method": f"uslaw:{tool}", "checked_at": now_iso()},
    }
    if get_entry(ledger, eid) is None:
        entry.update({"first_seen_at": now_iso(), "propositions": [], "quote_checks": [],
                      "treatment": {"level": "none", "verdict": None, "confidence": None,
                                    "manual_keycite": {"required": True, "done": False, "result": None, "date": None}}})
    upsert(ledger, entry)
    return [eid]


# ---------------------------------------------------------------- ingest entry point


def classify(payload: dict, text: str, data) -> str | None:
    tool = short_name(payload.get("tool_name", ""))
    hint = server_hint(payload)
    if ("uslaw" in hint or (isinstance(data, dict) and "ledger_hint" in data)) and tool in USLAW_TOOLS:
        return "uslaw"
    if "georgia" in hint or (tool in GC_TOOLS and _FM_RE.search(text.replace("\r\n", "\n"))):
        return "georgiacommons"
    if "courtlistener" in hint:
        return "courtlistener"
    if tool in GC_TOOLS and isinstance(data, dict) and tool == "verify_quote" and "verified" in data:
        return "georgiacommons"
    if tool in CL_TOOLS and (isinstance(data, (dict, list))):
        if tool == "read_document" and isinstance(data, dict) and (
                "doc_type" in data or isinstance(data.get("opinion_id"), int)):
            return "courtlistener"
        if tool == "search_document" and isinstance(data, dict) and isinstance(data.get("results"), list):
            return "courtlistener"
        # A forward sweep with no citers still records citing_count 0.
        if tool in ("search", "get_more_results") and isinstance(data, dict) and isinstance(data.get("results"), list) \
                and "cites:" in str((payload.get("tool_input") or {}).get("q") or ""):
            return "courtlistener"
        if any(isinstance(o.get("cluster_id"), int) or isinstance(o.get("citations"), list) for o in walk(data)):
            return "courtlistener"
    return None


def resolve_ingest_matter(project: Path) -> Path:
    matter = active_matter(project) or inbox(project)
    ensure_matter(matter)
    return matter


def cmd_ingest(_args) -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    project = None
    try:
        payload = json.loads(raw)
        project = project_dir(payload)
        if not (project / "research").is_dir():  # not a research workspace; the plugin is installed user-wide
            return 0
        if payload.get("hook_event_name") not in (None, "PostToolUse"):
            return 0
        if not str(payload.get("tool_name", "")).startswith("mcp__"):
            return 0
        if isinstance(payload.get("tool_response"), dict) and payload["tool_response"].get("isError"):
            return 0
        text = unspill(response_text(payload.get("tool_response")))
        data = try_json(text)
        system = classify(payload, text, data)
        if system is None:
            return 0
        matter = resolve_ingest_matter(project)
        tool = short_name(payload["tool_name"])
        with ledger_lock(matter):
            ledger = load_ledger(matter)
            if system == "courtlistener":
                touched = ingest_courtlistener(matter, ledger, payload, data, tool)
            elif system == "uslaw":
                touched = ingest_uslaw(ledger, data, tool)
            else:
                touched = ingest_georgiacommons(matter, ledger, payload, text, data, tool)
            if touched:
                save_ledger(matter, ledger)
    except Exception:
        log_dir = (project or Path.cwd()) / ".session"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "ingest-errors.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{now_iso()}\n{traceback.format_exc()}\n")
    return 0


# ---------------------------------------------------------------- human-facing subcommands


def matter_arg(value: str | None) -> Path:
    project = project_dir()
    if value:
        p = Path(value)
        return p if p.is_absolute() else project / p
    m = active_matter(project)
    if m is None:
        sys.exit("No active matter. Run: ledger.py create research/<course>/<assignment>")
    return m


def set_active(matter: Path) -> None:
    project = project_dir()
    marker = project / ".session" / "active-matter"
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        rel = matter.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        rel = str(matter)
    marker.write_text(rel + "\n", encoding="utf-8", newline="\n")


def cmd_create(args) -> int:
    matter = matter_arg(args.matter)
    ensure_matter(matter)
    if args.closed_universe:
        with ledger_lock(matter):
            ledger = load_ledger(matter)
            ledger["closed_universe"] = True
            save_ledger(matter, ledger)
    set_active(matter)
    print(f"Matter ready and active: {matter}")
    return 0


def cmd_use(args) -> int:
    matter = matter_arg(args.matter)
    if not (matter / "authorities.json").exists():
        sys.exit(f"No ledger at {matter}. Run: ledger.py create {args.matter}")
    set_active(matter)
    print(f"Active matter: {matter}")
    return 0


def label(e: dict) -> str:
    level = (e.get("treatment") or {}).get("level", "none")
    if e.get("type") == "secondary":
        return e.get("disclosure") or "Not reported"
    if e.get("type") != "case":
        return "n/a"
    return {"heavyweight": "Verified", "lightweight": "Screened"}.get(level, "Not validated")


def describe(e: dict) -> str:
    cit = e.get("citation") or {}
    if e.get("type") == "case":
        reps = ", ".join(f"{r['volume']} {r['reporter']} {r['page']}" for r in cit.get("reporters") or [])
        return f"{cit.get('case_name') or '(name unknown)'}, {reps or '(no reporter cite)'} ({cit.get('court_id') or '?'} {(cit.get('date_filed') or '')[:4]})"
    if e.get("type") == "secondary":
        return cit.get("bluebook") or (e.get("request") or {}).get("issue") or e["id"]
    return cit.get("cite_as") or f"{cit.get('code') or ''} {cit.get('section') or ''}".strip() or e["id"]


def cmd_show(args) -> int:
    matter = matter_arg(args.matter)
    ledger = load_ledger(matter)
    if args.json:
        print(json.dumps(ledger, indent=2, ensure_ascii=False))
        return 0
    rows = ledger["authorities"]
    print(f"Matter: {matter.name}  closed_universe={ledger.get('closed_universe')}  authorities={len(rows)}")
    for e in rows:
        mk = (e.get("treatment") or {}).get("manual_keycite") or {}
        print(f"- {e['id']} [{e['status']}, existence={e['verification']['existence']}, label={label(e)}, "
              f"keycite={'done: ' + str(mk.get('result')) if mk.get('done') else 'pending' if mk.get('required') else 'n/a'}] "
              f"{describe(e)}")
    return 0


def cmd_upsert(args) -> int:
    matter = matter_arg(args.matter)
    src = sys.stdin.read() if args.entry == "-" else Path(args.entry).read_text(encoding="utf-8")
    entry = json.loads(src)
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        upsert(ledger, entry)
        save_ledger(matter, ledger)
    print(f"Upserted {entry['id']}")
    return 0


def cmd_keycite_list(args) -> int:
    matter = matter_arg(args.matter)
    ledger = load_ledger(matter)
    pending = [e for e in ledger["authorities"] if e["status"] == "retrieved"
               and ((e.get("treatment") or {}).get("manual_keycite") or {}).get("required")
               and not e["treatment"]["manual_keycite"].get("done")]
    if not pending:
        print("No authorities await a manual KeyCite or Shepard's check.")
        return 0
    print("Run KeyCite or Shepard's by hand on each, then record: ledger.py mark <matter> <id> keycite=<result>")
    for e in pending:
        print(f"- [ ] {e['id']}: {describe(e)}")
    return 0


def cmd_mark(args) -> int:
    matter = matter_arg(args.matter)
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        e = get_entry(ledger, args.id)
        if e is None:
            sys.exit(f"No entry {args.id}")
        for pair in args.pairs:
            key, _, value = pair.partition("=")
            if key == "keycite":
                mk = e.setdefault("treatment", {}).setdefault("manual_keycite", {})
                mk.update({"required": True, "done": True, "result": value, "date": now_iso()[:10]})
            elif key == "note":
                e["notes"] = value
            else:
                sys.exit(f"Unknown field {key}; use keycite= or note=")
        save_ledger(matter, ledger)
    print(f"Marked {args.id}")
    return 0


def cmd_waive(args) -> int:
    """Record the user's waiver of one audit item (its key from audit/cite-check.json) so the Stop hook passes it."""
    matter = matter_arg(args.matter)
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        waivers = ledger.setdefault("waivers", [])
        if not any(w.get("key") == args.key for w in waivers):
            waivers.append({"key": args.key, "reason": args.reason, "by": "user", "date": now_iso()[:10]})
        save_ledger(matter, ledger)
    print(f"Waived: {args.key}")
    return 0


VERDICTS = ["VALID", "VALID BUT NARROWED", "AT RISK", "QUESTIONED", "INVALID FOR THIS PROPOSITION", "INVALID",
            "INDETERMINATE"]


def cmd_treatment(args) -> int:
    """Record a heavyweight validity verdict (the validity-checker agent's structured return)."""
    matter = matter_arg(args.matter)
    if args.verdict not in VERDICTS:
        sys.exit(f"verdict must be one of: {', '.join(VERDICTS)}")
    report = Path(args.report).read_text(encoding="utf-8") if args.report else None
    with ledger_lock(matter):
        ledger = load_ledger(matter)
        e = get_entry(ledger, args.id)
        if e is None or e.get("type") != "case":
            sys.exit(f"No case entry {args.id}")
        tr = e.setdefault("treatment", {})
        tr.update({"level": "heavyweight", "verdict": args.verdict, "confidence": args.confidence,
                   "proposition": args.proposition, "checked_at": now_iso(), "report_path": args.report,
                   "replacement": args.replacement})
        if report:
            tr["report"] = report
        tr.setdefault("manual_keycite", {"required": True, "done": False, "result": None, "date": None})
        save_ledger(matter, ledger)
    print(f"{args.id}: Verified (heavyweight), {args.verdict}, confidence {args.confidence}, for: {args.proposition}")
    return 0


def cmd_secondary(args) -> int:
    import secondary as sec

    try:
        if args.action == "request":
            matter = matter_arg(args.matter)
            spec = json.loads(sys.stdin.read() if args.src == "-" else Path(args.src).read_text(encoding="utf-8"))
            rid = sec.request(matter, spec)
            print(f"{rid} written to {(matter / 'audit' / 'secondary-requests.md').as_posix()} and ledgered as sec-{rid}")
        elif args.action == "ingest":
            matter = matter_arg(args.matter)
            src = Path(args.src) if args.src else matter / "audit" / "secondary-reports" / f"{args.id}.md"
            if not src.is_absolute() and not src.exists():
                src = matter / src
            e = sec.ingest(matter, args.id, sec.parse_report(src))
            print(f"sec-{args.id} reported: {e['citation']['bluebook']} [{e['disclosure']}]")
            if e["report"]["points_to_unresolved"]:
                print("Re-pull and ledger these before citing them: " + "; ".join(e["report"]["points_to_unresolved"]))
        elif args.action == "withdraw":
            sec.withdraw(matter_arg(args.matter), args.id)
            print(f"{args.id} withdrawn")
        else:
            rows = sec.listing(load_ledger(matter_arg(args.matter)))
            print("\n".join(rows) if rows else "No secondary-source requests in this matter.")
    except sec.RelayError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create"); p.add_argument("matter"); p.add_argument("--closed-universe", action="store_true")
    p.set_defaults(fn=cmd_create)
    p = sub.add_parser("use"); p.add_argument("matter"); p.set_defaults(fn=cmd_use)
    p = sub.add_parser("show"); p.add_argument("matter", nargs="?"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("upsert"); p.add_argument("matter"); p.add_argument("entry"); p.set_defaults(fn=cmd_upsert)
    p = sub.add_parser("keycite-list"); p.add_argument("matter", nargs="?"); p.set_defaults(fn=cmd_keycite_list)
    p = sub.add_parser("mark"); p.add_argument("matter"); p.add_argument("id"); p.add_argument("pairs", nargs="+")
    p.set_defaults(fn=cmd_mark)
    p = sub.add_parser("ingest"); p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("waive"); p.add_argument("matter"); p.add_argument("key"); p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_waive)
    p = sub.add_parser("treatment"); p.add_argument("matter"); p.add_argument("id")
    p.add_argument("--verdict", required=True); p.add_argument("--confidence", choices=["low", "moderate", "high"], required=True)
    p.add_argument("--proposition", required=True); p.add_argument("--report"); p.add_argument("--replacement")
    p.set_defaults(fn=cmd_treatment)
    p = sub.add_parser("secondary"); ss = p.add_subparsers(dest="action", required=True)
    q = ss.add_parser("request"); q.add_argument("matter"); q.add_argument("src")
    q = ss.add_parser("ingest"); q.add_argument("matter"); q.add_argument("id"); q.add_argument("src", nargs="?")
    q = ss.add_parser("list"); q.add_argument("matter", nargs="?")
    q = ss.add_parser("withdraw"); q.add_argument("matter"); q.add_argument("id")
    p.set_defaults(fn=cmd_secondary)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
