import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'
import { DRAFTS, HOME, REPORT, auditCounts, newMatterProblem, reportJson } from './home.tsx'
import { courtsLine, findJurisdiction, parseJurisdictions, renderContext } from './matter.ts'

const MATTER = 'research/torts/proximate-cause-georgia'
const JURIS = JSON.stringify({
  default: 'federal',
  jurisdictions: [
    { id: 'federal', label: 'Federal (all federal courts)', binding: ['scotus', 'ca1', 'ca11', 'cadc'],
      federal: Array.from({ length: 20 }, (_, i) => `d${i}`), statutes: 'uslaw-mcp', citation_mode: 'academic' },
    { id: 'georgia', label: 'Georgia', binding: ['ga', 'gactapp'], federal: ['ca11', 'gamd', 'gand', 'gasd'],
      statutes: 'Georgia Commons', citation_mode: 'ga' },
  ],
})
const QUESTION_GA = '---\nquestion: "What is the Georgia proximate cause standard?"\njurisdiction: "Georgia"\njurisdiction_id: georgia\n' +
  'audience: "Legal Writing memo"\nclosed_universe: false\n---\n'
const QUESTION_PLAIN = '---\nquestion: "Is a bar liable?"\naudience: Legal Writing memo\nclosed_universe: false\n---\n'
const LEDGER = JSON.stringify({ authorities: [
  { id: 'cl-cluster-5749642', type: 'case', status: 'retrieved', treatment: { level: 'heavyweight', manual_keycite: { required: true, done: false } } },
  { id: 'sec-SR-001', type: 'secondary', status: 'requested', request_id: 'SR-001', request: { issue: 'Intervening acts', searches: [] } },
] })
const AUDIT = JSON.stringify({ drafts: [{ path: 'drafts/issue-3.md', items: [
  { severity: 'red', waived: false }, { severity: 'yellow', waived: false }, { severity: 'yellow', waived: true }] }] })

function lookup(path: string, keys: readonly string[]): string | undefined {
  const p = path.replace(/\\/g, '/')
  return keys.find(k => p === k || p.endsWith(`/${k}`))
}

function host(on: On, files: Record<string, string>, dirs: Record<string, { name: string; kind: string }[]> = {}) {
  const calls: string[] = []
  const writes: Record<string, string> = {}
  on('process.run', ($, e) => {
    calls.push(e.argv.join(' '))
    const argv = e.argv.join(' ')
    const stdout = argv.includes('matter.py new') ? 'Created and switched to research/contracts/offer-acceptance'
      : argv.includes('matter.py set') ? 'jurisdiction set: Georgia'
      : argv.includes('secondary ingest') ? 'SR-001 reported' : ''
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } as never }
  })
  on('session.cwd', () => ({ value: 'C:/repo' }))
  on('fs.exists', ($, e) => ({ value: lookup(e.path, [...Object.keys(files), 'research']) !== undefined }))
  on('fs.read', ($, e) => {
    const k = lookup(e.path, Object.keys(files))
    return k === undefined ? { deny: `ENOENT: ${e.path}` } : { value: files[k] }
  })
  on('fs.list', ($, e) => {
    const k = lookup(e.path, Object.keys(dirs))
    return k === undefined ? { deny: `ENOENT: ${e.path}` } : { value: dirs[k].map(d => ({ ...d, size: 0, mtimeMs: 0, isLink: false })) as never }
  })
  on('fs.write', ($, e) => {
    writes[e.path.replace(/\\/g, '/')] = e.text
    return { value: undefined as never }
  })
  on('ui.open', () => ({ value: { isPlaced: true } as never }))
  mock.store(on)
  mock.clock(on)
  return { calls, writes }
}

const FILES = {
  '.session/active-matter': MATTER, [`${MATTER}/question.md`]: QUESTION_GA, [`${MATTER}/authorities.json`]: LEDGER,
  [`${MATTER}/audit/cite-check.json`]: AUDIT, [`${MATTER}/drafts/issue-3.md`]: '# Issue 3\n\nThe rule. [[src:cl-cluster-5749642 841]].',
  'plugins/legal-research/data/jurisdictions.json': JURIS,
}
const DIRS = {
  research: [{ name: 'torts', kind: 'directory' }],
  'research/torts': [{ name: 'proximate-cause-georgia', kind: 'directory' }],
  [`${MATTER}/drafts`]: [{ name: 'issue-3.md', kind: 'file' }],
}

