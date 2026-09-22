/**
 * 分区域量化（含区域内的亮度标准差与梯度均值）。
 * 用法：node regions.mjs <label> <png> [<label> <png> ...]
 * 区域是归一化 0..1 —— 出图尺寸一致时可直接横向比较。
 *
 * 看什么：
 *   over    该区域有没有被打到饱和（饱和之后其上的纹理全部消失）
 *   std     区域内亮度的标准差 —— "这块面有没有深浅变化"
 *   detail  区域内相邻像素梯度均值 —— "这块面有没有可见纹理"
 * 判断"材质特征有没有生效"必须看后两个，且**要在同一曝光下比**。
 */
import { analyzePng } from './pngStats.mjs'

const REGIONS = [
  { name: 'skyTop', x: 0.05, y: 0.005, w: 0.90, h: 0.07 },
  { name: 'skyMid', x: 0.05, y: 0.07, w: 0.90, h: 0.08 },
  { name: 'roof', x: 0.40, y: 0.30, w: 0.22, h: 0.08 },
  { name: 'wall', x: 0.42, y: 0.42, w: 0.18, h: 0.14 },
  { name: 'wallLit', x: 0.30, y: 0.36, w: 0.13, h: 0.12 },
  { name: 'ground', x: 0.05, y: 0.88, w: 0.90, h: 0.10 },
]

const args = process.argv.slice(2)

if (process.env.STATS === 'detail') {
  console.log(`${'case'.padEnd(18)} ${'region'.padEnd(9)} ${'mean'.padStart(7)} ${'std'.padStart(7)} ${'detail'.padStart(8)}`)
  for (let i = 0; i < args.length; i += 2) {
    const stats = analyzePng(args[i + 1], { regions: REGIONS })
    for (const r of REGIONS) {
      const v = stats.regions[r.name]
      console.log(
        `${args[i].padEnd(18)} ${r.name.padEnd(9)} ${String(v.meanLuma).padStart(7)} `
        + `${String(v.stdLuma).padStart(7)} ${String(v.detailEnergy).padStart(8)}`,
      )
    }
  }
} else {
  console.log(
    `${'case'.padEnd(16)} ${'mean'.padStart(6)} ${'over'.padStart(6)} ${'detail'.padStart(7)}  `
    + REGIONS.map((r) => r.name.padStart(13)).join(''),
  )
  for (let i = 0; i < args.length; i += 2) {
    const stats = analyzePng(args[i + 1], { regions: REGIONS })
    console.log(
      `${args[i].padEnd(16)} ${String(stats.meanLuma).padStart(6)} `
      + `${stats.overexposureRatio.toFixed(3).padStart(6)} ${String(stats.detailEnergy).padStart(7)}  `
      + REGIONS.map((r) => {
        const v = stats.regions[r.name]
        return `${v.meanLuma.toFixed(0)}/${v.stdLuma.toFixed(1)}`.padStart(13)
      }).join(''),
    )
  }
}
