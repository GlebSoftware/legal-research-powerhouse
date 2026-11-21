// Where the legal-research plugin's scripts live. Loaded from the repo (--plugin-dir), the mod sits two folders
// from plugins/legal-research/scripts. An installed copy under ~/.claude/plugins/cache has no such sibling, so the
// session's project folder is the fallback. A path that holds no cite_gate.py makes the gate fail, and the gate's
// .catch then denies the write.
import type { EngineInterface } from 'claude-code'

function trim(p: string): string {
  return p.replace(/\\/g, '/').replace(/\/$/, '')
}

export async function scriptsDir($: EngineInterface): Promise<string> {
  const sibling = `${trim($.plugin.root)}/../../plugins/legal-research/scripts`
  try {
    if (await $.fs.exists(`${sibling}/cite_gate.py`)) return sibling
  } catch {
    // outside the readable roots: use the project folder
  }
  return `${trim(await $.session.cwd())}/plugins/legal-research/scripts`
}

export async function scriptPath($: EngineInterface, name: string): Promise<string> {
  return `${await scriptsDir($)}/${name}`
}
