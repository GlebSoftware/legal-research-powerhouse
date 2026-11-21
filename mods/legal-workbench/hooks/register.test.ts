import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'
import { SECTION_ID } from './register.tsx'

const MATTER = 'research/legal-writing/closed-memo-dram-shop'
const QUESTION = `---
question: "Phase 1 Test 1 fixture: closed-universe cite-check of a Georgia dram shop memo"
jurisdiction: Georgia
audience: Legal Writing memo
closed_universe: true
---
`
const LEDGER = JSON.stringify({
  authorities: [
    { id: 'cl-cluster-1266402', type: 'case', status: 'retrieved',
      treatment: { level: 'none', manual_keycite: { required: true, done: false } } },
    { id: 'gc-code-51-1-40', type: 'statute', status: 'retrieved', treatment: { level: 'none', manual_keycite: { required: false } } },
    { id: 'sec-SR-001', type: 'secondary', status: 'requested' },
  ],
})

// The engine hands fs hooks the path resolved against the working directory, so match by suffix.
function lookup(path: string, keys: readonly string[]): string | undefined {
  const p = path.replace(/\\/g, '/')
  return keys.find(k => p === k || p.endsWith(`/${k}`))
}

function disk(on: On, files: Record<string, string>, dirs: string[] = ['research']) {
  on('fs.read', ($, e) => {
    const k = lookup(e.path, Object.keys(files))
    return k === undefined ? { deny: `ENOENT: ${e.path}` } : { value: files[k] }
  })
  on('fs.exists', ($, e) => ({ value: lookup(e.path, [...Object.keys(files), ...dirs]) !== undefined }))
}

function capture(on: On) {
  const seen: { text: string; context?: readonly string[] }[] = []
  on('prompt.submit', ($, e) => {
    seen.push({ text: e.text, context: e.context })
    return { text: e.text, context: e.context }
  })
  return seen
}

describe('prompt.submit', () => {
  test('attaches the active matter and protocol to a plain prompt', async ($, on) => {
    disk(on, { '.session/active-matter': `${MATTER}\n`, [`${MATTER}/question.md`]: QUESTION, [`${MATTER}/authorities.json`]: LEDGER })
    mock.store(on)
    const seen = capture(on)
    await $.prompt.submit({ text: 'Is a bar liable when it did not know the patron would drive?' })
    expect(seen.length).toBe(1)
    expect(seen[0].text).toBe('Is a bar liable when it did not know the patron would drive?')
    const block = (seen[0].context ?? []).join('\n')
    expect(block).toContain(`Active matter: ${MATTER}`)
    expect(block).toContain('Jurisdiction: Georgia')
    expect(block).toContain('closed universe: yes')
    expect(block).toContain('3 entries, 2 retrieved, 0 candidates; cases 0 Verified, 0 Screened, 1 Not validated; 1 awaiting manual KeyCite; secondary 1 requested, 0 reported')
    expect(block).toContain('Mode: research')
    expect(block).toContain('CourtListener is disconnected, reconnect it before I proceed')
  })

  test('reads the stored mode', async ($, on) => {
    disk(on, { '.session/active-matter': MATTER, [`${MATTER}/question.md`]: QUESTION, [`${MATTER}/authorities.json`]: LEDGER })
    mock.store(on, { mode: 'draft' })
    const seen = capture(on)
    await $.prompt.submit({ text: 'Draft the rule section.' })
    expect((seen[0].context ?? []).join('\n')).toContain('Mode: draft')
  })

  test('says no matter is active when the marker is missing', async ($, on) => {
    disk(on, {})
    mock.store(on)
    const seen = capture(on)
    await $.prompt.submit({ text: 'What is the Georgia rule on proximate cause?' })
    expect((seen[0].context ?? []).join('\n')).toContain('Active matter: none')
  })

  test('adds nothing outside a research workspace', async ($, on) => {
    disk(on, {}, [])
    mock.store(on)
    const seen = capture(on)
    await $.prompt.submit({ text: 'hello' })
    expect(seen[0].context ?? []).toEqual([])
  })
})

describe('prompt.compose', () => {
  test('appends the protocol as a session section once', async ($, on) => {
    disk(on, {})
    on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'base', scope: 'shared' as const }] }))
    const out = await $.prompt.compose({ model: "claude-opus-5-5", promptModel: "claude-opus-5-5", surfaces: [], tools: [], outputStyle: null, traits: [] })
    const ids = out.sections.map(s => s.id)
    expect(ids).toEqual(['intro', SECTION_ID])
    expect(out.sections[1].scope).toBe('session')
  })

  test('leaves a bare prompt alone', async ($, on) => {
    disk(on, {})
    on('prompt.compose', () => ({ sections: [{ id: 'bare', text: 'one line', scope: 'shared' as const }] }))
    const out = await $.prompt.compose({ traits: ['bare'] })
    expect(out.sections.map(s => s.id)).toEqual(['bare'])
  })
})