describe('jurisdiction context', () => {
  const list = parseJurisdictions(JURIS)
  test('an unset jurisdiction reads as Federal', () => {
    const j = findJurisdiction(list, undefined)
    expect(j?.id).toBe('federal')
    expect(courtsLine(j)).toContain('binding scotus ca1 ca11 cadc; district courts: 20 federal district courts')
  })
  test('Georgia names its courts, statutes, and citation mode', () => {
    const line = courtsLine(findJurisdiction(list, 'georgia')) ?? ''
    expect(line).toContain('binding ga gactapp; federal courts sitting here (persuasive on state law): ca11 gamd gand gasd')
    expect(line).toContain('Citation mode: ga')
  })
  test('the context block carries the label and the courts line', () => {
    const m = { path: MATTER, jurisdictionId: 'federal', closedUniverse: false,
      counts: { total: 0, retrieved: 0, candidates: 0, verified: 0, screened: 0, notValidated: 0, keycitePending: 0,
                secondaryRequested: 0, secondaryReported: 0 } }
    const block = renderContext(m, 'research', findJurisdiction(list, 'federal'))
    expect(block).toContain('Jurisdiction: Federal (all federal courts)')
    expect(block).toContain('Courts (CourtListener court filter): binding scotus')
  })
})

describe('pure helpers', () => {
  test('auditCounts skips waived items', () => {
    expect(auditCounts(AUDIT)['drafts/issue-3.md']).toEqual({ red: 1, yellow: 1 })
    expect(auditCounts('not json')).toEqual({})
  })
  test('newMatterProblem names the missing field', () => {
    expect(newMatterProblem({ course: '', name: 'x', question: 'q', jurisdiction: 'federal' })).toContain('course')
    expect(newMatterProblem({ course: 'torts', name: 'x', question: ' ', jurisdiction: 'federal' })).toContain('question')
    expect(newMatterProblem({ course: 'torts', name: 'x', question: 'q?', jurisdiction: 'federal' })).toBeNull()
  })
  test('reportJson builds the relay report and refuses an empty summary', () => {
    const base = { requestId: 'SR-001', citation: 'Restatement (Second) of Torts § 448 (1965)', pin: 'cmt. b', summary: '',
      quote1: 'The act of a third person', quote1Pin: '', quote2: '', quote2Pin: '', pointsTo: '250 Ga. 199; 300 Ga. 840', keycite: '' }
    expect(reportJson(base, '2026-10-16').problem).toContain('summary')
    const ok = reportJson({ ...base, summary: 'One. Two.' }, '2026-10-16')
    expect(ok.problem).toBeNull()
    const body = JSON.parse(ok.json)
    expect(body.points_to).toEqual(['250 Ga. 199', '300 Ga. 840'])
    expect(body.quotes).toEqual([{ text: 'The act of a third person', pin: 'cmt. b' }])
    expect(body.system).toBe('westlaw-manual')
  })
})

