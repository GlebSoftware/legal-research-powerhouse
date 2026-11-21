// legal-workbench H4 (docs/04-harness.md 5.5): the panes that replace opening files. Home (matter, jurisdiction and
// mode pickers, what waits on the user, the matter list, the new-matter form, a question box), Drafts (audit counts,
// review page, Word file), Help, and the Westlaw report-back form. Every form calls a plugin script.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'
import type {
  LegalWorkbenchChoice, LegalWorkbenchDraft, LegalWorkbenchMatterRow, LegalWorkbenchNewMatter, LegalWorkbenchReport,
  LegalWorkbenchRow, LegalWorkbenchSummary,
} from '../types'
import { DEFAULT_JURISDICTION, MODES, currentMode, frontMatter, isWorkspace, loadJurisdictions } from './matter.ts'
import { scriptPath } from './paths.ts'
import { refreshRows, refreshSummary } from './state.ts'

const summary = atom({ plugin: 'legal-workbench', key: 'summary' } as const, null as LegalWorkbenchSummary | null)
const rows = atom({ plugin: 'legal-workbench', key: 'rows' } as const, [] as LegalWorkbenchRow[])
const matters = atom({ plugin: 'legal-workbench', key: 'matters' } as const, [] as LegalWorkbenchMatterRow[])
const newMatter = atom({ plugin: 'legal-workbench', key: 'newMatter' } as const,
  { course: '', name: '', question: '', jurisdiction: DEFAULT_JURISDICTION } as LegalWorkbenchNewMatter)
const jurisdictions = atom({ plugin: 'legal-workbench', key: 'jurisdictions' } as const, [] as LegalWorkbenchChoice[])
const homeMessage = atom({ plugin: 'legal-workbench', key: 'homeMessage' } as const, null as string | null)
const drafts = atom({ plugin: 'legal-workbench', key: 'drafts' } as const, [] as LegalWorkbenchDraft[])
const draftSelected = atom({ plugin: 'legal-workbench', key: 'draftSelected' } as const, null as string | null)
const report = atom({ plugin: 'legal-workbench', key: 'report' } as const, null as LegalWorkbenchReport | null)
const reportMessage = atom({ plugin: 'legal-workbench', key: 'reportMessage' } as const, null as string | null)

export const HOME = 'home'
export const DRAFTS = 'drafts'
export const HELP = 'help'
export const REPORT = 'westlaw-report'
const AUTHORITIES = 'authorities'

export const MODE_LABELS: Record<string, string> = {
  research: 'Research: find, read, and ledger authority',
  draft: 'Draft: write from the ledger only',
  cite: 'Cite-check: audit and fix drafts',
  free: 'Free: context only, no protocol',
}

async function runScript($: EngineInterface, name: string, args: string[]) {
  const cwd = await $.session.cwd()
  return $.process.run(['uv', 'run', '--quiet', '--script', await scriptPath($, name), ...args],
    { cwd, timeoutMs: 300_000, env: { CLAUDE_PROJECT_DIR: cwd } })
}

