import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'
import { SOURCES_PANE, parseSources, readable } from './sources.tsx'

const MATTER = 'research/torts/proximate-cause-georgia'
const QUESTION = `---
question: "Test 2 fixture"
jurisdiction: Georgia
closed_universe: false
---
`
const STATUS = JSON.stringify([
  { id: 'cl-cluster-5749642', path: 'sources/cl-cluster-5749642.html', system: 'courtlistener',
    retrieved_at: '2026-10-16T18:02:11Z', bytes: 41210, status: 'ok' },
  { id: 'gc-code-51-12-9', path: 'sources/gc-code-51-12-9.md', system: 'georgiacommons',
    retrieved_at: '2026-10-16T17:40:03Z', bytes: 1880, status: 'CHANGED' },
])
const FILES: Record<string, string> = {
  '.session/active-matter': MATTER,
  [`${MATTER}/question.md`]: QUESTION,
  [`${MATTER}/authorities.json`]: '{"authorities": []}',
  [`${MATTER}/sources/cl-cluster-5749642.html`]: '<div><p>As this Court has stated, when a defendant claims<span class="star-pagination" label="842">*842</span> that its negligence</p></div>',
  [`${MATTER}/audit/cite-check.html`]: '<html></html>',
}

function lookup(path: string, keys: readonly string[]): string | undefined {
  const p = path.replace(/\\/g, '/')
  return keys.find(k => p === k || p.endsWith(`/${k}`))
}

function host(on: On, answers: Record<string, { stdout: string; exitCode?: number }>) {
  const calls: string[] = []
  on('process.run', ($, e) => {
    const argv = e.argv.join(' ')
    calls.push(argv)
    const hit = Object.entries(answers).find(([script]) => argv.includes(script))
    return { value: { exitCode: hit?.[1].exitCode ?? 0, stdout: hit?.[1].stdout ?? '', stderr: '',
                      isStdoutTruncated: false, isStderrTruncated: false } as never }
  })
  on('session.cwd', () => ({ value: 'C:/repo' }))
  on('fs.exists', ($, e) => ({ value: lookup(e.path, [...Object.keys(FILES), 'research']) !== undefined }))
  on('fs.read', ($, e) => {
    const k = lookup(e.path, Object.keys(FILES))
    return k === undefined ? { deny: `ENOENT: ${e.path}` } : { value: FILES[k] }
  })
  mock.store(on)
  return calls
}

describe('pure helpers', () => {
  test('readable strips CourtListener markup', () => {
    const t = readable('sources/x.html', FILES[`${MATTER}/sources/cl-cluster-5749642.html`])
    expect(t).toContain('when a defendant claims*842 that its negligence')
    expect(t).not.toContain('<')
  })
  test('readable leaves Markdown alone', () => {
    expect(readable('sources/x.md', '# O.C.G.A. 51-12-9')).toBe('# O.C.G.A. 51-12-9')
  })
  test('parseSources tolerates junk', () => {
    expect(parseSources('not json')).toEqual([])
    expect(parseSources(STATUS).length).toBe(2)
  })
})

describe('/sources and /review', () => {
  test('/sources reports the hash check', async ($, on) => {
    const calls = host(on, { 'sources_status.py': { stdout: STATUS, exitCode: 1 } })
    on('ui.open', () => ({ value: { isPlaced: true } as never }))
    await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
    const out = await $.command.run({ command: 'sources', args: '' })
    expect(out.text).toBe('2 saved sources, 1 changed or missing.')
    expect(calls.some(c => c.includes(`sources_status.py ${MATTER} --json`))).toBe(true)
  })

  test('/review runs the audit with --html and opens the page', async ($, on) => {
    const calls = host(on, { 'cite_audit.py': { stdout: 'drafts/memo.md: 0 red, 3 yellow', exitCode: 0 } })
    await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
    const out = await $.command.run({ command: 'review', args: '' })
    expect(out.text).toContain('0 red, 3 yellow')
    expect(out.text).toContain('No unwaived red items.')
    expect(calls.some(c => c.includes(`cite_audit.py ${MATTER} --html`))).toBe(true)
    expect(calls.some(c => c.startsWith('cmd /c start') && c.includes('cite-check.html'))).toBe(true)
  })
})

describe('Sources pane', () => {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`lists sources and shows a document on ${surface}`, async ($, on) => {
      host(on, { 'sources_status.py': { stdout: STATUS, exitCode: 1 } })
      on('ui.open', () => ({ value: { isPlaced: true } as never }))
      await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
      await $.command.run({ command: 'sources', args: '' })
      const ui = await $.ui.mount({ plugin: 'legal-workbench', surface, component: 'Pane', requestId: SOURCES_PANE,
        props: { title: 'Sources', isFocused: true, bodyColumns: 100 } as never })
      expect(await ui.find({ type: 'Text', text: /2 saved sources · 1 changed or missing/ })).toBeDefined()
      await ui.press({ key: 'src:sources/cl-cluster-5749642.html' })
      expect(await ui.find({ key: 'src-text' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /hash ok/ })).toBeDefined()
      await ui.press({ key: 'src-back' })
      expect(await ui.find({ key: 'src:sources/gc-code-51-12-9.md' })).toBeDefined()
      await ui.unmount()
    })
  }
})