describe('Home pane', () => {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`shows the matter, pickers, waiting items, and matter list on ${surface}`, async ($, on) => {
      host(on, FILES, DIRS)
      await $.command.run({ command: 'workbench', args: '' })
      const ui = await $.ui.mount({ plugin: 'legal-workbench', surface, component: 'Pane', requestId: HOME,
        props: { title: 'Home', isFocused: true, bodyColumns: 100 } as never })
      expect(await ui.find({ type: 'Text', text: /Matter: torts\/proximate-cause-georgia/ })).toBeDefined()
      expect(await ui.find({ key: 'home-jurisdiction' })).toBeDefined()
      expect(await ui.find({ key: 'home-mode' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /1 authorities need your KeyCite check/ })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /1 Westlaw request\(s\) waiting for your report/ })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /1 draft\(s\), 1 red citation item/ })).toBeDefined()
      expect(await ui.find({ key: `matter:${MATTER}` })).toBeDefined()
      expect(await ui.find({ key: 'new-create' })).toBeDefined()
      await ui.unmount()
    })
  }

  test('the new-matter form runs matter.py new with the typed fields', async ($, on) => {
    const { calls } = host(on, FILES, DIRS)
    await $.command.run({ command: 'workbench', args: '' })
    const ui = await $.ui.mount({ plugin: 'legal-workbench', surface: 'terminal', component: 'Pane', requestId: HOME,
      props: { title: 'Home', isFocused: true, bodyColumns: 100 } as never })
    await ui.press({ key: 'new-create' })
    expect(await ui.find({ type: 'Text', text: /Type a course/ })).toBeDefined()
    await ui.input({ key: 'new-course', text: 'contracts', kind: 'change' })
    await ui.input({ key: 'new-name', text: 'offer acceptance', kind: 'change' })
    await ui.input({ key: 'new-question', text: 'Is a reply with new terms an acceptance?', kind: 'change' })
    await ui.press({ key: 'new-create' })
    const run = calls.find(c => c.includes('matter.py new')) ?? ''
    expect(run).toContain('matter.py new contracts offer acceptance --question Is a reply with new terms an acceptance? --jurisdiction federal')
    expect(await ui.find({ type: 'Text', text: /Created and switched to research\/contracts\/offer-acceptance/ })).toBeDefined()
    await ui.unmount()
  })

  test('the jurisdiction and mode pickers write the settings', async ($, on) => {
    const { calls } = host(on, { ...FILES, [`${MATTER}/question.md`]: QUESTION_PLAIN }, DIRS)
    await $.command.run({ command: 'workbench', args: '' })
    const ui = await $.ui.mount({ plugin: 'legal-workbench', surface: 'desktop', component: 'Pane', requestId: HOME,
      props: { title: 'Home', isFocused: true, bodyColumns: 100 } as never })
    await ui.select({ key: 'home-jurisdiction', value: 'georgia' })
    expect(calls.some(c => c.includes(`matter.py set ${MATTER} jurisdiction=georgia`))).toBe(true)
    await ui.select({ key: 'home-mode', value: 'draft' })
    expect(await ui.find({ type: 'Text', text: /Mode set to Draft/ })).toBeDefined()
    await ui.unmount()
  })
})

describe('Drafts pane', () => {
  test('lists drafts with audit counts and makes the Word file', async ($, on) => {
    const { calls } = host(on, FILES, DIRS)
    await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
    await $.command.run({ command: 'drafts', args: '' })
    const ui = await $.ui.mount({ plugin: 'legal-workbench', surface: 'terminal', component: 'Pane', requestId: DRAFTS,
      props: { title: 'Drafts', isFocused: true, bodyColumns: 100 } as never })
    expect(await ui.find({ type: 'Text', text: /1 red · 1 yellow/ })).toBeDefined()
    await ui.press({ key: 'draft:drafts/issue-3.md' })
    expect(await ui.find({ key: 'draft-text' })).toBeDefined()
    await ui.press({ key: 'draft-word' })
    expect(calls.some(c => c.includes(`render_memo.py ${MATTER} drafts/issue-3.md`))).toBe(true)
    expect(calls.some(c => c.startsWith('cmd /c start') && c.includes('issue-3.docx'))).toBe(true)
    await ui.unmount()
  })
})

describe('Westlaw report form', () => {
  test('writes the report file and runs the relay ingest', async ($, on) => {
    const { calls, writes } = host(on, FILES, DIRS)
    await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
    const authorities = await $.ui.mount({ plugin: 'legal-workbench', surface: 'terminal', component: 'Pane', requestId: 'authorities',
      props: { title: 'Authorities', isFocused: true, bodyColumns: 100 } as never })
    await authorities.press({ key: 'sec-SR-001-report' })
    await authorities.unmount()
    const ui = await $.ui.mount({ plugin: 'legal-workbench', surface: 'terminal', component: 'Pane', requestId: REPORT,
      props: { title: 'Westlaw report: SR-001', isFocused: true, bodyColumns: 100 } as never })
    await ui.input({ key: 'report-citation', text: 'Restatement (Second) of Torts § 448 (1965)', kind: 'change' })
    await ui.input({ key: 'report-pin', text: 'cmt. b', kind: 'change' })
    await ui.press({ key: 'report-submit' })
    expect(await ui.find({ type: 'Text', text: /two-to-six-sentence summary/ })).toBeDefined()
    await ui.input({ key: 'report-summary', text: 'Section 448 makes a crime superseding. Foreseeability is the exception.', kind: 'change' })
    await ui.press({ key: 'report-submit' })
    const file = Object.keys(writes).find(k => k.endsWith('audit/secondary-reports/SR-001.json')) ?? ''
    expect(JSON.parse(writes[file]).pin).toBe('cmt. b')
    expect(calls.some(c => c.includes(`ledger.py secondary ingest ${MATTER} SR-001`))).toBe(true)
    expect((await ui.find({ type: 'Text', text: /SR-001 recorded/ }))).toBeDefined()
    await ui.unmount()
  })
})
