/** 输出目录显式传入，避免原始工具默认写到项目目录。 */
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

if (!process.argv[2] || !process.argv[3]) {
  console.error('用法: node render_preview.mjs <建筑.wild> <输出目录> [Chrome路径] [--time=day|sunset|night] [--quality=low|medium|high] [--baseline]')
  process.exitCode = 2
} else {
  const script = fileURLToPath(new URL('../references/blueprint-kit/核心资料/wild-web/scripts/render-baseline.mjs', import.meta.url))
  const args = process.argv.slice(2)
  const forwarded = args.filter(arg => arg !== '--baseline')
  if (!args.includes('--baseline') && !args.includes('--presentation')) forwarded.push('--presentation')
  const child = spawn(process.execPath, [script, ...forwarded], {
    stdio: 'inherit', windowsHide: true,
  })
  process.exitCode = await new Promise((resolve, reject) => {
    child.once('error', reject)
    child.once('exit', code => resolve(code ?? 1))
  })
}
