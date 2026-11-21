// Legal summaries of tool calls for the transcript (H1, docs/04-harness.md section 5.2). Pure functions.

export type Source = 'courtlistener' | 'georgiacommons' | 'uslaw' | 'draft'

const CL_SUFFIXES = new Set(['search', 'read_document', 'get_endpoint_item', 'call_endpoint', 'analyze_citations',
  'resume_citation_analysis', 'get_more_results', 'search_document'])

export function suffix(tool: string): string {
  const i = tool.lastIndexOf('__')
  return i >= 0 ? tool.slice(i + 2) : tool
}

function server(tool: string): string {
  const parts = tool.split('__')
  return parts.length >= 3 ? parts[1].toLowerCase() : ''
}

export function classify(tool: string, input: unknown): Source | null {
  if (tool === 'Write' || tool === 'Edit' || tool === 'MultiEdit') {
    const fp = String((input as { file_path?: string } | null)?.file_path ?? '').replace(/\\/g, '/')
    return /\/research\/.+\/drafts\//.test(fp) ? 'draft' : null
  }
  if (!tool.startsWith('mcp__')) return null
  const s = server(tool)
  if (s.includes('georgiacommons')) return 'georgiacommons'
  if (s.includes('uslaw')) return 'uslaw'
  return CL_SUFFIXES.has(suffix(tool)) ? 'courtlistener' : null
}

/** The text an MCP tool returned, from whatever shape the row carries. */
export function outputText(output: unknown): string {
  if (output == null) return ''
  if (typeof output === 'string') return output
  if (Array.isArray(output)) {
    return output.map(b => (b && typeof b === 'object' && 'text' in b ? String((b as { text: unknown }).text) : '')).join('\n')
  }
  if (typeof output === 'object') {
    const o = output as Record<string, unknown>
    if (Array.isArray(o.content)) return outputText(o.content)
    if (typeof o.text === 'string') return o.text
  }
  return ''
}

export function outputJson(output: unknown): Record<string, unknown> | null {
  const t = outputText(output).trim()
  if (!t.startsWith('{')) return null
  try {
    return JSON.parse(t) as Record<string, unknown>
  } catch {
    return null
  }
}

function frontMatter(text: string): Record<string, string> {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text.trim())
  const out: Record<string, string> = {}
  for (const line of m ? m[1].split(/\r?\n/) : []) {
    const kv = /^([\w-]+):\s*(.*)$/.exec(line)
    if (kv) out[kv[1]] = kv[2].trim()
  }
  return out
}

function list(v: unknown): string {
  return Array.isArray(v) ? v.join(', ') : v == null ? '' : String(v)
}

function short(text: string, n = 70): string {
  const t = text.replace(/\s+/g, ' ').trim()
  return t.length > n ? `${t.slice(0, n - 1)}…` : t
}

