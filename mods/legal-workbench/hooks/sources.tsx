// legal-workbench H3 (docs/04-harness.md 5.3): the Sources pane, /sources, and /review.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'
import type { LegalWorkbenchSource, LegalWorkbenchSummary } from '../types'
import { isWorkspace } from './matter.ts'
import { scriptPath } from './paths.ts'

const summary = atom({ plugin: 'legal-workbench', key: 'summary' } as const, null as LegalWorkbenchSummary | null)
const sources = atom({ plugin: 'legal-workbench', key: 'sources' } as const, [] as LegalWorkbenchSource[])
const sourceSelected = atom({ plugin: 'legal-workbench', key: 'sourceSelected' } as const, null as string | null)

export const SOURCES_PANE = 'sources'
const SHOW_CHARS = 100_000

async function runScript($: EngineInterface, name: string, args: string[]) {
  const cwd = await $.session.cwd()
  return $.process.run(['uv', 'run', '--quiet', '--script', await scriptPath($, name), ...args],
    { cwd, timeoutMs: 300_000, env: { CLAUDE_PROJECT_DIR: cwd } })
}

function openInBrowser($: EngineInterface, path: string) {
  return $.process.run(['cmd', '/c', 'start', '', path.replace(/\//g, '\\')])
}

/** Saved opinions arrive as CourtListener HTML or XML; the pane shows their text. */
export function readable(path: string, text: string): string {
  if (!/\.(html?|xml)$/i.test(path)) return text
  return text
    .replace(/<(script|style)\b[\s\S]*?<\/\1>/gi, '')
    .replace(/<(?:br|\/p|\/div|\/h\d|\/li)\b[^>]*>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;|&#160;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;|&#x27;|&rsquo;/g, '’')
    .replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
}

export function parseSources(stdout: string): LegalWorkbenchSource[] {
  try {
    const rows = JSON.parse(stdout.trim() || '[]')
    return Array.isArray(rows) ? (rows as LegalWorkbenchSource[]) : []
  } catch {
    return []
  }
}

async function matterPath($: EngineInterface): Promise<string | null> {
  return (await read($, summary))?.matter ?? null
}

export async function refreshSources($: EngineInterface): Promise<LegalWorkbenchSource[]> {
  const m = await matterPath($)
  const list = m ? parseSources((await runScript($, 'sources_status.py', [m, '--json'])).stdout) : []
  await update($, sources, () => list)
  return list
}

/** H3 startup, called from register.tsx's one session.start hook. */
export async function sourcesStart($: EngineInterface): Promise<void> {
  if (!(await isWorkspace($))) return
  await $.command.register({ name: 'sources', description: 'Open the Sources pane: saved documents with hash check and retrieval time' })
  await $.command.register({ name: 'review', description: 'Run the citation audit on the drafts and open audit/cite-check.html' })
}

export function registerSources(on: On): void {
  on('command.run', { command: 'sources' }, async $ => {
    const list = await refreshSources($)
    await $.ui.open({ id: SOURCES_PANE, title: 'Sources' })
    const bad = list.filter(s => s.status !== 'ok').length
    return { text: `${list.length} saved sources, ${bad} changed or missing.` }
  })

  on('command.run', { command: 'review' }, async $ => {
    const m = await matterPath($)
    if (!m) return { text: 'No active matter.' }
    const r = await runScript($, 'cite_audit.py', [m, '--html'])
    const html = `${m}/audit/cite-check.html`
    if (await $.fs.exists(html)) await openInBrowser($, html)
    const out = (r.stdout || r.stderr).trim()
    return { text: `${out}\n${r.exitCode === 0 ? 'No unwaived red items.' : 'Unwaived red items remain.'} Opened ${html}.` }
  })

  on('ui.render', { component: 'Pane', requestId: SOURCES_PANE }, async ($, e) => {
    const { Box, Text, Button, Markdown } = $.ui.resolve(e)
    const list = await read($, sources)
    const pick = await read($, sourceSelected)
    const m = await matterPath($)
    const src = pick ? list.find(s => s.path === pick) : undefined
    if (src && m) {
      let body = ''
      try {
        const out = await $.fs.read(`${m}/${src.path}`)
        body = typeof out === 'string' ? readable(src.path, out) : ''
      } catch {
        body = 'The file is missing.'
      }
      const cut = body.length > SHOW_CHARS
      return (
        <Box flexDirection="column">
          <Text bold>{src.path}</Text>
          <Text dimColor>{`${src.id ?? 'no ledger id'} · ${src.system ?? '?'} · retrieved ${src.retrieved_at ?? '?'} · hash ${src.status}`}</Text>
          <Box flexDirection="row" gap={1}>
            <Button key="src-open" label="Open in browser" onPress={() => { void openInBrowser($, `${m}/${src.path}`) }} />
            <Button key="src-back" label="Back" hotkey="b" onPress={() => update($, sourceSelected, () => null)} />
          </Box>
          {Markdown ? <Markdown key="src-text" text={cut ? `${body.slice(0, SHOW_CHARS)}\n\n[first ${SHOW_CHARS.toLocaleString('en-US')} characters shown]` : body} />
                    : <Text>{body.slice(0, SHOW_CHARS)}</Text>}
        </Box>
      )
    }
    const bad = list.filter(s => s.status !== 'ok').length
    return (
      <Box flexDirection="column">
        <Text dimColor>{m ? `${list.length} saved sources · ${bad} changed or missing` : 'No active matter.'}</Text>
        {list.map(s => (
          <Button key={`src:${s.path}`} onPress={() => update($, sourceSelected, () => s.path)}>
            {s.path.replace(/^sources\//, '')} <Text dimColor>{`· ${s.system ?? '?'} · ${(s.retrieved_at ?? '').slice(0, 10)} · ${s.status}`}</Text>
          </Button>
        ))}
      </Box>
    )
  }).catch(($, e, next) => next(e))
}
