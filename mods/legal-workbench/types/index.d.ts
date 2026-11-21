// legal-workbench state contract: values the band, status line, and panes read.
export type LegalWorkbenchQuota = { remaining: number; limit: number; window: string; checkedAt: number }

export type LegalWorkbenchSummary = {
  matter: string | null
  jurisdiction: string | null
  jurisdictionId?: string | null
  question?: string | null
  closedUniverse: boolean
  total: number
  verified: number
  screened: number
  notValidated: number
  keycitePending: number
  secondaryRequested: number
  planDone: number
  planTotal: number
}

export type LegalWorkbenchSearch = { label: string; method: string; content?: string; query?: string; path?: string }

export type LegalWorkbenchRow = {
  id: string
  type: string
  status: string
  name: string
  cite: string
  label: string
  keycite: string
  citingCount: number | null
  flags: number
  verdict: string | null
  localPath: string | null
  requestId: string | null
  searches: LegalWorkbenchSearch[]
  /** Westlaw find-by-citation link for the user's manual KeyCite; null when the entry has no usable citation. */
  westlaw?: string | null
}

/** One saved document, as sources_status.py --json reports it (hash checked against sources/manifest.jsonl). */
export type LegalWorkbenchSource = {
  id: string | null
  path: string
  system: string | null
  retrieved_at: string | null
  bytes: number | null
  status: 'ok' | 'CHANGED' | 'missing'
}

/** One matter folder, research/<course>/<name>/, as the Home pane lists it. */
export type LegalWorkbenchMatterRow = {
  path: string
  course: string
  name: string
  question: string | null
  jurisdiction: string
  active: boolean
}

/** The Home pane's new-matter form, field by field as typed. */
export type LegalWorkbenchNewMatter = { course: string; name: string; question: string; jurisdiction: string }

/** A Select option for the jurisdiction picker (data/jurisdictions.json). */
export type LegalWorkbenchChoice = { id: string; label: string }

/** One draft in drafts/, with the last audit's counts. */
export type LegalWorkbenchDraft = { path: string; name: string; red: number | null; yellow: number | null }

/** The Westlaw report-back form for one pending request (docs/05-secondary-sources.md section 4). */
export type LegalWorkbenchReport = {
  requestId: string
  citation: string
  pin: string
  summary: string
  quote1: string
  quote1Pin: string
  quote2: string
  quote2Pin: string
  pointsTo: string
  keycite: string
}

declare module 'claude-code' {
  interface PluginState {
    'legal-workbench': {
      quota: LegalWorkbenchQuota | null
      summary: LegalWorkbenchSummary | null
      rows: LegalWorkbenchRow[]
      selected: string | null
      ledgerStamp: number
      sources: LegalWorkbenchSource[]
      sourceSelected: string | null
      matters: LegalWorkbenchMatterRow[]
      newMatter: LegalWorkbenchNewMatter
      jurisdictions: LegalWorkbenchChoice[]
      homeMessage: string | null
      drafts: LegalWorkbenchDraft[]
      draftSelected: string | null
      report: LegalWorkbenchReport | null
      reportMessage: string | null
    }
  }
}
