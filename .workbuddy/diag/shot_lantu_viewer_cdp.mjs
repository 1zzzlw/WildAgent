/**
 * 用真浏览器给 lantu 查看器出图（CDP 版）。
 *
 * 为什么不是 `chrome --screenshot`：
 *   那套靠 `--virtual-time-budget` 猜时机，实测会截到"只有地面、建筑还没重建完"
 *   的空帧 —— 而且因为此时相机还是写死的初值，不同 cam 参数会截出**字节完全相同**
 *   的图，很容易被误读成"参数没生效"。
 * 本脚本显式轮询页面里的 `window.__wildViewer.ready()`，等重建真的完成再截。
 *
 * 前置：查看器 dev server 在跑
 *   cd wild-web/lantu/viewer && node ../../node_modules/vite/bin/vite.js --port 5180 --strictPort
 *
 * 用法：
 *   node .workbuddy/diag/shot_lantu_viewer_cdp.mjs                   # 默认全套机位
 *   node .workbuddy/diag/shot_lantu_viewer_cdp.mjs pool front        # 指定机位
 *   EXP=1.15 W=2000 H=1200 PREFIX=v2 node .workbuddy/diag/shot_lantu_viewer_cdp.mjs
 */
import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

const CHROME = process.env.CHROME
  ?? 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1148/chrome-win/chrome.exe'
const URL_BASE = process.env.URL_BASE ?? 'http://127.0.0.1:5180'
/**
 * 曝光覆盖。**留空即"不覆盖"** —— 这点很重要：`?exp=` 在查看器里是绝对覆盖，
 * 一旦默认传 1.05，"这一张图用的就是引擎标定后的曝光"这句话就不成立了。
 * 标定之后要验证"交付状态"，必须让查看器走 `TIME_PRESETS` 自己的值。
 */
const EXP = process.env.EXP ?? ''
const PANEL = process.env.PANEL ?? '0'
const GRID = process.env.GRID ?? '1'
/** 额外查询参数（不含 ?），如 `time=night&env=meadow`。 */
const EXTRA = process.env.EXTRA ?? ''
const W = Number(process.env.W ?? 1600)
const H = Number(process.env.H ?? 1000)
const DSF = Number(process.env.DSF ?? 1.5)
const PREFIX = process.env.PREFIX ?? 'viewer_real'
const OUT = resolve(
  process.env.OUT ?? 'E:/AgentProject/WildAgent/wild-web/lantu/docs/renders',
)
const PORT = Number(process.env.CDP_PORT ?? 9333)

const CAMS = process.argv.slice(2)
const CAM_LIST = CAMS.length > 0 ? CAMS : ['pool', 'front', 'aerial', 'iso']

if (!existsSync(CHROME)) {
  console.error(`找不到 Chromium：${CHROME}`)
  process.exit(1)
}

const PROFILE = 'C:/Users/Administrator/AppData/Local/Temp/cbcdp'
rmSync(PROFILE, { recursive: true, force: true })
mkdirSync(PROFILE, { recursive: true })
mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 极简 CDP 客户端：只实现本脚本需要的方法。 */
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
        if (msg.error) reject(new Error(`${msg.error.message} (${JSON.stringify(msg.error.data ?? '')})`))
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
  /** 在页面里求值并取回 JSON 结果。 */
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    })
    if (r.exceptionDetails) {
      throw new Error(`页面内异常：${r.exceptionDetails.text} ${r.exceptionDetails.exception?.description ?? ''}`)
    }
    return r.result?.value
  }
}

const chrome = spawn(CHROME, [
  '--headless=new',
  '--no-sandbox',
  '--no-first-run',
  '--no-proxy-server',
  '--disable-dev-shm-usage',
  '--hide-scrollbars',
  '--enable-unsafe-swiftshader',
  // 打开单文件产物（file://）时必须给：ES module 在 file:// 下默认被 CORS 拦掉，
  // 页面会停在"句柄建不出来"或"canvas 全黑"两种假象上，非常容易误判成渲染坏了。
  '--allow-file-access-from-files',
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

let exitCode = 0
try {
  await waitForDevTools()
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
  const target = list.find((t) => t.type === 'page')
  if (!target) throw new Error('没有可用的 page target')

  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true })
    ws.addEventListener('error', rej, { once: true })
  })
  const cdp = new Cdp(ws)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: W,
    height: H,
    deviceScaleFactor: DSF,
    mobile: false,
  })

  console.log(`chromium : ${CHROME}`)
  console.log(`url      : ${URL_BASE}   exposure=${EXP}  ${W}x${H} @${DSF}x`)
  console.log()

  for (const cam of CAM_LIST) {
    // URL_BASE 指向单文件 HTML 时（file:// 或 .../index.html），直接拼查询串；
    // 指向 dev server 根（http://127.0.0.1:5180）时补根路径。
    const base = /\.html?$/i.test(URL_BASE) ? URL_BASE : `${URL_BASE}/`
    // EXTRA 透传额外查询参数（如 `time=night&env=meadow`），用于固定复现时段/环境档。
    const extra = EXTRA ? `&${EXTRA}` : ''
    // EXP 为空时不传 exp —— 让查看器用引擎预设自己的曝光（验证"交付状态"必须这样）。
    const expParam = EXP === '' ? '' : `&exp=${EXP}`
    const url = `${base}?cam=${cam}&panel=${PANEL}&grid=${GRID}${expParam}${extra}`
    await cdp.send('Page.navigate', { url })
    // 导航是"发起"就返回，页面还没换执行上下文。此时立刻 eval 会打到 about:blank 上，
    // 表现是 `phase=no-handle` —— 而且**时快时慢**（首帧要编译着色器 + 建 PMREM +
    // 重建 129 个网格，慢的时候好几秒），所以看着像"随机失败"。
    await sleep(2500)

    // 等重建真的完成（而不是等一个猜出来的时长）
    let phase = 'unknown'
    for (let i = 0; i < 240; i++) {
      phase = await cdp
        .eval('(window.__wildViewer && window.__wildViewer.phase && window.__wildViewer.phase()) || "no-handle"')
        .catch((err) => (process.env.DEBUG_POLL ? `eval-err:${err.message}` : 'no-handle'))
      if (process.env.DEBUG_POLL && i % 4 === 0) {
        console.log(`  [poll ${i}] phase=${phase} url=${await cdp.eval('location.href').catch(() => '?')}`)
      }
      if (phase === 'ready' || phase === 'error') break
      await sleep(250)
    }
    if (phase === 'error') {
      const msg = await cdp.eval('window.__wildViewer.message()').catch(() => '?')
      console.log(`❌ ${cam}  → 页面重建失败：${msg}`)
      exitCode = 1
      continue
    }
    if (phase !== 'ready') {
      console.log(`❌ ${cam}  → 等待就绪超时（phase=${phase}）`)
      exitCode = 1
      continue
    }

    // 换机位 → 至少画两帧 → 再截（阴影贴图要一帧才生效）
    await cdp.eval(`window.__wildViewer.setCam(${JSON.stringify(cam)})`)
    await cdp.eval(`new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 300))))`)
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' })
    const buf = Buffer.from(shot.data, 'base64')
    const file = resolve(OUT, `${PREFIX}_${cam}.png`)
    writeFileSync(file, buf)
    console.log(`✅ ${cam.padEnd(7)} → ${PREFIX}_${cam}.png  ${buf.length} B`)
  }

  ws.close()
} catch (err) {
  console.error('出错：', err?.message ?? err)
  exitCode = 1
} finally {
  chrome.kill()
}

process.exit(exitCode)
