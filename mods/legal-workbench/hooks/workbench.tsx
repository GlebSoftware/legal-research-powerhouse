// legal-workbench H2 (docs/04-harness.md 5.3): the tool.call citation gate, the Authorities pane with pending
// Westlaw requests, ledger polling, and the /matter, /mode, /authorities, /keycite commands.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'
import type { LegalWorkbenchRow, LegalWorkbenchSummary } from '../types'
import { MODES, currentMode, isWorkspace } from './matter.ts'
import { shortName } from './ledger.ts'
import { relayCard } from './rows.ts'
import { scriptPath } from './paths.ts'
import { HOME, open, openReport } from './home.tsx'
import { pollLedger, refreshRows, refreshSummary } from './state.ts'

const summary = atom({ plugin: 'legal-workbench', key: 'summary' } as const, null as LegalWorkbenchSummary | null)
const rows = atom({ plugin: 'legal-workbench', key: 'rows' } as const, [] as LegalWorkbenchRow[])
const selected = atom({ plugin: 'legal-workbench', key: 'selected' } as const, null as string | null)
const ledgerStamp = atom({ plugin: 'legal-workbench', key: 'ledgerStamp' } as const, 0)

export const PANE = 'authorities'
const POLL_MS = 2000
const GATED = ['Write', 'Edit', 'MultiEdit'] as const


function underResearch(filePath: string): boolean {
  return /(^|[\\/])research[\\/]/.test(filePath)
}

/** The gate's verdict for one write: the deny reason, or null to let it through. */
export function parseGate(stdout: string): string | null {
  const t = stdout.trim()
  if (!t) return null
  const out = JSON.parse(t)
  const h = out.hookSpecificOutput ?? {}
  return h.permissionDecision === 'deny' ? String(h.permissionDecisionReason ?? 'Citation gate denied the write.') : null
}

async function runScript($: EngineInterface, name: string, args: string[], stdin?: string) {
  const cwd = await $.session.cwd()
  return $.process.run(['uv', 'run', '--quiet', '--script', await scriptPath($, name), ...args],
    { cwd, stdin, timeoutMs: 120_000, env: { CLAUDE_PROJECT_DIR: cwd } })
}

/** Hand a URL to Windows' default browser. rundll32 takes it as one argument, so the & in a query string survives
 * (cmd /c start would split the line at it). The browser opens the page for the user; nothing here reads it back. */
