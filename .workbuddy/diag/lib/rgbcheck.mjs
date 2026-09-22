import { analyzePng } from './pngStats.mjs'

const REGIONS = [
  { name: 'skyTop', x: 0.05, y: 0.005, w: 0.90, h: 0.07 },
  { name: 'skyMid', x: 0.05, y: 0.07, w: 0.90, h: 0.08 },
  { name: 'wall', x: 0.42, y: 0.42, w: 0.18, h: 0.14 },
]

for (const file of process.argv.slice(2)) {
  const stats = analyzePng(file, { regions: REGIONS })
  const r = stats.regions
  const name = file.replace(/\\/g, '/').split('/').pop()
  console.log(
    `${name.padEnd(50)} mean=${String(stats.meanLuma).padEnd(6)} detail=${stats.detailEnergy}  `
    + `skyMid=${JSON.stringify(r.skyMid.rgb)} B-R=${String(r.skyMid.blueBias).padStart(3)}  `
    + `skyTop=${JSON.stringify(r.skyTop.rgb)}  wall=${JSON.stringify(r.wall.rgb)}`,
  )
}
