import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'
import { relayCard } from './rows.ts'
import { PANE, parseGate } from './workbench.tsx'

const DENY = JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny',
  permissionDecisionReason: 'Citation gate: Smith v. Jones, 1 Ga. 1 is not in the ledger.' } })

const MATTER = 'research/torts/proximate-cause-georgia'
const QUESTION = `---
question: "Test 2 fixture"
jurisdiction: Georgia
closed_universe: false
---
`
const LEDGER = JSON.stringify({
  authorities: [
    { id: 'cl-cluster-5749642', type: 'case', status: 'retrieved', local_path: 'sources/cl-cluster-5749642.md',
      citation: { case_name: 'Goldstein, Garber & Salama, LLC v. J.B.', court_id: 'ga', date_filed: '2017-03-06',
                  reporters: [{ volume: '300', reporter: 'Ga.', page: '840' }] },
      treatment: { level: 'lightweight', citing_count: 35, flags: [], manual_keycite: { required: true, done: false } } },
    { id: 'sec-SR-001', type: 'secondary', status: 'requested', request_id: 'SR-001',
      request: { issue: 'Intervening criminal acts and proximate cause',
                 searches: [{ label: 'search 1', method: 'Terms and connectors', content: 'Secondary Sources',
                              query: 'adv: "proximate cause" /s "intervening act" & georgia' }] } },
  ],
})
const FILES: Record<string, string> = {
  '.session/active-matter': MATTER, [`${MATTER}/question.md`]: QUESTION, [`${MATTER}/authorities.json`]: LEDGER,
}

// The engine hands fs hooks the path resolved against the working directory, so match by suffix.
function lookup(path: string, keys: readonly string[]): string | undefined {
  const p = path.replace(/\\/g, '/')
  return keys.find(k => p === k || p.endsWith(`/${k}`))
}

