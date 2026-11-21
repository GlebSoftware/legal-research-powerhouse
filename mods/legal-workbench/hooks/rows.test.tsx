import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import { classify, countCitations, describeCall, describeResult } from './rows.ts'
import { hourlyQuota, planProgress } from './matter.ts'
import { bandLine, countsLine, statusText } from './register.tsx'

const CL = 'mcp__1f46847a-abd9-418f-a14c-92a14d0f7e1c__'
const SEARCH_OUT = [{ type: 'text', text: JSON.stringify({ query_id: 'q', count: 1, results: [{ caseName: 'Becks v. Pierce',
  citation: ['638 S.E.2d 390', '282 Ga. App. 229', '2006 Ga. App. LEXIS 1360'], cluster_id: 1266402, court_id: 'gactapp', dateFiled: '2006-11-02' }] }) }]
const READ_OUT = [{ type: 'text', text: JSON.stringify({ doc_type: 'opinion', doc_id: 1266402, total_chars: 29605,
  text: '<opinion><span class="star-pagination" label="230">*230</span></opinion>' }) }]
const GC_OUT = [{ type: 'text', text: '---\ntitle: O.C.G.A. § 51-1-40. Liability for acts of intoxicated persons.\ncollection: code\nid: 51-1-40\ncite_as: O.C.G.A. § 51-1-40 (2025)\ncurrent_through: Including Acts of the 2025 Regular Session of the General Assembly\n---\n\n# body' }]
const ECFR_OUT = [{ type: 'text', text: JSON.stringify({ system: 'ecfr', up_to_date_as_of: '2026-10-14', text: '§ 744.11 License requirements ...' }) }]

describe('classify', () => {
  test('sources by server and suffix', () => {
    expect(classify(`${CL}search`, {})).toBe('courtlistener')
    expect(classify('mcp__claude_ai_CourtListener__read_document', {})).toBe('courtlistener')
    expect(classify('mcp__georgiacommons__search', {})).toBe('georgiacommons')
    expect(classify('mcp__plugin_legal-research_uslaw__ecfr_section', {})).toBe('uslaw')
    expect(classify('Write', { file_path: 'C:\\repo\\research\\torts\\x\\drafts\\memo.md' })).toBe('draft')
    expect(classify('Write', { file_path: 'C:\\repo\\research\\torts\\x\\notes\\n.md' })).toBe(null)
    expect(classify('Bash', {})).toBe(null)
  })
})

describe('describeCall', () => {
  test('CourtListener search reads as a legal step with a count', () => {
    const row = describeCall(`${CL}search`, { q: 'caseName:"Becks v. Pierce"', court: ['ga', 'gactapp'] }, SEARCH_OUT)
    expect(row?.title).toBe('Searching CourtListener · "caseName:"Becks v. Pierce"" · court: ga, gactapp')
    expect(row?.detail).toBe('1 result')
  })
  test('read_document names the case from the ledger', () => {
    const row = describeCall(`${CL}read_document`, { cluster_id: 1266402 }, READ_OUT, { 'cl-cluster-1266402': 'Becks v. Pierce' })
    expect(row?.title).toBe('Reading Becks v. Pierce')
    expect(row?.detail).toBe('29,605 characters · saved to sources/')
  })
  test('Georgia Commons section shows cite and currency', () => {
    const row = describeCall('mcp__georgiacommons__code_lookup_section', { citation: 'O.C.G.A. § 51-1-40' }, GC_OUT)
    expect(row?.title).toBe('O.C.G.A. § 51-1-40 (2025)')
    expect(row?.detail).toContain('current through 2025 Regular Session')
  })
  test('eCFR section shows currency', () => {
    const row = describeCall('mcp__plugin_legal-research_uslaw__ecfr_section', { title: 15, section: '744.11' }, ECFR_OUT)
    expect(row?.title).toBe('15 C.F.R. § 744.11')
    expect(row?.detail).toBe('eCFR up to date as of 2026-10-14 · saved to sources/')
  })
  test('draft writes count citations', () => {
    const row = describeCall('Write', { file_path: '/r/research/a/b/drafts/memo.md',
      content: 'Becks v. Pierce, 282 Ga. App. 229, 234, 638 S.E.2d 390 (2006); O.C.G.A. § 51-1-40(b).' }, undefined)
    expect(row?.title).toBe('Draft updated · memo.md')
    expect(row?.detail).toBe('3 citations · cleared by the citation gate')
  })
  test('countCitations ignores repeats', () => {
    expect(countCitations('638 S.E.2d 390 and 638 S.E.2d 390')).toBe(1)
  })
})

