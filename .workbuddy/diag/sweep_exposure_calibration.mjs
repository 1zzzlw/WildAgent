/**
 * 曝光/光强标定扫描（真浏览器 + 单会话批量）。
 *
 * ── 为什么要在"一个会话里扫" ────────────────────────────────────
 * 曝光与光强是**连续量**，靠推理定不下来：ACES 在饱和区把亮度压扁，
 * "曝光降 20% ⇒ 平均亮度降 20%"根本不成立（37% 像素已经打到 240+ 时，
 * 画面大部分落在压缩曲线的平坦段）。所以只能实测。
 * 而每次 reload 都要重跑一遍蓝图重建 + PMREM，30 个组合能等一分钟以上；
 * 所以改成在页面里调 `__wildViewer.setLook()` 后重绘、逐组合截图。
 *
 * ── 判据（不看"好不好看"，看三个数）────────────────────────────
 *   overexposureRatio ≤ 上限   过曝的像素上，一切材质/几何细节都被压成同一个白
 *   meanLuma 落在目标带内      太暗则发闷、看不出材质
 *   detailEnergy 尽量大        相邻像素亮度梯度的均值 = "画面里还剩多少可见细节"
 * 打分函数刻意把 detailEnergy 放在首位：本轮优化的目标就是**看得见细节**。
 *
 * 用法：
 *   node .workbuddy/diag/sweep_exposure_calibration.mjs <time> <stage>
 *     time  : day | sunset | night
 *     stage : a（扫曝光）| b（扫 key × hemi）
 *   URL_BASE 可覆盖（默认指向单文件产物，file:// 直接开）
 */
import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { analyzePng } from './lib/pngStats.mjs'

const CHROME = process.env.CHROME
  ?? 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1148/chrome-win/chrome.exe'
const HERE = resolve(import.meta.dirname ?? '.')
const STANDALONE = resolve(HERE, '../../wild-web/lantu/viewer/dist-standalone/index.html')
const URL_BASE = process.env.URL_BASE ?? `file:///${STANDALONE.replace(/\\/g, '/')}`
const OUT = resolve(process.env.OUT ?? resolve(HERE, 'calib'))
const W = Number(process.env.W ?? 1600)
const H = Number(process.env.H ?? 1000)
const DSF = Number(process.env.DSF ?? 1.5)
const PORT = Number(process.env.CDP_PORT ?? 9334)
const CAM = process.env.CAM ?? 'pool'

const TIME = process.argv[2] ?? 'day'
const STAGE = process.argv[3] ?? 'a'

/** 目标带：区间取自"对照时段"的实测 —— 黄昏在 121 亮度 / 0% 过曝时 detailEnergy 最高。 */
const TARGET = { minMean: 100, maxMean: 155, maxOverexposure: 0.02 }

/**
 * 天空的硬约束。
 * 上限 210 来自"自然白天天空的亮度感受"：再亮就只剩白，与阴天/曝晒无区别；
 * blueBias ≥ 18 是"天空没被打白"的客观判据（白天空 B−R ≈ 0）。
 */
const SKY = { minLuma: 150, maxLuma: 212, maxOverexposure: 0.02, minBlueBias: 18 }

/** 区域采样（归一化）：天空是判断"天空辐射量是否离谱"的唯一直接证据。 */
const REGIONS = [
  { name: 'skyTop', x: 0.05, y: 0.005, w: 0.90, h: 0.07 },
  { name: 'skyMid', x: 0.05, y: 0.07, w: 0.90, h: 0.08 },
  { name: 'roof', x: 0.40, y: 0.30, w: 0.22, h: 0.08 },
  { name: 'wall', x: 0.42, y: 0.42, w: 0.18, h: 0.14 },
  { name: 'ground', x: 0.05, y: 0.88, w: 0.90, h: 0.10 },
]

/** 阶段 A：先固定 key/hemi 倍率，只扫曝光，找到"刚好不过曝"的量级。 */
const STAGE_A_KEY = Number(process.env.A_KEY ?? 0.7)
const STAGE_A_HEMI = Number(process.env.A_HEMI ?? 0.35)

