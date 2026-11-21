"""uslaw-mcp tools (architecture section 3.2). Document tools save to the active matter's sources/."""

from __future__ import annotations

import re
from typing import Literal

import httpx
from fastmcp import FastMCP

from .common import USER_AGENT, env_value, envelope, html_to_text, slug

mcp = FastMCP(
    "uslaw",
    instructions=(
        "Federal legal sources for the legal-research plugin: eCFR (point-in-time CFR text), Federal Register, "
        "GovInfo (U.S. Code, public laws, Statutes at Large, CFR annual editions), Congress.gov (bills, laws, CRS "
        "reports), Regulations.gov (dockets and documents). Search tools return snippets for triage only; read the "
        "document with the matching document tool (ecfr_section, fr_document, govinfo_package) before quoting or "
        "characterizing it. Document tools save the text to the active matter's sources/ and return its sha256."
    ),
)

ECFR = "https://www.ecfr.gov/api/versioner/v1"
FR = "https://www.federalregister.gov/api/v1"
GOVINFO = "https://api.govinfo.gov"
CONGRESS = "https://api.congress.gov/v3"
REGS = "https://api.regulations.gov/v4"


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=60, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
                             follow_redirects=True)


def data_gov_headers() -> dict:
    key = env_value("DATA_GOV_API_KEY")
    if not key:
        raise RuntimeError("DATA_GOV_API_KEY is missing from the environment and the repository .env.")
    return {"X-Api-Key": key}


def congress_headers() -> dict:
    key = env_value("CONGRESS_GOV_API_KEY") or env_value("DATA_GOV_API_KEY")
    if not key:
        raise RuntimeError("CONGRESS_GOV_API_KEY is missing from the environment and the repository .env.")
    return {"X-Api-Key": key}


async def get_json(c: httpx.AsyncClient, url: str, **kw) -> dict:
    r = await c.get(url, **kw)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- eCFR


async def ecfr_title_meta(c: httpx.AsyncClient, title: int) -> dict:
    data = await get_json(c, f"{ECFR}/titles.json")
    for t in data["titles"]:
        if t["number"] == title:
            return t
    raise ValueError(f"No CFR title {title}.")


@mcp.tool
async def ecfr_section(title: int, section: str, date: str | None = None) -> dict:
    """Point-in-time text of one CFR section from the eCFR versioner, e.g. title=15, section="744.11".

    date: YYYY-MM-DD; omitted, the title's up_to_date_as_of date. Saves the text to sources/ and returns the
    heading, the eCFR currency dates, and the sha256. eCFR is "authoritative but unofficial"; vacated text stays
    until the agency publishes a change, so check the Federal Register for vacatur notices.
    """
    part = section.split(".")[0]
    async with client() as c:
        meta = await ecfr_title_meta(c, title)
        when = date or meta["up_to_date_as_of"]
        api_url = f"{ECFR}/full/{when}/title-{title}.xml"
        r = await c.get(api_url, params={"part": part, "section": section})
        r.raise_for_status()
        xml = r.text
    head = re.search(r"<HEAD>(.*?)</HEAD>", xml, re.S)
    heading = html_to_text(head.group(1)) if head else None
    text = html_to_text(xml)
    cite = f"{title} C.F.R. § {section}"
    return envelope(
        entry_id=f"ecfr-{title}-{slug(section)}", text=text, ext=".txt", system="ecfr", tool="ecfr_section",
        source_url=f"https://www.ecfr.gov/on/{when}/title-{title}/section-{section}", version_or_date=when,
        ledger_hint={"type": "regulation", "citation": {"code": "C.F.R.", "title": str(title), "section": section,
                                                        "heading": heading, "cite_as": cite, "version": when,
                                                        "current_through": f"eCFR up to date as of {meta['up_to_date_as_of']}"}},
        extra={"heading": heading, "up_to_date_as_of": meta["up_to_date_as_of"],
               "latest_amended_on": meta.get("latest_amended_on"), "api_url": f"{api_url}?part={part}&section={section}"},
    )


@mcp.tool
async def ecfr_versions(title: int, part: str, section: str | None = None) -> dict:
    """Amendment dates for a CFR part or section (eCFR versions endpoint), oldest first.

    Each version carries date, amendment_date, issue_date, name, substantive, removed. Point-in-time coverage
    starts January 2017.
    """
    params = {"part": part}
    if section:
        params["section"] = section
    async with client() as c:
        data = await get_json(c, f"{ECFR}/versions/title-{title}.json", params=params)
    versions = [{k: v.get(k) for k in ("date", "amendment_date", "issue_date", "identifier", "name", "substantive", "removed")}
                for v in data.get("content_versions", [])]
    return {"system": "ecfr", "title": title, "part": part, "section": section, "count": len(versions),
            "versions": versions, "meta": data.get("meta")}


