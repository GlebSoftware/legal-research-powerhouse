// Reads the active research matter from disk and renders the hidden context block (docs/04-harness.md 5.1).
import type { EngineInterface } from 'claude-code'
import { scriptsDir } from './paths.ts'

export const MODES = ['research', 'draft', 'cite', 'free'] as const
export type Mode = (typeof MODES)[number]

export const PROTOCOL =
  'Legal research protocol: treat this prompt as a research request when it asks what the law is, whether ' +
  'authority is good law, what a statute requires, or how a court would rule, and load the matching skill ' +
  '(research-protocol, case-law-research, statute-research, secondary-source-request, citation-format) without ' +
  'waiting for a slash command. Cite only authorities retrieved this session or in the matter ledger; read an ' +
  'opinion with read_document before stating its holding; request fields on every CourtListener call; label ' +
  'every case Verified (heavyweight), Screened (lightweight), or Not validated; paywalled secondary sources ' +
  'arrive only through /secondary. If CourtListener is disconnected, say "CourtListener is disconnected, ' +
  'reconnect it before I proceed" and stop.'

export type Counts = {
  total: number
  retrieved: number
  candidates: number
  verified: number
  screened: number
  notValidated: number
  keycitePending: number
  secondaryRequested: number
  secondaryReported: number
}

export type Matter = {
  path: string
  question?: string
  jurisdiction?: string
  jurisdictionId: string
  audience?: string
  closedUniverse: boolean
  counts: Counts
}

async function readText($: EngineInterface, path: string): Promise<string | undefined> {
  try {
    const out = await $.fs.read(path)
    return typeof out === 'string' ? out : undefined
  } catch {
    return undefined
  }
}

export function frontMatter(text: string): Record<string, string> {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)
  const out: Record<string, string> = {}
  if (!m) return out
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line)
    if (!kv) continue
    const raw = kv[2].trim()
    let value = raw.replace(/^["']|["']$/g, '').trim()
    if (raw.startsWith('"')) {
      try {
        value = String(JSON.parse(raw)) // matter.py writes strings JSON-quoted
      } catch {
        // a hand-written YAML string keeps the stripped form
      }
    }
    out[kv[1]] = value === 'null' ? '' : value
  }
  return out
}

type Entry = {
  type?: string
  status?: string
  treatment?: { level?: string; manual_keycite?: { required?: boolean; done?: boolean } }
}

export function countLedger(ledgerText: string | undefined): Counts {
  const counts: Counts = {
    total: 0, retrieved: 0, candidates: 0, verified: 0, screened: 0, notValidated: 0,
    keycitePending: 0, secondaryRequested: 0, secondaryReported: 0,
  }
  if (!ledgerText) return counts
  let rows: Entry[] = []
  try {
    rows = (JSON.parse(ledgerText).authorities ?? []) as Entry[]
  } catch {
    return counts
  }
  for (const e of rows) {
    counts.total++
    if (e.type === 'secondary') {
      if (e.status === 'requested') counts.secondaryRequested++
      if (e.status === 'reported') counts.secondaryReported++
      continue
    }
    if (e.status === 'retrieved') counts.retrieved++
    if (e.status === 'candidate') counts.candidates++
    if (e.type === 'case' && e.status === 'retrieved') {
      const level = e.treatment?.level
      if (level === 'heavyweight') counts.verified++
      else if (level === 'lightweight') counts.screened++
      else counts.notValidated++
    }
    const mk = e.treatment?.manual_keycite
    if (e.status === 'retrieved' && mk?.required && !mk.done) counts.keycitePending++
  }
  return counts
}

/** True when the session's working directory is a research workspace (it holds research/). */
export async function isWorkspace($: EngineInterface): Promise<boolean> {
  try {
    return await $.fs.exists('research')
  } catch {
    return false
  }
}

export async function loadMatter($: EngineInterface): Promise<Matter | undefined> {
  const marker = (await readText($, '.session/active-matter'))?.trim()
  if (!marker) return undefined
  const path = marker.replace(/\\/g, '/').replace(/\/+$/, '')
  const q = frontMatter((await readText($, `${path}/question.md`)) ?? '')
  return {
    path,
    question: q.question || undefined,
    jurisdiction: q.jurisdiction || undefined,
    jurisdictionId: q.jurisdiction_id || slugJurisdiction(q.jurisdiction) || DEFAULT_JURISDICTION,
    audience: q.audience || undefined,
    closedUniverse: q.closed_universe === 'true',
    counts: countLedger(await readText($, `${path}/authorities.json`)),
  }
}

// ---------------------------------------------------------------- jurisdictions (plugins/legal-research/data)

export const DEFAULT_JURISDICTION = 'federal'

export type Jurisdiction = {
  id: string
  label: string
  binding: string[]
  federal: string[]
  statutes: string
  citation_mode: string
}

export function slugJurisdiction(label: string | undefined): string | undefined {
  if (!label) return undefined
  const s = label.toLowerCase().replace(/\(.*?\)/g, '').replace(/[^a-z]+/g, '-').replace(/^-|-$/g, '')
  return s || undefined
}

export function parseJurisdictions(text: string | undefined): Jurisdiction[] {
  try {
    return (JSON.parse(text ?? '{}').jurisdictions ?? []) as Jurisdiction[]
  } catch {
    return []
  }
}

export function findJurisdiction(list: Jurisdiction[], id: string | undefined): Jurisdiction | undefined {
  return list.find(j => j.id === (id ?? DEFAULT_JURISDICTION)) ?? list.find(j => j.id === DEFAULT_JURISDICTION)
}

