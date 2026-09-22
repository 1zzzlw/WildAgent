/**
 * 曝光标定门禁（真浏览器出图 + 量化断言）。
 *
 * ── 为什么必须做成脚本，而不是"看一眼觉得行" ──────────────────
 * 曝光是**最容易反复退化**的一类改动：S0 把 IBL 接进引擎时，没有任何门禁发现
 * "白天 37% 的像素被打到 240 以上"；而像素一旦进入饱和区，其上的材质与几何细节
 * 会全部并成同一个白 —— 观感上就是"模型不够精细"，但根因在曝光。
 * 所以这里把当时靠人眼发现的三件事固化成断言：
 *   ① 过曝比 ≤ 2%     —— 细节还在不在
 *   ② 天空还得是蓝的   —— 天空被 ACES 推平是"整片白"最常见的来源
 *   ③ 整体亮度落在带内 —— 太暗则发闷
 *
 * ⚠️ 断言的是**区间**不是等值：这些都是观感量，写死等值只会逼后来者
 * "改断言而不是改参数"。区间才拦得住真正的退化。
 *
 * 用法：node .workbuddy/diag/audit_exposure_calibration.mjs
 *   URL_BASE 可覆盖（默认单文件产物 file://）
 *   KEEP=1 保留出图到 .workbuddy/diag/calib/audit/
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
const OUT = resolve(HERE, 'calib/audit')
const PORT = Number(process.env.CDP_PORT ?? 9355)
const W = 1600
const H = 1000
const DSF = 1.5

/**
 * 采样矩阵。
 * 白天额外取 `desert`（directLightScale 1.3，全环境档里最亮的一档）——
 * 标定只要漏了最亮那一档，"某一档一换就刺眼"就会漏到线上。
 */
const CASES = [
  { time: 'day', env: 'minimal' },
  { time: 'day', env: 'desert' },
  { time: 'sunset', env: 'minimal' },
  { time: 'night', env: 'minimal' },
]

const REGIONS = [
  { name: 'skyMid', x: 0.05, y: 0.07, w: 0.90, h: 0.08 },
  { name: 'wall', x: 0.42, y: 0.42, w: 0.18, h: 0.14 },
  { name: 'ground', x: 0.05, y: 0.88, w: 0.90, h: 0.10 },
]

/** 每个时段的期望带（观感区间，不是等值）。 */
const BANDS = {
  day: { mean: [118, 170], maxOver: 0.02, sky: { luma: [148, 214], minBlueBias: 18 } },
  sunset: { mean: [98, 148], maxOver: 0.02, sky: null },
  night: { mean: [17, 46], maxOver: 0.02, sky: null },
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

if (!existsSync(CHROME)) {
  console.error(`找不到 Chromium：${CHROME}`)
  process.exit(1)
}
if (!process.env.URL_BASE && !existsSync(STANDALONE)) {
  console.error(`单文件查看器不存在：${STANDALONE}\n先构建：cd wild-web/lantu/viewer && node ../../node_modules/vite/bin/vite.js build --config vite.config.standalone.mjs`)
  process.exit(1)
}

const PROFILE = 'C:/Users/Administrator/AppData/Local/Temp/cbauditexp'
rmSync(PROFILE, { recursive: true, force: true })
mkdirSync(PROFILE, { recursive: true })
mkdirSync(OUT, { recursive: true })

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
      }, 30000)
    })
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw new Error(`页面内异常：${r.exceptionDetails.text}`)
    return r.result?.value
  }
}

const chrome = spawn(CHROME, [
  '--headless=new', '--no-sandbox', '--no-first-run', '--no-proxy-server',
  '--disable-dev-shm-usage', '--hide-scrollbars', '--enable-unsafe-swiftshader',
  '--allow-file-access-from-files',
  `--user-data-dir=${PROFILE}`, `--remote-debugging-port=${PORT}`,
  `--window-size=${W},${H}`, 'about:blank',
], { stdio: 'ignore' })

async function waitForDevTools() {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok) return
    } catch { /* 还没起来 */ }
    await sleep(200)
  }
  throw new Error('DevTools 端口没起来')
}

const failures = []
let exitCode = 0

function check(label, ok, detail) {
  console.log(`  ${ok ? '✅' : '❌'} ${label}  ${detail}`)
  if (!ok) {
    failures.push(`${label}：${detail}`)
    exitCode = 1
  }
}

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

  for (const testCase of CASES) {
    const label = `${testCase.time}/${testCase.env}`
    console.log(`\n── ${label} ──`)
    // 关键：**不传 `?exp=`**。一旦传了，量到的就是覆盖值而不是引擎预设，
    // 门禁就变成"验证覆盖值"这种毫无意义的自证。
    const url = `${base}?cam=pool&panel=0&grid=1&time=${testCase.time}&env=${testCase.env}`
    await cdp.send('Page.navigate', { url })
    await sleep(2500)

    let phase = 'unknown'
    for (let i = 0; i < 160; i++) {
      phase = await cdp
        .eval('(window.__wildViewer && window.__wildViewer.phase && window.__wildViewer.phase()) || "no-handle"')
        .catch(() => 'no-handle')
      if (phase === 'ready' || phase === 'error') break
      await sleep(250)
    }
    if (phase !== 'ready') {
      check(`${label} 页面就绪`, false, `phase=${phase}`)
      continue
    }

    const look = await cdp.eval('window.__wildViewer.look()')
    await cdp.eval('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 260))))')
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' })
    const file = resolve(OUT, `${testCase.time}_${testCase.env}.png`)
    writeFileSync(file, Buffer.from(shot.data, 'base64'))

    const stats = analyzePng(file, { regions: REGIONS })
    const band = BANDS[testCase.time]

    console.log(`     生效曝光 ${look.exposure.toFixed(3)} / key ${look.keyIntensity.toFixed(2)} / hemi ${look.hemisphereIntensity.toFixed(2)}`)

    check(
      `${label} 无过曝`,
      stats.overexposureRatio <= band.maxOver,
      `over=${stats.overexposureRatio}（限 ${band.maxOver}）`,
    )
    check(
      `${label} 亮度在带内`,
      stats.meanLuma >= band.mean[0] && stats.meanLuma <= band.mean[1],
      `mean=${stats.meanLuma}（带 ${band.mean[0]}~${band.mean[1]}）`,
    )

    if (band.sky) {
      const sky = stats.regions.skyMid
      check(
        `${label} 天空未被推平`,
        sky.meanLuma >= band.sky.luma[0] && sky.meanLuma <= band.sky.luma[1],
        `sky=${sky.meanLuma}（带 ${band.sky.luma[0]}~${band.sky.luma[1]}）`,
      )
      // B−R 是"天空被打白"的客观判据：纯白/灰的天空 B−R ≈ 0。
      check(
        `${label} 天空仍是蓝的`,
        sky.blueBias >= band.sky.minBlueBias,
        `B−R=${sky.blueBias}（≥${band.sky.minBlueBias}）rgb=${JSON.stringify(sky.rgb)}`,
      )
    }
  }

  ws.close()
} catch (err) {
  console.error('出错：', err?.message ?? err)
  exitCode = 1
} finally {
  chrome.kill()
}

console.log()
if (failures.length > 0) {
  console.log(`❌ 曝光标定门禁未通过（${failures.length} 项）：`)
  for (const failure of failures) console.log(`   - ${failure}`)
} else {
  console.log(`✅ 通过：三个时段的曝光/光强标定均在区间内（过曝比、亮度带、天空蓝色偏置）。`)
}
if (!process.env.KEEP) rmSync(OUT, { recursive: true, force: true })

process.exit(exitCode)