@mcp.tool
async def ecfr_search(query: str, title: int | None = None, per_page: int = 20) -> dict:
    """Full-text search of the current eCFR. Results are snippets for triage; read hits with ecfr_section."""
    params: dict = {"query": query, "per_page": per_page}
    if title:
        params["hierarchy[title]"] = title
    async with client() as c:
        data = await get_json(c, "https://www.ecfr.gov/api/search/v1/results", params=params)
    hits = []
    for r in data.get("results", []):
        h = r.get("hierarchy") or {}
        hits.append({"title": h.get("title"), "part": h.get("part"), "section": h.get("section"),
                     "heading": (r.get("headings") or {}).get("section"), "excerpt": html_to_text(r.get("full_text_excerpt") or ""),
                     "starts_on": r.get("starts_on")})
    return {"system": "ecfr", "query": query, "count": (data.get("meta") or {}).get("total_count"), "results": hits}


# ---------------------------------------------------------------- Federal Register

FR_FIELDS = ["document_number", "title", "type", "publication_date", "citation", "effective_on", "html_url",
             "raw_text_url", "cfr_references", "agencies", "docket_ids", "abstract"]


@mcp.tool
async def fr_search(term: str | None = None, cfr_title: int | None = None, cfr_part: str | None = None,
                    doc_type: Literal["RULE", "PRORULE", "NOTICE", "PRESDOCU"] | None = None,
                    date_gte: str | None = None, date_lte: str | None = None, per_page: int = 20,
                    order: Literal["newest", "oldest", "relevance"] = "newest") -> dict:
    """Federal Register document search (1994 forward). Filter by term, CFR title and part, type, and dates.

    For vacatur notices use term '"notification of court decision"' or 'vacatur' with the CFR part.
    Results are metadata for triage; read a document with fr_document.
    """
    params: list[tuple[str, str]] = [("per_page", str(per_page)), ("order", order)]
    params += [("fields[]", f) for f in FR_FIELDS]
    if term:
        params.append(("conditions[term]", term))
    if cfr_title:
        params.append(("conditions[cfr][title]", str(cfr_title)))
    if cfr_part:
        params.append(("conditions[cfr][part]", str(cfr_part)))
    if doc_type:
        params.append(("conditions[type][]", doc_type))
    if date_gte:
        params.append(("conditions[publication_date][gte]", date_gte))
    if date_lte:
        params.append(("conditions[publication_date][lte]", date_lte))
    async with client() as c:
        data = await get_json(c, f"{FR}/documents.json", params=params)
    results = [{k: r.get(k) for k in FR_FIELDS if k != "agencies"} | {"agencies": [a.get("name") for a in r.get("agencies") or []]}
               for r in data.get("results", [])]
    return {"system": "federalregister", "description": data.get("description"), "count": data.get("count"),
            "results": results}


@mcp.tool
async def fr_document(document_number: str) -> dict:
    """One Federal Register document by number (e.g. "2026-17231"): metadata plus full text, saved to sources/."""
    async with client() as c:
        meta = await get_json(c, f"{FR}/documents/{document_number}.json")
        text = ""
        if meta.get("raw_text_url"):
            r = await c.get(meta["raw_text_url"])
            r.raise_for_status()
            text = html_to_text(r.text)
        elif meta.get("body_html_url"):
            r = await c.get(meta["body_html_url"])
            r.raise_for_status()
            text = html_to_text(r.text)
    fr_cite = meta.get("citation")
    header = (f"{meta.get('title')}\n{meta.get('type')} | {fr_cite} | published {meta.get('publication_date')} | "
              f"effective {meta.get('effective_on')} | document {document_number}\n\n")
    vol, page = (fr_cite.split(" FR ") + [None])[:2] if fr_cite and " FR " in fr_cite else (None, None)
    return envelope(
        entry_id=f"fr-{slug(document_number)}", text=header + text, ext=".txt", system="federalregister",
        tool="fr_document", source_url=meta.get("html_url") or f"https://www.federalregister.gov/d/{document_number}",
        version_or_date=meta.get("publication_date"),
        ledger_hint={"type": "regulation", "citation": {"code": "Fed. Reg.", "cite_as": fr_cite, "title": vol, "section": page,
                                                        "heading": meta.get("title"), "date_filed": meta.get("publication_date"),
                                                        "docket_number": ", ".join(meta.get("docket_ids") or []) or None}},
        extra={"title": meta.get("title"), "type": meta.get("type"), "citation": fr_cite,
               "publication_date": meta.get("publication_date"), "effective_on": meta.get("effective_on"),
               "cfr_references": meta.get("cfr_references"), "agencies": [a.get("name") for a in meta.get("agencies") or []]},
    )


