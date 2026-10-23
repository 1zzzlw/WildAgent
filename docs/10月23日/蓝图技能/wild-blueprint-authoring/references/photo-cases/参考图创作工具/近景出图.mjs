/** Additional camera framing only; uses the same real renderer and complete WILD. */
import { readFile, writeFile, unlink } from 'node:fs/promises'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const here = dirname(fileURLToPath(import.meta.url))
const source = process.env.WILD_RENDER_SCRIPT || resolve(here, '../../../wild-web/scripts/render-baseline.mjs')
const temporary = join(dirname(source), `.reference-view-${process.pid}.mjs`)
const original = await readFile(source, 'utf8')
const polar = Number(process.argv.find(arg => arg.startsWith('--polar='))?.split('=')[1] || 74)
const adjusted = original
  .replace('width: 1280,', 'width: 1600,').replace('height: 960,', 'height: 1200,')
  .replace(/const VIEWS = \[[\s\S]*?\n\]/, `const VIEWS = [{ name: 'perspective', azimuthDeg: 145, polarDeg: ${polar} }]`)
  .replace("radius * (view.name === 'top' ? 3.4 : 2.6)", 'radius * 1.65')
await writeFile(temporary, adjusted)
try {
  const child = spawn(process.execPath, [temporary, ...process.argv.slice(2)], { stdio: 'inherit', env: process.env })
  process.exitCode = await new Promise((resolve, reject) => { child.once('exit', code => resolve(code ?? 1)); child.once('error', reject) })
} finally { await unlink(temporary) }