const CASE_CITE = /\b\d{1,4} (?:Ga\. App\.|Ga\.|S\.E\.(?:2d|3d)?|U\.S\.|S\. ?Ct\.|L\. ?Ed\.(?: 2d)?|F\.(?:2d|3d|4th)?|F\. Supp\.(?: 2d| 3d)?|F\. App'x) \d{1,5}\b/g
const STATUTE_CITE = /(?:O\.C\.G\.A\.|U\.S\.C\.|C\.F\.R\.)\s*§+\s*[\d.\-]+[\w()]*/g

export function countCitations(text: string): number {
  const seen = new Set<string>([...(text.match(CASE_CITE) ?? []), ...(text.match(STATUTE_CITE) ?? [])])
  return seen.size
}

export type Row = { title: string; detail?: string }

/** One line for the tool row: what the call does, in legal terms. */
export function describeCall(tool: string, input: unknown, output: unknown, names: Record<string, string> = {}): Row | null {
  const src = classify(tool, input)
  if (!src) return null
  const inp = (input ?? {}) as Record<string, unknown>
  const data = outputJson(output)
  const s = suffix(tool)
  if (src === 'draft') {
    const fp = String(inp.file_path ?? '').replace(/\\/g, '/')
    const file = fp.split('/').pop()
    const body = String(inp.content ?? inp.new_string ?? '')
    const n = countCitations(body)
    return { title: `Draft updated · ${file}`, detail: `${n} citation${n === 1 ? '' : 's'} · cleared by the citation gate` }
  }
  if (src === 'courtlistener') {
    if (s === 'search' || s === 'get_more_results') {
      const bits = [inp.semantic ? 'semantic' : null, inp.q ? `"${short(String(inp.q), 60)}"` : null,
        inp.court ? `court: ${list(inp.court)}` : null].filter(Boolean)
      const count = data ? (data.count ?? (Array.isArray(data.results) ? data.results.length : undefined)) : undefined
      return { title: `Searching CourtListener · ${bits.join(' · ')}`, detail: count === undefined ? undefined : `${count} result${count === 1 ? '' : 's'}` }
    }
    if (s === 'read_document') {
      const id = (inp.cluster_id ?? inp.opinion_id) as number | undefined
      const name = id !== undefined ? names[`cl-cluster-${id}`] : undefined
      const chars = data?.total_chars as number | undefined
      return { title: `Reading ${name ?? `opinion ${id ?? ''}`.trim()}`,
               detail: [chars ? `${chars.toLocaleString('en-US')} characters` : null,
                        data && 'chunk_index' in data ? `chunk ${Number(data.chunk_index) + 1} of ${data.total_chunks}` : 'saved to sources/']
                 .filter(Boolean).join(' · ') }
    }
    if (s === 'get_endpoint_item' || s === 'call_endpoint') {
      const ep = String(inp.endpoint_id ?? '')
      const name = data?.case_name as string | undefined
      return { title: `Fetching CourtListener ${ep || 'record'}${name ? ` · ${name}` : ''}` }
    }
    if (s === 'analyze_citations' || s === 'resume_citation_analysis') return { title: 'Verifying citations with CourtListener' }
    if (s === 'search_document') return { title: `Searching within opinion ${list(inp.opinion_id ?? inp.cluster_id)}`, detail: inp.q ? `"${short(String(inp.q), 50)}"` : undefined }
  }
  if (src === 'georgiacommons') {
    const fm = frontMatter(outputText(output))
    if (s === 'verify_quote') {
      const ok = data?.verified
      return { title: `Quote check · ${String(data?.id ?? inp.id ?? '')}`,
               detail: ok === undefined ? undefined : ok ? `verified (${data?.occurrences ?? 1} occurrence${data?.occurrences === 1 ? '' : 's'})` : 'NOT FOUND in the stored text' }
    }
    if (fm.cite_as) {
      const through = fm.current_through?.replace(/^Including Acts of the /, 'current through ')
      return { title: fm.cite_as, detail: [fm.title?.replace(/^.*?\d\.\s*/, ''), through].filter(Boolean).join(' · ') }
    }
    return { title: `Georgia Commons · ${s.replace(/_/g, ' ')}`, detail: inp.citation || inp.query ? short(String(inp.citation ?? inp.query), 60) : undefined }
  }
  // uslaw
  if (s === 'ecfr_section') {
    return { title: `${inp.title} C.F.R. § ${inp.section}`, detail: data?.up_to_date_as_of ? `eCFR up to date as of ${data.up_to_date_as_of} · saved to sources/` : undefined }
  }
  if (s === 'ecfr_versions') return { title: `CFR amendment history · ${inp.title} C.F.R. ${inp.section ? `§ ${inp.section}` : `pt. ${inp.part}`}`, detail: data?.count !== undefined ? `${data.count} versions` : undefined }
  if (s === 'fr_search') {
    const bits = [inp.term ? `"${short(String(inp.term), 40)}"` : null, inp.cfr_title ? `${inp.cfr_title} CFR ${inp.cfr_part ?? ''}`.trim() : null, inp.doc_type ? String(inp.doc_type).toLowerCase() : null].filter(Boolean)
    return { title: `Searching the Federal Register · ${bits.join(' · ')}`, detail: data?.count !== undefined ? `${data.count} documents` : undefined }
  }
  if (s === 'fr_document') return { title: `Federal Register ${data?.citation ?? inp.document_number}`, detail: data?.title ? short(String(data.title), 70) : undefined }
  if (s === 'govinfo_package') {
    const hint = (data?.ledger_hint as { citation?: { cite_as?: string } } | undefined)?.citation?.cite_as
    return { title: `GovInfo · ${hint ?? inp.granule_id ?? inp.package_id}`, detail: 'saved to sources/' }
  }
  return { title: `Federal sources · ${s.replace(/_/g, ' ')}` }
}

/** A few lines for the result block in place of raw JSON. */
export function describeResult(tool: string, input: unknown, output: unknown): string[] | null {
  const src = classify(tool, input)
  if (!src || src === 'draft') return null
  const data = outputJson(output)
  const s = suffix(tool)
  if (src === 'courtlistener' && (s === 'search' || s === 'get_more_results') && Array.isArray(data?.results)) {
    return (data.results as Record<string, unknown>[]).slice(0, 5).map(r => {
      const cites = Array.isArray(r.citation) ? (r.citation as string[]).filter(c => !/LEXIS|WL /.test(c)).slice(0, 2).join(', ') : ''
      return `${r.caseName ?? r.case_name ?? '(untitled)'}${cites ? `, ${cites}` : ''} (${[r.court_id, String(r.dateFiled ?? '').slice(0, 4)].filter(Boolean).join(' ')})`
    })
  }
  if (src === 'courtlistener' && s === 'read_document' && data) {
    const text = String(data.text ?? '')
    return [`${Number(data.total_chars ?? text.length).toLocaleString('en-US')} characters; star pagination ${/star-pagination|<page-number/.test(text) ? 'present' : 'absent'}`]
  }
  if (src === 'uslaw' && Array.isArray(data?.results)) {
    return (data.results as Record<string, unknown>[]).slice(0, 5).map(r =>
      short([r.citation ?? r.document_number ?? r.packageId ?? r.id, r.title ?? r.heading, r.publication_date ?? r.postedDate ?? r.dateIssued].filter(Boolean).join(' · '), 100))
  }
  if (src === 'uslaw' && Array.isArray(data?.versions)) {
    const v = data.versions as { date?: string }[]
    return [`${v.length} versions; latest ${v[v.length - 1]?.date ?? 'unknown'}`]
  }
  if (data && typeof data.text === 'string') return [short(data.text, 140)]
  const t = outputText(output)
  return t ? [short(t.replace(/^---[\s\S]*?---/, ''), 140)] : []
}

// ---------------------------------------------------------------- /secondary card (docs/05-secondary-sources.md section 6)

export type RelayCard = { action: 'request' | 'ingest' | 'list' | 'withdraw'; requestId: string | null; title: string; lines: string[] }

const RELAY_RE = /ledger\.py["']?\s+secondary\s+(request|ingest|list|withdraw)\b(?:\s+\S+)?(?:\s+(SR-\d+))?/

/** A Bash call that runs the Westlaw relay, drawn as a card; null for every other call. */
export function relayCard(tool: string, input: unknown, output: unknown): RelayCard | null {
  if (tool !== 'Bash') return null
  const m = RELAY_RE.exec(String((input as { command?: string } | null)?.command ?? ''))
  if (!m) return null
  const action = m[1] as RelayCard['action']
  const text = outputText(output).trim()
  const rid = m[2] ?? /\b(SR-\d+)\b/.exec(text)?.[1] ?? null
  const lines = text ? text.split('\n').map(l => l.trimEnd()).filter(Boolean).slice(0, 12) : []
  const title = action === 'request' ? `Westlaw request ${rid ?? ''} written · run each search by hand`.replace('  ', ' ')
    : action === 'ingest' ? `Westlaw report ${rid ?? ''} recorded`.replace('  ', ' ')
    : action === 'withdraw' ? `Westlaw request ${rid ?? ''} withdrawn`.replace('  ', ' ')
    : 'Westlaw requests in this matter'
  return { action, requestId: rid, title, lines }
}