function openFile($: EngineInterface, path: string) {
  return $.process.run(['cmd', '/c', 'start', '', path.replace(/\//g, '\\')])
}

async function readText($: EngineInterface, path: string): Promise<string | undefined> {
  try {
    const out = await $.fs.read(path)
    return typeof out === 'string' ? out : undefined
  } catch {
    return undefined
  }
}

async function say($: EngineInterface, text: string | null): Promise<void> {
  await update($, homeMessage, () => text)
}

async function matterPath($: EngineInterface): Promise<string | null> {
  return (await read($, summary))?.matter ?? null
}

// ---------------------------------------------------------------- refreshes

export async function refreshMatters($: EngineInterface): Promise<LegalWorkbenchMatterRow[]> {
  const active = await matterPath($)
  const out: LegalWorkbenchMatterRow[] = []
  try {
    for (const course of await $.fs.list('research')) {
      if (course.kind !== 'directory') continue
      for (const m of await $.fs.list(`research/${course.name}`)) {
        const path = `research/${course.name}/${m.name}`
        const q = m.kind === 'directory' ? await readText($, `${path}/question.md`) : undefined
        if (q === undefined) continue
        const fm = frontMatter(q)
        out.push({ path, course: course.name, name: m.name, question: fm.question || null,
                   jurisdiction: fm.jurisdiction || 'Federal (all federal courts)', active: path === active })
      }
    }
  } catch {
    // no research/ folder yet
  }
  await update($, matters, () => out)
  return out
}

/** Red and yellow counts per draft from the last audit/cite-check.json, unwaived items only. */
export function auditCounts(json: string | undefined): Record<string, { red: number; yellow: number }> {
  const out: Record<string, { red: number; yellow: number }> = {}
  try {
    for (const d of (JSON.parse(json ?? '{}').drafts ?? []) as { path: string; items?: { severity: string; waived?: boolean }[] }[]) {
      const live = (d.items ?? []).filter(i => !i.waived)
      out[d.path] = { red: live.filter(i => i.severity === 'red').length, yellow: live.filter(i => i.severity === 'yellow').length }
    }
  } catch {
    // no audit yet
  }
  return out
}

export async function refreshDrafts($: EngineInterface): Promise<LegalWorkbenchDraft[]> {
  const m = await matterPath($)
  const list: LegalWorkbenchDraft[] = []
  if (m) {
    const counts = auditCounts(await readText($, `${m}/audit/cite-check.json`))
    try {
      for (const f of await $.fs.list(`${m}/drafts`)) {
        if (f.kind !== 'file' || !f.name.endsWith('.md')) continue
        const c = counts[`drafts/${f.name}`]
        list.push({ path: `drafts/${f.name}`, name: f.name.replace(/\.md$/, ''), red: c?.red ?? null, yellow: c?.yellow ?? null })
      }
    } catch {
      // no drafts folder
    }
  }
  await update($, drafts, () => list)
  return list
}

async function refreshChoices($: EngineInterface): Promise<void> {
  if ((await read($, jurisdictions)).length) return
  const list = await loadJurisdictions($)
  await update($, jurisdictions, () => list.map(j => ({ id: j.id, label: j.label })))
}

async function refreshAll($: EngineInterface): Promise<void> {
  await refreshChoices($)
  const s = await refreshSummary($)
  await refreshRows($, s?.matter ?? null)
  await refreshMatters($)
  await refreshDrafts($)
}

// ---------------------------------------------------------------- actions

async function switchMatter($: EngineInterface, path: string): Promise<void> {
  const r = await runScript($, 'ledger.py', ['use', path])
  await refreshAll($)
  await say($, r.exitCode === 0 ? `Switched to ${path.replace(/^research\//, '')}.` : r.stderr.trim())
}

export function newMatterProblem(f: LegalWorkbenchNewMatter): string | null {
  if (!f.course.trim()) return 'Type a course (for example: torts).'
  if (!f.name.trim()) return 'Type a short name for the matter (for example: proximate cause).'
  if (!f.question.trim()) return 'Type the research question.'
  return null
}

async function createMatter($: EngineInterface): Promise<void> {
  const f = await read($, newMatter)
  const problem = newMatterProblem(f)
  if (problem) return say($, problem)
  const r = await runScript($, 'matter.py', ['new', f.course.trim(), f.name.trim(), '--question', f.question.trim(),
    '--jurisdiction', f.jurisdiction || DEFAULT_JURISDICTION])
  if (r.exitCode !== 0) return say($, r.stderr.trim() || 'The matter could not be created.')
  await update($, newMatter, () => ({ course: '', name: '', question: '', jurisdiction: DEFAULT_JURISDICTION }))
  await refreshAll($)
  await say($, `${r.stdout.trim()}. Ask your question in the box above, or type it in the prompt.`)
}

async function setJurisdiction($: EngineInterface, id: string): Promise<void> {
  const m = await matterPath($)
  if (!m) return say($, 'Create or switch to a matter first.')
  const r = await runScript($, 'matter.py', ['set', m, `jurisdiction=${id}`])
  await refreshAll($)
  await say($, r.exitCode === 0 ? `Jurisdiction ${r.stdout.trim().replace(/^jurisdiction set: /, 'set to ')}.` : r.stderr.trim())
}

async function setMode($: EngineInterface, mode: string): Promise<void> {
  await $.store.set('mode', mode)
  await update($, summary, s => (s ? { ...s } : s)) // redraw the band, which reads the mode
  await say($, `Mode set to ${MODE_LABELS[mode] ?? mode}.`)
}

async function ask($: EngineInterface, text: string): Promise<void> {
  if (!text.trim()) return
  await $.prompt.submit({ text: text.trim(), asUser: true })
}

export function reportJson(r: LegalWorkbenchReport, today: string): { problem: string | null; json: string } {
  const quotes = [[r.quote1, r.quote1Pin], [r.quote2, r.quote2Pin]].filter(([t]) => t.trim())
    .map(([text, pin]) => ({ text: text.trim(), pin: pin.trim() || r.pin.trim() }))
  const body = {
    request_id: r.requestId, system: 'westlaw-manual', citation: r.citation.trim(), pin: r.pin.trim(),
    retrieved_at: today, keycite: r.keycite.trim() || null,
    points_to: r.pointsTo.split(';').map(s => s.trim()).filter(Boolean), quotes, summary: r.summary.trim(),
  }
  const problem = !body.citation ? 'Paste the full citation.' : !body.pin ? 'Type the pinpoint (section, comment, or page).'
    : !body.summary ? 'Write your two-to-six-sentence summary.' : null
  return { problem, json: JSON.stringify(body, null, 1) + '\n' }
}

async function submitReport($: EngineInterface): Promise<void> {
  const r = await read($, report)
  const m = await matterPath($)
  if (!r || !m) return
  const { problem, json } = reportJson(r, new Date(await $.clock.now()).toISOString().slice(0, 10))
  if (problem) {
    await update($, reportMessage, () => problem)
    return
  }
  const file = `${m}/audit/secondary-reports/${r.requestId}.json`
  await $.fs.write(file, json)
  const run = await runScript($, 'ledger.py', ['secondary', 'ingest', m, r.requestId, file])
  if (run.exitCode !== 0) {
    await update($, reportMessage, () => run.stderr.trim() || 'The report was not accepted.')
    return
  }
  await update($, report, () => null)
  await update($, reportMessage, () => `${r.requestId} recorded. ${run.stdout.trim()}`)
  await refreshAll($)
}

export async function openReport($: EngineInterface, requestId: string): Promise<void> {
  await update($, report, () => ({ requestId, citation: '', pin: '', summary: '', quote1: '', quote1Pin: '', quote2: '',
    quote2Pin: '', pointsTo: '', keycite: '' }))
  await update($, reportMessage, () => null)
  await open($, REPORT, `Westlaw report: ${requestId}`)
}

/** Open a pane; a pane the person asked for takes the keyboard so Tab and the letters work at once. */
export async function open($: EngineInterface, id: string, title: string, focus = true): Promise<void> {
  try {
    await $.ui.open(focus ? { id, title, focus: true } : { id, title })
  } catch {
    // no surface attached (headless): the command's text answers
  }
}

// ---------------------------------------------------------------- startup and commands

/** H4 startup, called from register.tsx's one session.start hook: commands, choices, the Home pane. */
export async function homeStart($: EngineInterface): Promise<void> {
  if (!(await isWorkspace($))) return
  for (const [name, description] of [
    ['workbench', 'Open the Home pane: your matters, jurisdiction, mode, and what is waiting on you'],
    ['drafts', 'Open the Drafts pane: check citations, open the review page, make the Word file'],
    ['legal-help', 'Guide to the legal research workbench: panes, keys, commands, what only you do'],
  ] as const) {
    await $.command.register({ name, description })
  }
  await refreshChoices($)
  await refreshMatters($)
  await refreshDrafts($)
  await open($, HOME, 'Home', false)
}

export function registerHome(on: On): void {
  on('command.run', { command: 'workbench' }, async $ => {
    await refreshAll($)
    await open($, HOME, 'Home')
    return { text: 'Home pane opened.' }
  })
  on('command.run', { command: 'drafts' }, async $ => {
    await refreshDrafts($)
    await open($, DRAFTS, 'Drafts')
    return { text: 'Drafts pane opened.' }
  })
  on('command.run', { command: 'legal-help' }, async $ => {
    await open($, HELP, 'Guide')
    return { text: 'Guide pane opened.' }
  })

  // ------------------------------------------------------------ Home
  on('ui.render', { component: 'Pane', requestId: HOME }, async ($, e) => {
    const { Box, Text, Button, Input, Select } = $.ui.resolve(e)
    const s = await read($, summary)
    const list = await read($, matters)
    const form = await read($, newMatter)
    const choices = (await read($, jurisdictions)).map(j => ({ value: j.id, label: j.label }))
    const msg = await read($, homeMessage)
    const ds = await read($, drafts)
    const mode = await currentMode($)
    const red = ds.reduce((n, d) => n + (d.red ?? 0), 0)
    const waiting = [
      s?.keycitePending ? { key: 'todo-keycite', text: `${s.keycitePending} authorities need your KeyCite check`, label: 'Authorities',
        go: () => open($, AUTHORITIES, 'Authorities') } : null,
      s?.secondaryRequested ? { key: 'todo-westlaw', text: `${s.secondaryRequested} Westlaw request(s) waiting for your report`,
        label: 'Authorities', go: () => open($, AUTHORITIES, 'Authorities') } : null,
      ds.length ? { key: 'todo-drafts', text: `${ds.length} draft(s), ${red} red citation item(s)`, label: 'Drafts',
        go: async () => { await refreshDrafts($); await open($, DRAFTS, 'Drafts') } } : null,
    ].filter(Boolean) as { key: string; text: string; label: string; go: () => Promise<void> }[]
    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>{s?.matter ? `Matter: ${s.matter.replace(/^research\//, '')}` : 'No matter yet: create one below.'}</Text>
          {s?.question ? <Text>{s.question}</Text> : null}
          {s?.matter && Select && choices.length ? (
            <Select key="home-jurisdiction" label="Jurisdiction" options={choices} value={s.jurisdictionId ?? DEFAULT_JURISDICTION}
              onSelect={v => { void setJurisdiction($, v) }} />
          ) : null}
          {Select ? (
            <Select key="home-mode" label="Mode" options={MODES.map(m => ({ value: m, label: MODE_LABELS[m] }))} value={mode}
              onSelect={v => { void setMode($, v) }} />
          ) : null}
          {s?.matter && Input ? (
            <Input key="home-ask" label="Ask" placeholder="Type a research question and press Enter" submitLabel="Ask Claude"
              onSubmit={v => { void ask($, v) }} />
          ) : null}
        </Box>
        <Box flexDirection="column">
          <Text bold>Waiting on you</Text>
          {waiting.length ? waiting.map(w => (
            <Box key={`${w.key}-row`} flexDirection="row" gap={1}>
              <Text>{w.text}</Text>
              <Button key={w.key} label={w.label} onPress={() => { void w.go() }} />
            </Box>
          )) : <Text dimColor>Nothing.</Text>}
        </Box>
        <Box flexDirection="column">
          <Text bold>Your matters</Text>
          {list.length ? list.map(m => (
            <Button key={`matter:${m.path}`} onPress={() => { void switchMatter($, m.path) }}>
              {`${m.active ? '● ' : '○ '}${m.course} / ${m.name}`} <Text dimColor>{`· ${m.jurisdiction}${m.question ? ` · ${m.question.slice(0, 60)}` : ''}`}</Text>
            </Button>
          )) : <Text dimColor>No matters yet.</Text>}
        </Box>
        <Box flexDirection="column">
          <Text bold>New matter</Text>
          {Input ? <Input key="new-course" label="Course" placeholder="torts" value={form.course}
            onInput={v => { void update($, newMatter, f => ({ ...f, course: v })) }}
            onSubmit={v => { void update($, newMatter, f => ({ ...f, course: v })) }} /> : null}
          {Input ? <Input key="new-name" label="Short name" placeholder="proximate cause" value={form.name}
            onInput={v => { void update($, newMatter, f => ({ ...f, name: v })) }}
            onSubmit={v => { void update($, newMatter, f => ({ ...f, name: v })) }} /> : null}
          {Input ? <Input key="new-question" label="Question" placeholder="What does the research need to answer?" value={form.question}
            onInput={v => { void update($, newMatter, f => ({ ...f, question: v })) }}
            onSubmit={v => { void update($, newMatter, f => ({ ...f, question: v })) }} /> : null}
          {Select && choices.length ? <Select key="new-jurisdiction" label="Jurisdiction" options={choices} value={form.jurisdiction}
            onSelect={v => { void update($, newMatter, f => ({ ...f, jurisdiction: v })) }} /> : null}
          <Button key="new-create" label="Create matter" onPress={() => { void createMatter($) }} />
        </Box>
        {msg ? <Text key="home-message">{msg}</Text> : null}
        <Text dimColor>Band buttons: h Home · a Authorities · s Sources · d Drafts · g Guide (click one, or ctrl+x then Tab to reach the band)</Text>
      </Box>
    )
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ Drafts
  on('ui.render', { component: 'Pane', requestId: DRAFTS }, async ($, e) => {
    const { Box, Text, Button, Markdown } = $.ui.resolve(e)
    const m = await matterPath($)
    const list = await read($, drafts)
    const pick = await read($, draftSelected)
    const msg = await read($, homeMessage)
    const d = pick ? list.find(x => x.path === pick) : undefined
    if (d && m) {
      const text = (await readText($, `${m}/${d.path}`)) ?? ''
      return (
        <Box flexDirection="column" gap={1}>
          <Text bold>{d.name}</Text>
          <Text dimColor>{d.red === null ? 'Citations not checked yet.' : `${d.red} red · ${d.yellow} yellow citation items`}</Text>
          <Box flexDirection="row" gap={1}>
            <Button key="draft-check" label="Check citations" onPress={() => { void (async () => {
              const r = await runScript($, 'cite_audit.py', [m, `${m}/${d.path}`, '--html'])
              await refreshDrafts($)
              await say($, (r.stdout || r.stderr).trim().split('\n')[0] ?? '')
            })() }} />
            <Button key="draft-review" label="Review page" onPress={() => { void openFile($, `${m}/audit/cite-check.html`) }} />
            <Button key="draft-word" label="Make Word file" onPress={() => { void (async () => {
              const r = await runScript($, 'render_memo.py', [m, d.path])
              if (r.exitCode === 0) await openFile($, `${m}/final/${d.name}.docx`)
              await say($, r.exitCode === 0 ? `Word file: ${m}/final/${d.name}.docx` : r.stderr.trim())
            })() }} />
            <Button key="draft-revise" label="Ask Claude to fix red items" onPress={() => {
              void ask($, `Revise ${m}/${d.path} until the citation audit shows zero red items.`)
            }} />
            <Button key="draft-back" label="Back" hotkey="b" onPress={() => update($, draftSelected, () => null)} />
          </Box>
          {msg ? <Text>{msg}</Text> : null}
          {Markdown ? <Markdown key="draft-text" text={text.slice(0, 100_000)} /> : <Text>{text.slice(0, 100_000)}</Text>}
        </Box>
      )
    }
    return (
      <Box flexDirection="column">
        <Text dimColor>{m ? `${list.length} draft(s) in ${m.replace(/^research\//, '')}` : 'No active matter.'}</Text>
        {list.length === 0 && m ? <Text dimColor>No drafts yet. Ask Claude to draft the memo from the Home pane.</Text> : null}
        {list.map(x => (
          <Button key={`draft:${x.path}`} onPress={() => update($, draftSelected, () => x.path)}>
            {x.name} <Text dimColor>{x.red === null ? '· not checked' : `· ${x.red} red · ${x.yellow} yellow`}</Text>
          </Button>
        ))}
      </Box>
    )
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ Help
  on('ui.render', { component: 'Pane', requestId: HELP }, async ($, e) => {
    const { Box, Markdown, Text } = $.ui.resolve(e)
    return <Box flexDirection="column">{Markdown ? <Markdown key="help-text" text={HELP_TEXT} /> : <Text>{HELP_TEXT}</Text>}</Box>
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ Westlaw report-back
  on('ui.render', { component: 'Pane', requestId: REPORT }, async ($, e) => {
    const { Box, Text, Button, Input } = $.ui.resolve(e)
    const r = await read($, report)
    const msg = await read($, reportMessage)
    if (!r) return <Box flexDirection="column"><Text dimColor>{msg ?? 'No report open.'}</Text></Box>
    const field = (key: keyof LegalWorkbenchReport, label: string, placeholder: string) => Input ? (
      <Input key={`report-${key}`} label={label} placeholder={placeholder} value={String(r[key])}
        onInput={v => { void update($, report, x => (x ? { ...x, [key]: v } : x)) }}
        onSubmit={v => { void update($, report, x => (x ? { ...x, [key]: v } : x)) }} />
    ) : null
    return (
      <Box flexDirection="column" gap={1}>
        <Text bold>{`Report back on ${r.requestId}`}</Text>
        <Text dimColor>Bring back only what Westlaw's terms allow: the citation, your own summary, and short quotes under 50 words each.</Text>
        {field('citation', 'Citation', 'Restatement (Second) of Torts § 448 (Am. L. Inst. 1965)')}
        {field('pin', 'Pinpoint', 'cmt. b')}
        {field('summary', 'Your summary (2 to 6 sentences)', 'In your own words')}
        {field('quote1', 'Quote 1 (optional)', 'verbatim, under 50 words')}
        {field('quote1Pin', 'Quote 1 pinpoint', 'cmt. b')}
        {field('quote2', 'Quote 2 (optional)', 'verbatim, under 50 words')}
        {field('quote2Pin', 'Quote 2 pinpoint', '')}
        {field('pointsTo', 'Cases or statutes it cites (separate with ;)', '250 Ga. 199; 300 Ga. 840')}
        {field('keycite', 'KeyCite notes (optional)', 'green flag on each case')}
        <Box flexDirection="row" gap={1}>
          <Button key="report-submit" label="Submit report" onPress={() => { void submitReport($) }} />
          <Button key="report-cancel" label="Cancel" onPress={() => { void update($, report, () => null) }} />
        </Box>
        {msg ? <Text key="report-message">{msg}</Text> : null}
      </Box>
    )
  }).catch(($, e, next) => next(e))
}

export const HELP_TEXT = `# Legal research workbench

**Ask in plain words.** Type a legal question in the prompt or in the Home pane's Ask box. Claude picks the
research steps itself; no slash command is needed.

## Panes

The band above the prompt has a button for each pane. Click one, or press ctrl+x then Tab to move from the prompt
to the band and press its letter. Inside a pane, Tab moves between controls and Enter presses one.

| Key | Pane | What you do there |
|---|---|---|
| h | Home | Switch matters, create a matter, change jurisdiction and mode, see what waits on you, ask a question |
| a | Authorities | Every case and statute in the matter with its label; record KeyCite results; copy Westlaw searches; report back on a Westlaw request |
| s | Sources | The saved text of every authority, with a tamper check |
| d | Drafts | Check citations, open the review page, make the Word file |
| g | Guide | This page |

## Commands

| Command | Does |
|---|---|
| /workbench | Open Home |
| /authorities, /sources, /drafts | Open that pane |
| /matter | List matters; /matter switch torts/x; /matter new torts/x |
| /mode research, draft, cite, or free | Change how strictly Claude follows the protocol |
| /keycite | Your KeyCite checklist |
| /review | Run the citation audit and open the review page |
| /validate <case> | Check whether a case is still good law |
| /secondary request <issue> | Ask Claude to write Westlaw searches for you to run |
| /legal-help | This page |

## Labels on every case

- **Verified (heavyweight)**: Claude read the citing cases and checked history. Still KeyCite it for graded work.
- **Screened (lightweight)**: a quick scan of citing cases found nothing loud.
- **Not validated**: retrieved and read, not yet checked.

## What only you do

1. **KeyCite**: in Authorities, open the case and press *Open in Westlaw* (key w). Read the flag, type it in the
   KeyCite result box, and press *Mark KeyCited*.
2. **Westlaw requests**: copy each search from Authorities, run it yourself, then press *Report back* and fill the form.
Claude never opens Westlaw, Lexis, or Bloomberg; their terms forbid it.

## Matters

Each research project is a matter: a folder under research/<course>/<name>. You never need to open it; the
Home pane creates and switches matters. Jurisdiction starts as Federal; change it from Home.
`