# ---------------------------------------------------------------- GovInfo


@mcp.tool
async def govinfo_search(query: str, collection: str | None = None, page_size: int = 20) -> dict:
    """GovInfo full-text search. collection: USCODE, PLAW, STATUTE, CFR, FR, USCOURTS, CONAN, CHRG, CREC, BILLS.

    Results are metadata for triage; read one with govinfo_package (package id, optional granule id).
    """
    q = f"collection:({collection}) AND ({query})" if collection else query
    async with client() as c:
        r = await c.post(f"{GOVINFO}/search", headers=data_gov_headers(),
                         json={"query": q, "pageSize": page_size, "offsetMark": "*"})
        r.raise_for_status()
        data = r.json()
    results = [{k: x.get(k) for k in ("title", "packageId", "granuleId", "collectionCode", "dateIssued", "lastModified",
                                      "governmentAuthor", "resultLink")} for x in data.get("results", [])]
    return {"system": "govinfo", "query": q, "count": data.get("count"), "results": results}


@mcp.tool
async def govinfo_package(package_id: str, granule_id: str | None = None) -> dict:
    """One GovInfo package or granule (e.g. package USCODE-2024-title42, granule USCODE-2024-title42-chap21-subchapI-sec1983):
    summary plus text, saved to sources/."""
    path = f"/packages/{package_id}" + (f"/granules/{granule_id}" if granule_id else "")
    async with client() as c:
        h = data_gov_headers()
        summary = await get_json(c, f"{GOVINFO}{path}/summary", headers=h)
        links = summary.get("download") or {}
        text = ""
        for key in ("txtLink", "htmLink", "xmlLink"):
            if links.get(key):
                r = await c.get(links[key], headers=h)
                if r.status_code == 200:
                    text = html_to_text(r.text)
                    break
    ident = granule_id or package_id
    hint: dict = {"type": "statute", "citation": {"heading": summary.get("title"), "version": summary.get("dateIssued"),
                                                  "cite_as": summary.get("title")}}
    m = re.match(r"USCODE-(\d{4})-title(\d+)\S*-sec(\w[\w.\-]*)$", ident)
    if m:
        hint["citation"].update({"code": "U.S.C.", "title": m.group(2), "section": m.group(3),
                                 "cite_as": f"{m.group(2)} U.S.C. § {m.group(3)} ({m.group(1)})", "version": m.group(1)})
    elif summary.get("collectionCode") == "CFR":
        hint["type"] = "regulation"
    return envelope(
        entry_id=f"govinfo-{slug(ident)}", text=text, ext=".txt", system="govinfo", tool="govinfo_package",
        source_url=summary.get("detailsLink") or f"https://www.govinfo.gov/app/details/{package_id}",
        version_or_date=summary.get("dateIssued"), ledger_hint=hint,
        extra={"title": summary.get("title"), "collection": summary.get("collectionCode"),
               "date_issued": summary.get("dateIssued"), "last_modified": summary.get("lastModified")},
    )


# ---------------------------------------------------------------- Congress.gov


@mcp.tool
async def congress_bill(congress: int, bill_type: str, number: int) -> dict:
    """A bill's record from Congress.gov (bill_type: hr, s, hjres, sjres, hconres, sconres, hres, sres):
    title, sponsor, latest action, laws enacted, and the URLs of each text version (Congress.gov never inlines text)."""
    base = f"{CONGRESS}/bill/{congress}/{bill_type.lower()}/{number}"
    async with client() as c:
        h = congress_headers()
        bill = (await get_json(c, base, headers=h, params={"format": "json"})).get("bill", {})
        texts = (await get_json(c, f"{base}/text", headers=h, params={"format": "json"})).get("textVersions", [])
    return {"system": "congress", "congress": congress, "type": bill_type, "number": number,
            "title": bill.get("title"), "introduced": bill.get("introducedDate"),
            "sponsors": [s.get("fullName") for s in bill.get("sponsors") or []],
            "latest_action": bill.get("latestAction"), "laws": bill.get("laws"),
            "text_versions": [{"type": t.get("type"), "date": t.get("date"),
                               "formats": {f.get("type"): f.get("url") for f in t.get("formats") or []}} for t in texts]}


