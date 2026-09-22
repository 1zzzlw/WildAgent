/**
 * 生成小尺寸对比图，供人眼查看。
 *
 * 用法：
 *   node mkview.mjs out.png "a.png|x0,y0,w,h" "b.png|..." [--step=6] [--dir=calib]
 * rect 是归一化 0..1；不写 rect 就用整图。
 */
import { resolve } from 'node:path'
import { sideBySideToFile, cropScaleToFile, analyzePng } from './pngStats.mjs'

const args = process.argv.slice(2)
const flags = Object.fromEntries(
  args.filter((a) => a.startsWith('--')).map((a) => a.replace(/^--/, '').split('=')),
)
const positional = args.filter((a) => !a.startsWith('--'))
const [out, ...items] = positional

const step = Number(flags.step ?? 6)
const sources = items.map((item) => {
  const [file, rect] = item.split('|')
  const parsed = rect
    ? rect.split(',').map(Number)
    : null
  return { file, rect: parsed }
})

const info = sideBySideToFile(sources, out, { step, gap: 6 })
console.log(`→ ${out}  ${info.width}x${info.height}  ${info.bytes} B`)
for (const source of sources) {
  const stats = analyzePng(source.file)
  console.log(
    `   ${source.file}  mean=${stats.meanLuma} p50=${stats.p50} `
    + `over=${stats.overexposureRatio} detail=${stats.detailEnergy}`,
  )
}

export { cropScaleToFile, resolve }
