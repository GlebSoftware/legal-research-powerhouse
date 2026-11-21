// Shared session values (types/index.d.ts) and the refreshes that fill them.
import { atom, update } from 'claude-code'
import type { EngineInterface } from 'claude-code'
import type { LegalWorkbenchQuota, LegalWorkbenchRow, LegalWorkbenchSummary } from '../types'
import { fetchQuota, isWorkspace, loadMatter, planProgress, readPlan } from './matter.ts'
import { rows as ledgerRows } from './ledger.ts'

const quota = atom({ plugin: 'legal-workbench', key: 'quota' } as const, null as LegalWorkbenchQuota | null)
const summary = atom({ plugin: 'legal-workbench', key: 'summary' } as const, null as LegalWorkbenchSummary | null)
const rows = atom({ plugin: 'legal-workbench', key: 'rows' } as const, [] as LegalWorkbenchRow[])
const selected = atom({ plugin: 'legal-workbench', key: 'selected' } as const, null as string | null)
const ledgerStamp = atom({ plugin: 'legal-workbench', key: 'ledgerStamp' } as const, 0)

export async function refreshSummary($: EngineInterface): Promise<LegalWorkbenchSummary | null> {
  if (!(await isWorkspace($))) return null
  const m = await loadMatter($)
  const plan = m ? planProgress(await readPlan($, m.path)) : { done: 0, total: 0 }
  const s: LegalWorkbenchSummary = {
    matter: m?.path ?? null, jurisdiction: m ? (m.jurisdiction ?? 'Federal (all federal courts)') : null,
    jurisdictionId: m?.jurisdictionId ?? null, question: m?.question ?? null,
    closedUniverse: m?.closedUniverse ?? false,
    total: m?.counts.total ?? 0, verified: m?.counts.verified ?? 0, screened: m?.counts.screened ?? 0,
    notValidated: m?.counts.notValidated ?? 0, keycitePending: m?.counts.keycitePending ?? 0,
    secondaryRequested: m?.counts.secondaryRequested ?? 0, planDone: plan.done, planTotal: plan.total,
  }
  await update($, summary, () => s)
  return s
}

export async function refreshQuota($: EngineInterface): Promise<void> {
  const q = await fetchQuota($)
  if (q) await update($, quota, () => ({ ...q, checkedAt: Date.now() }))
}

export async function refreshRows($: EngineInterface, matterPath: string | null): Promise<void> {
  if (!matterPath) {
    await update($, rows, () => [])
    return
  }
  let text: string | undefined
  try {
    const out = await $.fs.read(`${matterPath}/authorities.json`)
    text = typeof out === 'string' ? out : undefined
  } catch {
    text = undefined
  }
  await update($, rows, () => ledgerRows(text))
}

/** Reread the ledger when authorities.json changed since the last look; true when it did. */
export async function pollLedger($: EngineInterface, matterPath: string | null, last: number): Promise<number> {
  if (!matterPath) return last
  try {
    const st = await $.fs.stat(`${matterPath}/authorities.json`)
    if (st.mtimeMs !== last) {
      await refreshRows($, matterPath)
      await refreshSummary($)
      await update($, ledgerStamp, () => st.mtimeMs)
      return st.mtimeMs
    }
  } catch {
    // no ledger yet
  }
  return last
}