/** Stands for the host: a fake disk, the scripts' answer, and every process call the mod made. */
function host(on: On, stdout: string, exitCode = 0) {
  const calls: { argv: readonly string[]; stdin?: string }[] = []
  on('process.run', ($, e) => {
    calls.push({ argv: e.argv, stdin: e.init?.stdin as string | undefined })
    return { value: { exitCode, stdout, stderr: exitCode ? 'boom' : '', isStdoutTruncated: false, isStderrTruncated: false } as never }
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

describe('parseGate', () => {
  test('reads a deny', () => {
    expect(parseGate(DENY)).toContain('Smith v. Jones')
  })
  test('passes empty output and an allow', () => {
    expect(parseGate('')).toBeNull()
    expect(parseGate(JSON.stringify({ hookSpecificOutput: { permissionDecision: 'allow' } }))).toBeNull()
  })
})

describe('tool.call citation gate', () => {
  test('a denied draft write never reaches the tool', async ($, on) => {
    const calls = host(on, DENY)
    let wrote = false
    on('tool.call', { tool: 'Write' }, () => { wrote = true; return { result: 'written' as never } })
    const out = await $.tool.call({ tool: 'Write', file_path: `C:/repo/${MATTER}/drafts/memo.md`,
                                    content: 'See Smith v. Jones, 1 Ga. 1 (1846).' } as never)
    expect(wrote).toBe(false)
    expect(String(out.deny ?? out.text)).toContain('Smith v. Jones')
    expect(calls.length).toBe(1)
    expect(calls[0].argv.join(' ')).toContain('plugins/legal-research/scripts/cite_gate.py')
    const payload = JSON.parse(calls[0].stdin ?? '{}')
    expect(payload.hook_event_name).toBe('PreToolUse')
    expect(payload.tool_input.file_path).toBe(`C:/repo/${MATTER}/drafts/memo.md`)
  })

  test('an allowed write goes through', async ($, on) => {
    host(on, '')
    let wrote = false
    on('tool.call', { tool: 'Edit' }, () => { wrote = true; return { result: 'edited' as never } })
    const out = await $.tool.call({ tool: 'Edit', file_path: `C:/repo/${MATTER}/drafts/memo.md`,
                                    old_string: 'a', new_string: 'b' } as never)
    expect(wrote).toBe(true)
    expect(out.deny).toBeUndefined()
  })

  test('a write outside research/ skips the gate', async ($, on) => {
    const calls = host(on, DENY)
    on('tool.call', { tool: 'Write' }, () => ({ result: 'written' as never }))
    await $.tool.call({ tool: 'Write', file_path: 'C:/repo/docs/notes.md', content: 'Smith v. Jones, 1 Ga. 1' } as never)
    expect(calls.length).toBe(0)
  })

  test('a gate that fails to run blocks the write', async ($, on) => {
    host(on, '', 2)
    let wrote = false
    on('tool.call', { tool: 'Write' }, () => { wrote = true; return { result: 'written' as never } })
    const out = await $.tool.call({ tool: 'Write', file_path: `C:/repo/${MATTER}/drafts/memo.md`, content: 'x' } as never)
    expect(wrote).toBe(false)
    expect(String(out.deny ?? out.text)).toContain('Citation gate error (exit 2)')
  })
})

describe('commands', () => {
  test('/mode sets and reports the mode', async ($, on) => {
    host(on, '')
    expect((await $.command.run({ command: 'mode', args: 'draft' })).text).toBe('Mode set to draft.')
    expect((await $.command.run({ command: 'mode', args: 'loud' })).text).toContain('Mode is draft.')
  })

  test('/keycite runs the checklist for the active matter', async ($, on) => {
    const calls = host(on, '# KeyCite checklist\n- Goldstein')
    await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
    const out = await $.command.run({ command: 'keycite', args: '' })
    expect(out.text).toContain('KeyCite checklist')
    expect(calls.at(-1)!.argv.join(' ')).toContain(`keycite_checklist.py ${MATTER}`)
  })
})

describe('/secondary card', () => {
  const COMMAND = 'uv run --script "C:/repo/plugins/legal-research/scripts/ledger.py" secondary request research/torts/proximate-cause-georgia notes/sr-001-spec.json'
  test('relayCard reads the relay call and ignores other Bash calls', () => {
    const card = relayCard('Bash', { command: COMMAND }, 'SR-001 written to research/torts/proximate-cause-georgia/audit/secondary-requests.md and ledgered as sec-SR-001')
    expect(card?.action).toBe('request')
    expect(card?.requestId).toBe('SR-001')
    expect(card?.title).toBe('Westlaw request SR-001 written · run each search by hand')
    expect(relayCard('Bash', { command: 'git status' }, '')).toBeNull()
    expect(relayCard('Bash', { command: 'uv run ledger.py secondary list research/x' }, 'No secondary-source requests in this matter.')?.title)
      .toBe('Westlaw requests in this matter')
  })
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`draws the request card with Copy buttons on ${surface}`, async ($, on) => {
      host(on, '')
      await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
      const ui = await $.ui.mount({ plugin: 'legal-workbench', surface, component: 'ToolUse',
        props: { tool_use_id: 't9', tool: 'Bash', input: { command: COMMAND }, isRunning: false, isErrored: false,
                 isInterrupted: false, output: 'SR-001 written to research/torts/proximate-cause-georgia/audit/secondary-requests.md and ledgered as sec-SR-001' } as never })
      expect(await ui.find({ type: 'Text', text: /Westlaw request SR-001 written/ })).toBeDefined()
      expect(await ui.find({ key: 'card-search 1' })).toBeDefined()
      await ui.unmount()
    })
  }
})

describe('ledger polling', () => {
  test('a ledger change reaches the pane within two seconds', async ($, on) => {
    host(on, '')
    const clock = mock.clock(on)
    mock.env(on, {})
    let mtime = 1
    on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: mtime } as never }))
    on('command.register', () => ({ value: undefined as never }))
    on('session.start', ($, e) => ({ cwd: e.cwd }) as never)
    await $.session.start({ cwd: 'C:/repo', surface: 'terminal' } as never)
    const ui = await $.ui.mount({ plugin: 'legal-workbench', surface: 'terminal', component: 'Pane', requestId: PANE,
      props: { title: 'Authorities', isFocused: true, bodyColumns: 100 } as never })
    expect(await ui.find({ key: 'cl-cluster-1339729' })).toBeUndefined()
    const ledger = JSON.parse(FILES[`${MATTER}/authorities.json`])
    ledger.authorities.push({ id: 'cl-cluster-1339729', type: 'case', status: 'retrieved',
      citation: { case_name: 'Bradley Center, Inc. v. Wessner', court_id: 'ga', date_filed: '1982-10-26',
                  reporters: [{ volume: '250', reporter: 'Ga.', page: '199' }] }, treatment: { level: 'none' } })
    const before = FILES[`${MATTER}/authorities.json`]
    FILES[`${MATTER}/authorities.json`] = JSON.stringify(ledger)
    mtime = 2
    try {
      await clock.advance(2000)
      expect(await ui.find({ key: 'cl-cluster-1339729' })).toBeDefined()
    } finally {
      FILES[`${MATTER}/authorities.json`] = before
      await ui.unmount()
    }
  })
})

describe('Authorities pane', () => {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`lists authorities and pending Westlaw requests on ${surface}`, async ($, on) => {
      const calls = host(on, '')
      await $.command.run({ command: 'matter', args: 'switch torts/proximate-cause-georgia' })
      const ui = await $.ui.mount({ plugin: 'legal-workbench', surface, component: 'Pane', requestId: PANE,
        props: { title: 'Authorities', isFocused: true, bodyColumns: 100 } as never })
      expect(await ui.find({ type: 'Text', text: /1 authorities/ })).toBeDefined()
      expect(await ui.find({ key: 'cl-cluster-5749642' })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /Pending Westlaw requests \(1\)/ })).toBeDefined()
      expect(await ui.find({ key: 'sec-SR-001-search 1' })).toBeDefined()
      await ui.press({ key: 'cl-cluster-5749642' })
      expect(await ui.find({ type: 'Text', text: /Citing opinions: 35/ })).toBeDefined()
      expect(await ui.find({ key: 'validate' })).toBeDefined()
      await ui.press({ key: 'westlaw' })
      expect(calls.at(-1)?.argv).toEqual(['rundll32', 'url.dll,FileProtocolHandler',
        'https://a.next.westlaw.com/Link/Document/FullText?findType=Y&cite=300%20Ga.%20840'])
      await ui.press({ key: 'back' })
      expect(await ui.find({ key: 'cl-cluster-5749642' })).toBeDefined()
      await ui.unmount()
    })
  }
})