export function openUrl($: EngineInterface, url: string) {
  if (!/^https:\/\//.test(url)) return Promise.resolve(undefined)
  return $.process.run(['rundll32', 'url.dll,FileProtocolHandler', url])
}

async function matterPath($: EngineInterface): Promise<string | null> {
  return (await read($, summary))?.matter ?? null
}

/** H2 startup, called from register.tsx's one session.start hook: commands, first ledger read, polling. */
export async function workbenchStart($: EngineInterface): Promise<void> {
  if (!(await isWorkspace($))) return
  for (const [name, description] of [
    ['matter', 'List research matters or switch: /matter [switch <path>]; create matters in the Home pane'],
    ['mode', 'Set the research mode: /mode research | draft | cite | free'],
    ['authorities', 'Open the Authorities pane for the active matter'],
    ['keycite', 'Write and show the KeyCite and Shepard’s checklist for the active matter'],
  ] as const) {
    await $.command.register({ name, description })
  }
  const s = await refreshSummary($)
  await refreshRows($, s?.matter ?? null)
  let last = 0
  $.clock.every(POLL_MS, () => {
    void (async () => {
      last = await pollLedger($, await matterPath($), last)
    })()
  })
}

export function registerWorkbench(on: On): void {
  // ------------------------------------------------------------ tool.call citation gate (same script as the shell hook)
  for (const tool of GATED) {
    on('tool.call', { tool }, async ($, e, next) => {
      const input = e as unknown as Record<string, unknown>
      const filePath = String(input.file_path ?? '')
      if (!underResearch(filePath)) return next(e)
      const cwd = await $.session.cwd()
      const payload = {
        hook_event_name: 'PreToolUse', tool_name: tool, cwd,
        tool_input: { file_path: filePath, content: input.content, old_string: input.old_string, new_string: input.new_string,
                      replace_all: input.replace_all, edits: input.edits },
      }
      const ran = await runScript($, 'cite_gate.py', [], JSON.stringify(payload))
      const reason = ran.exitCode === 0 ? parseGate(ran.stdout) : `Citation gate error (exit ${ran.exitCode}): ${ran.stderr.slice(0, 300)}`
      if (reason) return { deny: reason }
      const result = await next(e)
      const m = await matterPath($)
      if (m) await refreshRows($, m)
      return result
    }).catch(($, e, next) => {
      const filePath = String((e as unknown as Record<string, unknown>).file_path ?? '')
      if (!underResearch(filePath)) return next(e)
      return next.called ? next(e) : { deny: 'legal-workbench: the citation gate could not run, so this write under research/ is blocked.' }
    })
  }

  // ------------------------------------------------------------ commands
  on('command.run', { command: 'mode' }, async ($, e) => {
    const want = e.args.trim().toLowerCase()
    if (!(MODES as readonly string[]).includes(want)) {
      return { text: `Mode is ${await currentMode($)}. Choose one of: ${MODES.join(', ')}.` }
    }
    await $.store.set('mode', want)
    return { text: `Mode set to ${want}.` }
  })

  on('command.run', { command: 'matter' }, async ($, e) => {
    const [verb, ...rest] = e.args.trim().split(/\s+/)
    const arg = rest.join(' ')
    if (verb === 'switch' && arg) {
      const r = await runScript($, 'ledger.py', ['use', arg.startsWith('research/') ? arg : `research/${arg}`])
      const s = await refreshSummary($)
      await refreshRows($, s?.matter ?? null)
      return { text: r.exitCode === 0 ? r.stdout.trim() : r.stderr.trim() }
    }
    if (verb === 'new') {
      await open($, HOME, 'Home')
      return { text: 'Fill in the New matter form in the Home pane: course, short name, question, jurisdiction.' }
    }
    const matters: string[] = []
    for (const course of await $.fs.list('research')) {
      if (course.kind !== 'directory') continue
      for (const m of await $.fs.list(`research/${course.name}`)) {
        if (m.kind === 'directory' && (await $.fs.exists(`research/${course.name}/${m.name}/question.md`))) {
          matters.push(`research/${course.name}/${m.name}`)
        }
      }
    }
    const active = await matterPath($)
    return { text: [`Active matter: ${active ?? 'none'}`, ...matters.map(m => `${m === active ? '*' : '-'} ${m}`),
                     'Switch or create matters in the Home pane (/workbench), or type /matter switch <path>.'].join('\n') }
  })

  on('command.run', { command: 'authorities' }, async $ => {
    await refreshRows($, await matterPath($))
    await open($, PANE, 'Authorities')
    return { text: 'Authorities pane opened.' }
  })

  on('command.run', { command: 'keycite' }, async $ => {
    const m = await matterPath($)
    if (!m) return { text: 'No active matter.' }
    const r = await runScript($, 'keycite_checklist.py', [m])
    return { text: r.exitCode === 0 ? r.stdout : r.stderr }
  })

  // ------------------------------------------------------------ /secondary card: the relay's Bash rows
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    const { tool, input, output, isErrored } = e.props
    const card = relayCard(tool, input, output)
    if (!card || isErrored) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    const pending = card.requestId ? (await read($, rows)).find(r => r.requestId === card.requestId && r.status === 'requested') : undefined
    return (
      <Box flexDirection="column">
        <Text bold>{card.title}</Text>
        {card.lines.map((l, i) => <Text key={`l${i}`} dimColor>{l}</Text>)}
        {pending?.searches.length ? (
          <Box flexDirection="row" gap={1}>
            {pending.searches.map(sr => (
              <Button key={`card-${sr.label}`} label={`Copy ${sr.label}`}
                onPress={() => { void $.ui.copy({ text: sr.query ?? sr.path ?? '' }) }} />
            ))}
            <Button key="card-pane" label="Authorities" onPress={() => { void $.ui.open({ id: PANE, title: 'Authorities' }) }} />
          </Box>
        ) : null}
      </Box>
    )
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ Authorities pane
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Input } = $.ui.resolve(e)
    await read($, ledgerStamp) // redraw when the ledger changes
    const list = await read($, rows)
    const pick = await read($, selected)
    const m = await matterPath($)
    const row = pick ? list.find(r => r.id === pick) : undefined
    if (row) {
      return (
        <Box flexDirection="column">
          <Text bold>{row.name}</Text>
          <Text>{row.cite}</Text>
          <Text dimColor>{`${row.type} · ${row.status} · ${row.label}${row.verdict ? ` · ${row.verdict}` : ''}`}</Text>
          <Text dimColor>{`Citing opinions: ${row.citingCount ?? 'not swept'} · screen flags: ${row.flags} · KeyCite: ${row.keycite}`}</Text>
          {row.westlaw ? (
            <Box flexDirection="row" gap={1}>
              <Button key="westlaw" label="Open in Westlaw" hotkey="w" onPress={() => { void openUrl($, row.westlaw ?? '') }} />
              <Text dimColor>Opens the case in your browser for KeyCite; you sign in and read the flag yourself.</Text>
            </Box>
          ) : null}
          {row.type === 'case' && Input ? (
            <Input key="keycite" label="KeyCite result" placeholder="flag and note, as the user read it" submitLabel="Mark KeyCited"
              onSubmit={value => {
                void (async () => {
                  if (!m || !value.trim()) return
                  await runScript($, 'ledger.py', ['mark', m, row.id, `keycite=${value.trim()}`])
                  await refreshRows($, m)
                })()
              }} />
          ) : null}
          <Box flexDirection="row" gap={1}>
            {row.localPath && m ? (
              <Button key="open" label="Open source" onPress={() => {
                void $.process.run(['cmd', '/c', 'start', '', `${m}/${row.localPath}`.replace(/\//g, '\\')])
              }} />
            ) : null}
            {row.type === 'case' ? (
              <Button key="validate" label="Validate (heavyweight)" onPress={() => {
                void $.prompt.submit({ text: `/validate ${row.id}`, asUser: true })
              }} />
            ) : null}
            <Button key="back" label="Back" hotkey="b" onPress={() => update($, selected, () => null)} />
          </Box>
        </Box>
      )
    }
    const pending = list.filter(r => r.type === 'secondary' && r.status === 'requested')
    const authorities = list.filter(r => !(r.type === 'secondary' && r.status === 'requested'))
    return (
      <Box flexDirection="column">
        <Text dimColor>{m ? `${m.replace(/^research\//, '')} · ${authorities.length} authorities` : 'No active matter.'}</Text>
        {authorities.length === 0 ? <Text dimColor>Nothing retrieved yet.</Text> : null}
        {authorities.map(r => (
          <Button key={r.id} onPress={() => update($, selected, () => r.id)}>
            {shortName(r.name)} <Text dimColor>{`· ${r.label} · KeyCite ${r.keycite}`}</Text>
          </Button>
        ))}
        {pending.length ? <Text bold>{`Pending Westlaw requests (${pending.length})`}</Text> : null}
        {pending.flatMap(r => [
          <Text key={`${r.id}-h`}>{`${r.requestId}: ${shortName(r.cite, 70)}`}</Text>,
          <Button key={`${r.id}-report`} label={`Report back on ${r.requestId}`} onPress={() => { void openReport($, r.requestId ?? '') }} />,
          ...r.searches.map(sr => (
            <Button key={`${r.id}-${sr.label}`} onPress={() => { void $.ui.copy({ text: sr.query ?? sr.path ?? '' }) }}>
              {`Copy ${sr.label}`} <Text dimColor>{`· ${sr.method}${sr.content ? ` · ${sr.content}` : ''}`}</Text>
            </Button>
          )),
        ])}
      </Box>
    )
  }).catch(($, e, next) => next(e))
}