function buildCombos() {
  if (process.env.COMBOS_JSON) {
    return JSON.parse(process.env.COMBOS_JSON)
  }
  if (STAGE === 'a') {
    const exps = [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65]
    return exps.map((exposure) => ({ exposure, key: STAGE_A_KEY, hemi: STAGE_A_HEMI }))
  }
  if (STAGE === 'c') {
    // 大范围探底：看天空要暗到什么程度才不再是白的。
    // 这一轴单独扫（光强不动），目的是量出"天空辐射量 / 曝光"的量级，
    // 而不是同时改两个变量导致因果不清。
    const exps = [0.6, 0.45, 0.34, 0.26, 0.2, 0.15, 0.11, 0.08]
    return exps.map((exposure) => ({ exposure, key: 1, hemi: 1 }))
  }
  if (STAGE === 'd') {
    // 联合扫描：曝光（决定天空是否被打白）+ 光强倍率（决定建筑落在哪个亮度带）。
    // 两者必须一起扫 —— 天空亮度只认曝光，建筑亮度是"曝光 × 光强"的合成，
    // 只调一个必然顾此失彼。
    const exps = [0.5, 0.42, 0.34, 0.28, 0.24, 0.2]
    const scales = [1.0, 1.35, 1.8, 2.4]
    const combos = []
    for (const exposure of exps) {
      for (const scale of scales) combos.push({ exposure, key: scale, hemi: scale })
    }
    return combos
  }
  const baseExposure = Number(process.env.B_EXPOSURE ?? 0.85)
  const keys = [0.55, 0.65, 0.75, 0.85, 1.0]
  const hemis = [0.2, 0.3, 0.4, 0.55]
  const combos = []
  for (const key of keys) for (const hemi of hemis) combos.push({ exposure: baseExposure, key, hemi })
  return combos
}

const COMBOS = buildCombos()

if (!existsSync(CHROME)) {
  console.error(`找不到 Chromium：${CHROME}`)
  process.exit(1)
}
if (!existsSync(STANDALONE) && !process.env.URL_BASE) {
  console.error(`单文件查看器不存在：${STANDALONE}\n先构建：cd wild-web/lantu/viewer && node ../../node_modules/vite/bin/vite.js build --config vite.config.standalone.mjs`)
  process.exit(1)
}

const PROFILE = 'C:/Users/Administrator/AppData/Local/Temp/cbsweep'
rmSync(PROFILE, { recursive: true, force: true })
mkdirSync(PROFILE, { recursive: true })
mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class Cdp {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id != null && this.pending.has(msg.id)) {
        const { resolve: res, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        if (msg.error) reject(new Error(msg.error.message))
        else res(msg.result)
      }
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((res, reject) => {
      this.pending.set(id, { resolve: res, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error(`CDP 超时：${method}`))
        }
      }, 60000)
    })
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) {
      throw new Error(`页面内异常：${r.exceptionDetails.text} ${r.exceptionDetails.exception?.description ?? ''}`)
    }
    return r.result?.value
  }
}

const chrome = spawn(CHROME, [
  '--headless=new', '--no-sandbox', '--no-first-run', '--no-proxy-server',
  '--disable-dev-shm-usage', '--hide-scrollbars', '--allow-file-access-from-files',
  '--enable-unsafe-swiftshader',
  `--user-data-dir=${PROFILE}`,
  `--remote-debugging-port=${PORT}`,
  `--window-size=${W},${H}`,
  'about:blank',
], { stdio: 'ignore' })