@mcp.tool
async def congress_law(congress: int, number: int, law_type: Literal["pub", "priv"] = "pub") -> dict:
    """A public or private law from Congress.gov by Congress and number (e.g. congress=119, number=21)."""
    async with client() as c:
        data = await get_json(c, f"{CONGRESS}/law/{congress}/{law_type}/{number}", headers=congress_headers(),
                              params={"format": "json"})
    bill = data.get("bill", {})
    return {"system": "congress", "congress": congress, "law_type": law_type, "number": number,
            "title": bill.get("title"), "laws": bill.get("laws"), "latest_action": bill.get("latestAction"),
            "origin_bill": {"type": bill.get("type"), "number": bill.get("number")}}


@mcp.tool
async def crs_report(report_number: str) -> dict:
    """A Congressional Research Service report's record from Congress.gov (e.g. "R46571"): title, dates, authors,
    topics, and format URLs. CRS reports are free secondary sources (docs/05-secondary-sources.md section 5)."""
    async with client() as c:
        data = await get_json(c, f"{CONGRESS}/crsreport/{report_number}", headers=congress_headers(),
                              params={"format": "json"})
    rep = data.get("CRSReport") or data.get("crsReport") or data
    return {"system": "congress", "report": rep}


# ---------------------------------------------------------------- Regulations.gov


@mcp.tool
async def regs_search(term: str, agency: str | None = None, docket: str | None = None, page_size: int = 20) -> dict:
    """Regulations.gov document search (rules, proposed rules, notices, supporting material) for triage."""
    params = {"filter[searchTerm]": term, "page[size]": max(5, min(page_size, 250)), "sort": "-postedDate"}
    if agency:
        params["filter[agencyId]"] = agency
    if docket:
        params["filter[docketId]"] = docket
    async with client() as c:
        data = await get_json(c, f"{REGS}/documents", headers=data_gov_headers(), params=params)
    rows = [{"id": d.get("id"), **{k: (d.get("attributes") or {}).get(k) for k in ("title", "documentType", "docketId",
                                                                                   "agencyId", "postedDate", "frDocNum")}}
            for d in data.get("data", [])]
    return {"system": "regulations", "count": (data.get("meta") or {}).get("totalElements"), "results": rows}


@mcp.tool
async def regs_docket(docket_id: str) -> dict:
    """A Regulations.gov docket's record (e.g. "BIS-2026-0012")."""
    async with client() as c:
        data = await get_json(c, f"{REGS}/dockets/{docket_id}", headers=data_gov_headers())
    return {"system": "regulations", "docket": data.get("data")}


# ---------------------------------------------------------------- U.S. Code mirror and Constitution Annotated tables


@mcp.tool
async def uscode_section(title: str, section: str) -> dict:
    """One U.S. Code section from the local release-point mirror (data/uscode/uscode.db), e.g. title="42", section="1983".

    The text carries the release point it is current through (Pub. L. <congress>-<law>). When the mirror lacks the
    title, use govinfo_search and govinfo_package for the annual edition and say which edition you cited.
    """
    from . import uscode

    row = uscode.get_section(title, section)
    if row is None:
        raise ValueError(f"{title} U.S.C. § {section} is not in the local mirror. Build it with scripts/uscode_mirror.py "
                         f"(the user approves the download), or retrieve the annual edition with govinfo_search and govinfo_package.")
    text = f"{title} U.S.C. § {section}. {row['heading']}\n\n{row['text']}"
    rp = row["release_point"]
    return envelope(
        entry_id=f"usc-{slug(title)}-{slug(section)}", text=text, ext=".txt", system="uscode", tool="uscode_section",
        source_url=f"https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title{title}-section{section}",
        version_or_date=f"Pub. L. {rp}",
        ledger_hint={"type": "statute", "citation": {"code": "U.S.C.", "title": str(title), "section": str(section),
                                                     "heading": row["heading"], "cite_as": f"{title} U.S.C. § {section}",
                                                     "current_through": f"release point Pub. L. {rp}", "version": rp}},
        extra={"heading": row["heading"], "release_point": rp, "status": row["status"]},
    )


@mcp.tool
async def uscode_search(query: str, title: str | None = None, limit: int = 20) -> dict:
    """Full-text search (SQLite FTS5 syntax) of the local U.S. Code mirror. Snippets for triage; read hits with uscode_section."""
    from . import uscode

    hits = uscode.search(query, title, limit)
    return {"system": "uscode", "query": query, "count": len(hits), "results": hits,
            "note": None if hits or uscode.db_path().is_file() else "The local mirror is not built yet."}