/** The jurisdiction table; empty when it cannot be read, so the context block still goes out without a courts line. */
export async function loadJurisdictions($: EngineInterface): Promise<Jurisdiction[]> {
  try {
    return parseJurisdictions(await readText($, `${await scriptsDir($)}/../data/jurisdictions.json`))
  } catch {
    return []
  }
}

/** The context line that tells the research skills which court filter, statute source, and citation form to use. */
export function courtsLine(j: Jurisdiction | undefined): string | undefined {
  if (!j) return undefined
  const fed = j.federal.length > 12
    ? `${j.federal.length} federal district courts (ids in plugins/legal-research/data/jurisdictions.json; omit the court filter to search them all)`
    : j.federal.join(' ')
  const second = j.id === DEFAULT_JURISDICTION ? 'district courts' : 'federal courts sitting here (persuasive on state law)'
  return `Courts (CourtListener court filter): binding ${j.binding.join(' ')}; ${second}: ${fed}. Statutes: ${j.statutes}. ` +
    `Citation mode: ${j.citation_mode}.`
}

export function renderContext(matter: Matter | undefined, mode: Mode, jurisdiction?: Jurisdiction): string {
  const lines = ['[legal-workbench context]']
  if (!matter) {
    lines.push('Active matter: none. Retrievals land in .session/inbox/ until a matter is created or selected in the ' +
      'Home pane (/workbench).')
  } else {
    const c = matter.counts
    lines.push(`Active matter: ${matter.path}`)
    if (matter.question) lines.push(`Question: ${matter.question}`)
    lines.push(`Jurisdiction: ${jurisdiction?.label ?? matter.jurisdiction ?? 'Federal (all federal courts)'}; ` +
      `audience: ${matter.audience ?? 'not recorded'}; ` +
      `closed universe: ${matter.closedUniverse ? 'yes (authorities outside question.md universe are refused)' : 'no'}`)
    const courts = courtsLine(jurisdiction)
    if (courts) lines.push(courts)
    lines.push(`Ledger: ${c.total} entries, ${c.retrieved} retrieved, ${c.candidates} candidates; cases ` +
      `${c.verified} Verified, ${c.screened} Screened, ${c.notValidated} Not validated; ${c.keycitePending} awaiting ` +
      `manual KeyCite; secondary ${c.secondaryRequested} requested, ${c.secondaryReported} reported.`)
  }
  lines.push(`Mode: ${mode}${mode === 'free' ? ' (context only; the protocol reminder is advisory)' : ''}`)
  lines.push(PROTOCOL)
  return lines.join('\n')
}

export async function currentMode($: EngineInterface): Promise<Mode> {
  try {
    const stored = await $.store.get('mode')
    return (MODES as readonly string[]).includes(String(stored)) ? (stored as Mode) : 'research'
  } catch {
    return 'research'
  }
}

/** Checkbox progress in the matter's plan.md: done of total, for the spinner's "issue k of n". */
export function planProgress(planText: string | undefined): { done: number; total: number } {
  const boxes = (planText ?? '').match(/^\s*[-*] \[( |x|X)\]/gm) ?? []
  return { done: boxes.filter(b => /\[[xX]\]/.test(b)).length, total: boxes.length }
}

/** Ledger id to case name, for tool rows that only carry a cluster id. */
export async function ledgerNames($: EngineInterface, matterPath: string): Promise<Record<string, string>> {
  const text = await readText($, `${matterPath}/authorities.json`)
  const out: Record<string, string> = {}
  try {
    for (const e of (JSON.parse(text ?? '{}').authorities ?? []) as { id: string; citation?: { case_name?: string } }[]) {
      if (e.citation?.case_name) out[e.id] = e.citation.case_name
    }
  } catch {
    // an unreadable ledger leaves the rows with ids
  }
  return out
}

export async function readPlan($: EngineInterface, matterPath: string): Promise<string | undefined> {
  return readText($, `${matterPath}/plan.md`)
}

export function envToken(envText: string | undefined, name: string): string | undefined {
  for (const line of (envText ?? '').split(/\r?\n/)) {
    if (line.startsWith(`${name}=`)) return line.slice(name.length + 1).trim().replace(/^["']|["']$/g, '') || undefined
  }
  return undefined
}

export type QuotaLimit = { scope?: string; rate?: string; remaining?: number; limit?: number; window_seconds?: number }

/** The hourly user-scope limit from /api/rest/v4/api-usage/ (REST shape: a flat list tagged by scope). */
export function hourlyQuota(body: string): { remaining: number; limit: number; window: string } | null {
  try {
    const usage = JSON.parse(body).current_usage
    const limits: QuotaLimit[] = Array.isArray(usage) ? usage.filter((l: QuotaLimit) => l.scope === 'user') : usage?.user?.limits ?? []
    const hourly = limits.find(l => (l.window_seconds ?? 0) >= 3600) ?? limits[0]
    if (!hourly || typeof hourly.remaining !== 'number' || typeof hourly.limit !== 'number') return null
    return { remaining: hourly.remaining, limit: hourly.limit, window: String(hourly.rate ?? '').split('/')[1] ?? 'hour' }
  } catch {
    return null
  }
}

export async function fetchQuota($: EngineInterface): Promise<{ remaining: number; limit: number; window: string } | null> {
  const token = envToken(await readText($, '.env'), 'COURTLISTENER_API_TOKEN')
  if (!token) return null
  try {
    const res = await $.http.fetch('https://www.courtlistener.com/api/rest/v4/api-usage/', { headers: { Authorization: `Token ${token}` } })
    return res.ok ? hourlyQuota(res.text) : null
  } catch {
    return null
  }
}
