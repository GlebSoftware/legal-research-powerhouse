// Ledger rows for the Authorities pane (H2). Pure: parses authorities.json text.
import type { LegalWorkbenchRow } from '../types'

type Entry = {
  id: string
  type?: string
  status?: string
  local_path?: string | null
  request_id?: string
  disclosure?: string | null
  citation?: { case_name?: string; reporters?: { volume: string; reporter: string; page: string }[]; cite_as?: string;
               bluebook?: string | null; court_id?: string; date_filed?: string }
  treatment?: { level?: string; verdict?: string | null; citing_count?: number | null; flags?: unknown[];
                manual_keycite?: { required?: boolean; done?: boolean; result?: string | null } }
  request?: { issue?: string; searches?: { label: string; method: string; content?: string; query?: string; path?: string }[] }
}

export function label(e: Entry): string {
  if (e.type === 'secondary') return e.disclosure ?? (e.status === 'requested' ? 'Westlaw request pending' : 'Not reported')
  if (e.type !== 'case') return 'n/a'
  return e.treatment?.level === 'heavyweight' ? 'Verified' : e.treatment?.level === 'lightweight' ? 'Screened' : 'Not validated'
}

export function cite(e: Entry): string {
  const c = e.citation ?? {}
  if (e.type === 'case') {
    const reps = (c.reporters ?? []).filter(r => !/LEXIS|Fulton County/.test(r.reporter)).map(r => `${r.volume} ${r.reporter} ${r.page}`)
    return `${reps.join(', ') || 'no reporter cite'} (${c.court_id ?? '?'} ${(c.date_filed ?? '').slice(0, 4)})`
  }
  if (e.type === 'secondary') return c.bluebook ?? e.request?.issue ?? e.id
  return c.cite_as ?? e.id
}

// Westlaw's find-by-citation link, as Cornell LII's "Read It Online" tool builds it
// (law.cornell.edu/rio, sources.js, fetched 2026-10-17). It opens the document, with its KeyCite flag, after sign-in.
export const WESTLAW_FIND = 'https://a.next.westlaw.com/Link/Document/FullText?findType=Y&cite='

/** The citation Westlaw resolves best: the first official or regional reporter for a case, the code cite for a statute. */
export function westlawCite(e: Entry): string | null {
  const c = e.citation ?? {}
  if (e.type === 'case') {
    const r = (c.reporters ?? []).find(x => !/LEXIS|WL|Fulton County|U\.S\.L\.W\./.test(x.reporter))
    return r ? `${r.volume} ${r.reporter} ${r.page}` : null
  }
  if (e.type === 'secondary') return null
  return c.cite_as ? c.cite_as.replace(/\s*\(\d{4}\)\s*$/, '') : null
}

export function westlawUrl(e: Entry): string | null {
  const cite = westlawCite(e)
  return cite ? WESTLAW_FIND + encodeURIComponent(cite) : null
}

export function rows(ledgerText: string | undefined, includeCandidates = false): LegalWorkbenchRow[] {
  let list: Entry[] = []
  try {
    list = (JSON.parse(ledgerText ?? '{}').authorities ?? []) as Entry[]
  } catch {
    return []
  }
  return list
    .filter(e => includeCandidates || e.status !== 'candidate')
    .map(e => {
      const mk = e.treatment?.manual_keycite
      return {
        id: e.id,
        type: e.type ?? 'unknown',
        status: e.status ?? 'unknown',
        name: e.type === 'case' ? (e.citation?.case_name ?? e.id) : e.type === 'secondary' ? (e.request_id ?? e.id) : (e.citation?.cite_as ?? e.id),
        cite: cite(e),
        label: label(e),
        keycite: mk?.done ? `done: ${mk.result ?? ''}` : mk?.required ? 'pending' : 'n/a',
        citingCount: e.treatment?.citing_count ?? null,
        flags: Array.isArray(e.treatment?.flags) ? e.treatment!.flags!.length : 0,
        verdict: e.treatment?.verdict ?? null,
        localPath: e.local_path ?? null,
        requestId: e.request_id ?? null,
        searches: e.request?.searches ?? [],
        westlaw: westlawUrl(e),
      }
    })
}

/** Short display name: the case name trimmed, or the id. */
export function shortName(name: string, n = 48): string {
  const t = name.replace(/\s+/g, ' ').trim()
  return t.length > n ? `${t.slice(0, n - 1)}…` : t
}