def _conan(name: str, query: str, limit: int) -> dict:
    import json as _json
    from .common import repo_root

    path = repo_root() / "data" / "conan" / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"data/conan/{name}.json is missing: save the Constitution Annotated page by hand and run "
                         f"scripts/conan_tables.py (the site blocks automated clients).")
    data = _json.loads(path.read_text(encoding="utf-8"))
    q = query.lower()
    rows = [r for r in data["rows"] if q in " ".join(str(v) for v in r.values()).lower()]
    return {"system": "conan", "table": data.get("title"), "source": data.get("source_url"), "saved_at": data.get("saved_at"),
            "count": len(rows), "results": rows[:limit]}


@mcp.tool
async def conan_overruled_decisions(query: str, limit: int = 20) -> dict:
    """Search the Constitution Annotated table of Supreme Court decisions overruled by subsequent decisions
    (express overrulings only), by case name or citation. A miss is no evidence a decision stands."""
    return _conan("decisions-overruled", query, limit)


@mcp.tool
async def conan_unconstitutional_laws(query: str, limit: int = 20) -> dict:
    """Search the Constitution Annotated table of federal and state laws held unconstitutional, by statute, case,
    or state. A miss is no evidence a law stands."""
    return _conan("unconstitutional-laws", query, limit)


# ---------------------------------------------------------------- Justice Manual (free secondary source)

JUSTICE = "https://www.justice.gov"
JM_SECTION_RE = re.compile(r"^(\d{1,2})-(\d{1,3})\.(\d{3,4})$")


def jm_extract(page: str, section: str) -> tuple[str, str | None, str | None]:
    """(text, heading, updated) of one section from a Justice Manual chapter page; each section opens with
    <h2>9-28.700 - Heading</h2> and runs to the next <h2>."""
    m = re.search(rf"<h2[^>]*>\s*{re.escape(section)}\s*-\s*(.*?)</h2>", page, re.S)
    if not m:
        raise ValueError(f"Section {section} is not on its chapter page.")
    nxt = re.search(r"<h2[\s>]", page[m.end():])
    block = page[m.end(): m.end() + nxt.start()] if nxt else page[m.end():]
    heading = html_to_text(m.group(1)).strip()
    upd = re.search(r"\[updated ([A-Z][a-z]+ \d{4})\]", block)
    body = html_to_text(block)  # the section's footnotes follow its <hr> inside the same block
    return body.strip(), heading, upd.group(1) if upd else None


@mcp.tool
async def jm_section(section: str) -> dict:
    """One section of the Justice Manual (e.g. "9-28.700"), DOJ's published prosecution and litigation policy, read
    from justice.gov and saved to sources/. Agency guidance and a free secondary source: it binds DOJ attorneys and
    creates no rights (JM 1-1.200). Cite as U.S. Dep't of Just., Just. Manual § 9-28.700 (<updated year>)."""
    m = JM_SECTION_RE.match(section.strip())
    if not m:
        raise ValueError('Give the section as title-chapter.section, e.g. "9-28.700".')
    title, chapter = m.group(1), m.group(2)
    async with client() as c:
        index = (await c.get(f"{JUSTICE}/jm/justice-manual")).text
        tm = re.search(rf'href="(/jm/title-{title}-[^"#]+)"', index)
        if not tm:
            raise ValueError(f"No Justice Manual title {title} on the index page.")
        title_page = (await c.get(JUSTICE + tm.group(1))).text
        cm = re.search(rf'href="(/jm/jm-{title}-{chapter}000[^"#]*)"', title_page)
        if not cm:
            raise ValueError(f"No chapter {title}-{chapter}.000 on the title {title} page.")
        url = JUSTICE + cm.group(1)
        r = await c.get(url)
        r.raise_for_status()
    text, heading, updated = jm_extract(r.text, section.strip())
    year = updated.split()[-1] if updated else None
    cite = f"U.S. Dep't of Just., Just. Manual § {section.strip()}" + (f" ({year})" if year else "")
    header = f"Justice Manual § {section.strip()} {heading}\n{url}#{section.strip()}\nupdated {updated or 'not stated'}\n\n"
    return envelope(
        entry_id=f"jm-{slug(section.strip())}", text=header + text, ext=".txt", system="justice-manual",
        tool="jm_section", source_url=f"{url}#{section.strip()}", version_or_date=updated,
        ledger_hint={"type": "agency_guidance", "citation": {"code": "Just. Manual", "section": section.strip(),
                                                               "heading": heading, "cite_as": cite, "updated": updated}},
        extra={"heading": heading, "updated": updated, "cite_as": cite},
    )


def main() -> None:
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