describe('describeResult', () => {
  test('search results list cases without LEXIS cites or JSON', () => {
    expect(describeResult(`${CL}search`, null, SEARCH_OUT)).toEqual(['Becks v. Pierce, 638 S.E.2d 390, 282 Ga. App. 229 (gactapp 2006)'])
  })
  test('read results report pagination', () => {
    expect(describeResult(`${CL}read_document`, null, READ_OUT)).toEqual(['29,605 characters; star pagination present'])
  })
})

describe('status, band, spinner inputs', () => {
  const s = { matter: 'research/torts/x', jurisdiction: 'Georgia', closedUniverse: false, total: 24, verified: 2, screened: 5,
              notValidated: 1, keycitePending: 8, secondaryRequested: 1, planDone: 1, planTotal: 3 }
  const q = { remaining: 997, limit: 1000, window: 'hour', checkedAt: 0 }
  test('status line', () => {
    expect(statusText(s, q)).toBe('Matter: torts/x · 24 authorities · CL 997/1000 per hour')
  })
  test('band lines', () => {
    expect(bandLine(s, q, 'research')).toBe('torts/x · Georgia · mode research · CourtListener 997/1000 per hour')
    expect(countsLine(s)).toBe('Cases: 2 Verified · 5 Screened · 1 Not validated · 8 KeyCite pending · 1 Westlaw request pending')
  })
  test('plan progress', () => {
    expect(planProgress('- [x] a\n- [ ] b\n  - [ ] c')).toEqual({ done: 1, total: 3 })
  })
  test('quota from the REST usage shape', () => {
    const body = JSON.stringify({ current_usage: [{ scope: 'api_usage', rate: '10/min', remaining: 8, limit: 10, window_seconds: 60 },
      { scope: 'user', rate: '1000/hour', remaining: 997, limit: 1000, window_seconds: 3600 },
      { scope: 'user', rate: '20/min', remaining: 20, limit: 20, window_seconds: 60 }] })
    expect(hourlyQuota(body)).toEqual({ remaining: 997, limit: 1000, window: 'hour' })
  })
})

function quiet(on: On) {
  on('fs.exists', () => ({ value: false }))
  on('fs.read', ($, e) => ({ deny: `ENOENT: ${e.path}` }))
  mock.store(on)
}

describe('rendered rows validate on both surfaces', () => {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`ToolUse on ${surface}`, async ($, on) => {
      quiet(on)
      const ui = await $.ui.mount({ plugin: 'legal-workbench', surface, component: 'ToolUse',
        props: { tool_use_id: 't1', tool: `${CL}search`, input: { q: 'dram shop', court: 'gactapp' }, isRunning: false,
                 isErrored: false, isInterrupted: false, output: SEARCH_OUT } })
      expect((await ui.find({ type: 'Text', text: /Searching CourtListener/ }))?.text).toContain('court: gactapp')
      expect(await ui.find({ type: 'Text', text: /query_id/ })).toBeUndefined()
    })
    test(`ToolResult on ${surface}`, async ($, on) => {
      quiet(on)
      const ui = await $.ui.mount({ plugin: 'legal-workbench', surface, component: 'ToolResult',
        props: { tool_use_id: 't1', tool: `${CL}search`, output: SEARCH_OUT, isErrored: false } })
      expect((await ui.find({ type: 'Text', text: /Becks v\. Pierce/ }))?.text).toContain('(gactapp 2006)')
    })
  }
})
