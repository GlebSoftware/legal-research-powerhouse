// legal-workbench (docs/04-harness.md).
// H0 routing: prompt.submit attaches the active matter and protocol as hidden context to every plain prompt;
//   prompt.compose appends the protocol as a session-scope system section so it survives compaction.
// H1 presentation: legal tool rows and results in place of raw JSON, spinner progress from plan.md,
//   status line, and the matter band above the prompt.
// H2 workspace: workbench.tsx (tool.call citation gate, Authorities pane, /matter, /mode, /authorities, /keycite).
// H3: sources.tsx (Sources pane, /sources, /review).
// H4: home.tsx (Home, Drafts, Guide, and Westlaw report panes; matter, jurisdiction, and mode pickers).
import { atom, read } from 'claude-code'
import type { Register } from 'claude-code'
import type { LegalWorkbenchQuota, LegalWorkbenchSummary } from '../types'
import { PROTOCOL, currentMode, findJurisdiction, isWorkspace, ledgerNames, loadJurisdictions, loadMatter, renderContext } from './matter.ts'
import { classify, describeCall, describeResult } from './rows.ts'
import { refreshQuota, refreshSummary } from './state.ts'
import { PANE, registerWorkbench, workbenchStart } from './workbench.tsx'
import { SOURCES_PANE, refreshSources, registerSources, sourcesStart } from './sources.tsx'
import { DRAFTS, HELP, HOME, homeStart, open as openPane, refreshDrafts, registerHome } from './home.tsx'

// Atoms are declared in each file that reads them (the engine lists a module's state from literals in the file).
const quota = atom({ plugin: 'legal-workbench', key: 'quota' } as const, null as LegalWorkbenchQuota | null)
const summary = atom({ plugin: 'legal-workbench', key: 'summary' } as const, null as LegalWorkbenchSummary | null)

export const SECTION_ID = 'legal-workbench:protocol'
const QUOTA_POLL_MS = 5 * 60 * 1000

function matterName(path: string | null): string {
  return path ? path.replace(/^research\//, '') : 'no matter'
}

export function statusText(s: LegalWorkbenchSummary | null, q: LegalWorkbenchQuota | null): string | undefined {
  if (!s) return undefined
  const cl = q ? ` · CL ${q.remaining}/${q.limit} per ${q.window}` : ''
  return `Matter: ${matterName(s.matter)} · ${s.total} authorities${cl}`
}

export function bandLine(s: LegalWorkbenchSummary, q: LegalWorkbenchQuota | null, mode: string): string {
  const parts = [matterName(s.matter), s.jurisdiction ?? 'jurisdiction not recorded', `mode ${mode}`]
  if (s.closedUniverse) parts.push('closed universe')
  if (q) parts.push(`CourtListener ${q.remaining}/${q.limit} per ${q.window}`)
  return parts.join(' · ')
}

export function countsLine(s: LegalWorkbenchSummary): string {
  const bits = [`${s.verified} Verified`, `${s.screened} Screened`, `${s.notValidated} Not validated`,
    `${s.keycitePending} KeyCite pending`]
  if (s.secondaryRequested) bits.push(`${s.secondaryRequested} Westlaw request${s.secondaryRequested === 1 ? '' : 's'} pending`)
  return `Cases: ${bits.join(' · ')}`
}

export const register: Register = on => {
  // ------------------------------------------------------------ H0 routing
  on('prompt.submit', async ($, e, next) => {
    if (e.command || e.isMeta) return next(e)
    if (!(await isWorkspace($))) return next(e)
    const m = await loadMatter($)
    const block = renderContext(m, await currentMode($), findJurisdiction(await loadJurisdictions($), m?.jurisdictionId))
    return next({ ...e, context: [...(e.context ?? []), block] })
  }).catch(($, e, next) => next(e))

  on('prompt.compose', async ($, e, next) => {
    const out = await next(e)
    if ((e.traits ?? []).includes('bare') || !(await isWorkspace($))) return out
    if (out.sections.some(s => s.id === SECTION_ID)) return out
    return { sections: [...out.sections, { id: SECTION_ID, text: PROTOCOL, scope: 'session' as const }] }
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ H1 status line and quota
  on('session.start', async ($, e, next) => {
    const out = await next(e)
    const s = await refreshSummary($)
    if (s) {
      await refreshQuota($)
      $.ui.status(statusText(s, await read($, quota)))
      $.clock.every(QUOTA_POLL_MS, () => {
        void refreshQuota($).then(async () => $.ui.status(statusText(await read($, summary), await read($, quota))))
      })
    }
    await workbenchStart($)
    await sourcesStart($)
    await homeStart($)
    return out
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    const out = await next(e)
    const s = await refreshSummary($)
    $.ui.status(statusText(s, await read($, quota)))
    return out
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ H1 tool rows
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    const { tool, input, output, isErrored, isRunning } = e.props
    if (!classify(tool, input)) return next(e)
    const s = await read($, summary)
    const names = s?.matter ? await ledgerNames($, s.matter) : {}
    const row = describeCall(tool, input, output, names)
    if (!row) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const draftDenied = classify(tool, input) === 'draft' && isErrored
    return (
      <Box flexDirection="column">
        <Text bold>{draftDenied ? `Draft write blocked by the citation gate · ${row.title.replace(/^Draft updated · /, '')}` : row.title}</Text>
        {row.detail && !draftDenied ? <Text dimColor>{isRunning ? `${row.detail} …` : row.detail}</Text> : null}
      </Box>
    )
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    const { tool, output, isErrored } = e.props
    if (isErrored || !classify(tool, null) || classify(tool, null) === 'draft') return next(e)
    const lines = describeResult(tool, null, output)
    if (!lines) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {lines.length ? lines.map((l, i) => <Text key={`r${i}`} dimColor>{l}</Text>) : <Text dimColor>No results.</Text>}
      </Box>
    )
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ H1 spinner
  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    const s = await read($, summary)
    if (!s?.matter || e.props.message) return next(e)
    const issue = s.planTotal ? `issue ${Math.min(s.planDone + 1, s.planTotal)} of ${s.planTotal}` : matterName(s.matter)
    return next({ ...e, props: { ...e.props, message: `Researching ${issue}` } })
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ H1 band
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const s = await read($, summary)
    if (!s) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        <Text dimColor wrap="truncate-end">{bandLine(s, await read($, quota), await currentMode($))}</Text>
        <Text dimColor wrap="truncate-end">{countsLine(s)}</Text>
        <Box flexDirection="row" gap={1}>
          <Button key="band-home" label="Home" hotkey="h" onPress={() => { void openPane($, HOME, 'Home') }} />
          <Button key="band-authorities" label="Authorities" hotkey="a" onPress={() => { void openPane($, PANE, 'Authorities') }} />
          <Button key="band-sources" label="Sources" hotkey="s"
            onPress={() => { void refreshSources($).then(() => openPane($, SOURCES_PANE, 'Sources')) }} />
          <Button key="band-drafts" label="Drafts" hotkey="d"
            onPress={() => { void refreshDrafts($).then(() => openPane($, DRAFTS, 'Drafts')) }} />
          <Button key="band-guide" label="Guide" hotkey="g" onPress={() => { void openPane($, HELP, 'Guide') }} />
        </Box>
      </Box>
    )
  }).catch(($, e, next) => next(e))

  // ------------------------------------------------------------ H2 workspace
  registerWorkbench(on)
  registerSources(on)
  registerHome(on)
}
