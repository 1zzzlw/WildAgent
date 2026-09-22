/**
 * 抓页面在真浏览器里的控制台错误与网络失败，用来回答"到底是打不开还是渲染不出来"。
 * 用法：node .workbuddy/diag/probe_page_errors.mjs <url> [<url> ...]
 */
import { spawn } from 'node:child_process'
import { rmSync, mkdirSync } from 'node:fs'

const CHROME = process.env.CHROME
  ?? 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1148/chrome-win/chrome.exe'
const PORT = Number(process.env.CDP_PORT ?? 9344)
const PROFILE = 'C:/Users/Administrator/AppData/Local/Temp/cbprobe'
rmSync(PROFILE, { recursive: true, force: true })
mkdirSync(PROFILE, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const chrome = spawn(CHROME, [
  '--headless=new', '--no-sandbox', '--no-first-run', '--no-proxy-server',
  '--disable-dev-shm-usage', '--enable-unsafe-swiftshader',
  `--user-data-dir=${PROFILE}`, `--remote-debugging-port=${PORT}`,
  'about:blank',
], { stdio: 'ignore' })

class Cdp {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.events = []
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id != null && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
      } else if (msg.method) {
        this.events.push(msg)
      }
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((res, rej) => {
      this.pending.set(id, { resolve: res, reject: rej })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); rej(new Error(`CDP 超时 ${method}`)) } }, 20000)
    })
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    return r.exceptionDetails ? { __error: r.exceptionDetails.text } : r.result?.value
  }
}

let code = 0
try {
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok) break } catch {}
    await sleep(200)
  }
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
  await cdp.send('Log.enable')
  await cdp.send('Network.enable')

  for (const url of process.argv.slice(2)) {
    cdp.events.length = 0
    console.log(`\n================ ${url} ================`)
    await cdp.send('Page.navigate', { url })
    await sleep(6000)

    const fails = cdp.events.filter((e) => e.method === 'Network.loadingFailed')
    const reqs = cdp.events.filter((e) => e.method === 'Network.responseReceived')
    const logs = cdp.events.filter((e) => e.method === 'Log.entryAdded').map((e) => e.params.entry)
    const exs = cdp.events.filter((e) => e.method === 'Runtime.exceptionThrown')
      .map((e) => e.params.exceptionDetails)

    console.log(`已发起请求 ${reqs.length} 个，其中非 2xx：`)
    for (const r of reqs) {
      const s = r.params.response.status
      if (s >= 400 || s === 0) console.log(`   ${s}  ${r.params.response.url.slice(0, 120)}`)
    }
    console.log(`加载失败 ${fails.length} 个：`)
    for (const f of fails) {
      console.log(`   ${f.params.errorText}  blocked=${f.params.blockedReason ?? '-'}  ${String(f.params.requestId)}`)
    }
    console.log(`控制台错误/警告 ${logs.length} 条：`)
    for (const l of logs.slice(0, 12)) {
      console.log(`   [${l.level}/${l.source}] ${String(l.text).slice(0, 200)}`)
    }
    console.log(`未捕获异常 ${exs.length} 条：`)
    for (const e of exs.slice(0, 6)) {
      console.log(`   ${String(e.text).slice(0, 160)} ${String(e.exception?.description ?? '').slice(0, 240)}`)
    }
    const state = await cdp.eval(`JSON.stringify({
      url: location.href,
      hasHandle: typeof window.__wildViewer,
      phase: window.__wildViewer ? window.__wildViewer.phase() : null,
      canvases: document.querySelectorAll('canvas').length,
      panelText: (document.getElementById('stats')||{}).textContent ? String(document.getElementById('stats').textContent).slice(0,120) : null
    })`)
    console.log(`页面状态：${state}`)
  }
  ws.close()
} catch (err) {
  console.error('出错：', err?.message ?? err)
  code = 1
} finally {
  chrome.kill()
}
process.exit(code)