async function waitForDevTools() {
  for (let i = 0; i < 100; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/version`)
      if (res.ok) return
    } catch { /* 还没起来 */ }
    await sleep(200)
  }
  throw new Error('DevTools 端口没起来')
}

/**
 * 打分：把"照片感"翻译成可计算的东西。
 *
 *   天空被打白的客观标志 = 天空区 B−R 趋近 0（纯白/灰）。蓝天必须有明显正偏。
 *   过曝的代价 = 该像素上的材质与几何细节被压成同一个白，直接从细节能量里扣。
 *   主观上"发闷"= 亮度低于目标带下沿。
 * 细节能量放在首位：本轮改动的目标就是**让细节看得见**。
 */
function score(stats) {
  const sky = stats.regions.skyMid
  if (sky.overexposureRatio > SKY.maxOverexposure) return -9999
  if (sky.meanLuma < SKY.minLuma || sky.meanLuma > SKY.maxLuma) return -9999
  if (sky.blueBias < SKY.minBlueBias) return -9999

  let s = stats.detailEnergy * 100
  if (stats.overexposureRatio > TARGET.maxOverexposure) {
    s -= (stats.overexposureRatio - TARGET.maxOverexposure) * 3000
  }
  if (stats.underexposureRatio > 0.03) s -= (stats.underexposureRatio - 0.03) * 2000
  if (stats.meanLuma < TARGET.minMean) s -= (TARGET.minMean - stats.meanLuma) * 2
  if (stats.meanLuma > TARGET.maxMean) s -= (stats.meanLuma - TARGET.maxMean) * 2
  return s
}

let exitCode = 0
try {
  await waitForDevTools()
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
  const target = list.find((t) => t.type === 'page')
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true })
    ws.addEventListener('error', rej, { once: true })
  })
  const cdp = new Cdp(ws)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: W, height: H, deviceScaleFactor: DSF, mobile: false,
  })

  const base = /\.html?$/i.test(URL_BASE) ? URL_BASE : `${URL_BASE}/`
  const env = process.env.ENV ?? 'minimal'
  const url = `${base}?cam=${CAM}&panel=0&grid=1&time=${TIME}&env=${env}`
  console.log(`url : ${url}`)
  console.log(`time: ${TIME}  env: ${env}  stage: ${STAGE}  组合数: ${COMBOS.length}\n`)
  await cdp.send('Page.navigate', { url })

  let phase = 'unknown'
  for (let i = 0; i < 240; i++) {
    phase = await cdp
      .eval('(window.__wildViewer && window.__wildViewer.phase && window.__wildViewer.phase()) || "no-handle"')
      .catch(() => 'no-handle')
    if (phase === 'ready' || phase === 'error') break
    await sleep(250)
  }
  if (phase !== 'ready') {
    throw new Error(`查看器未就绪：phase=${phase}`)
  }
  await cdp.eval(`window.__wildViewer.setCam(${JSON.stringify(CAM)})`)

  const rows = []
  for (const combo of COMBOS) {
    const look = await cdp.eval(
      `window.__wildViewer.setLook(${JSON.stringify(combo)}) && window.__wildViewer.look()`,
      )
    // 换参数 → 至少两帧 → 稍等，让 PMREM 与阴影落地
    await cdp.eval('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 220))))')
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' })
    const tag = [
      `e${look.exposure.toFixed(3)}`,
      `k${look.keyIntensity.toFixed(2)}`,
      `h${look.hemisphereIntensity.toFixed(2)}`,
      look.sky !== undefined ? `r${look.sky}` : '',
      look.skyTurbidity !== undefined ? `t${look.skyTurbidity}` : '',
    ].filter(Boolean).join('_')
    const file = resolve(OUT, `${TIME}_${process.env.ENV ?? 'minimal'}_${tag}.png`)
    writeFileSync(file, Buffer.from(shot.data, 'base64'))
    const stats = analyzePng(file, { regions: REGIONS })
    rows.push({ combo, look, stats, score: score(stats) })
    const sky = stats.regions.skyMid
    console.log(
      `exp=${String(look.exposure.toFixed(3)).padEnd(6)} key=${String(look.keyIntensity.toFixed(2)).padEnd(6)} `
      + `hemi=${String(look.hemisphereIntensity.toFixed(2)).padEnd(6)} `
      + `ray=${String(look.sky ?? '-').padEnd(5)} turb=${String(look.skyTurbidity ?? '-').padEnd(5)} → `
      + `mean=${String(stats.meanLuma).padEnd(6)} over=${String(stats.overexposureRatio).padEnd(7)} `
      + `detail=${String(stats.detailEnergy).padEnd(6)} `
      + `sky=${String(sky.meanLuma).padEnd(6)} skyB-R=${String(sky.blueBias).padEnd(5)} `
      + `wall=${String(stats.regions.wall.meanLuma).padEnd(6)} `
      + `score=${score(stats).toFixed(1)}`,
    )
  }

  rows.sort((a, b) => b.score - a.score)
  console.log('\n── 排名（前 5）──')
  for (const row of rows.slice(0, 5)) {
    console.log(
      `combo exp=${row.combo.exposure} key=${row.combo.key} hemi=${row.combo.hemi}`
      + `  → 生效曝光 ${row.look.exposure.toFixed(3)} / key ${row.look.keyIntensity.toFixed(3)}`
      + ` / hemi ${row.look.hemisphereIntensity.toFixed(3)}`
      + `  mean=${row.stats.meanLuma} over=${row.stats.overexposureRatio} detail=${row.stats.detailEnergy}`
      + `  score=${row.score.toFixed(1)}`,
    )
  }

  ws.close()
} catch (err) {
  console.error('出错：', err?.message ?? err)
  exitCode = 1
} finally {
  chrome.kill()
}

process.exit(exitCode)
