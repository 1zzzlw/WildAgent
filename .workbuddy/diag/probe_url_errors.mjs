/**
 * 打开一个 URL，把所有 console / 未捕获异常 / 资源失败打出来。
 * 用途：出图脚本只报 `phase=no-handle` 时，定位"模块到底为什么没跑起来"。
 *
 * 用法：node probe_url_errors.mjs "http://127.0.0.1:5180/?cam=pool"
 */
import { spawn } from 'node:child_process'
import { rmSync, mkdirSync, existsSync } from 'node:fs'

const CHROME = process.env.CHROME
  ?? 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1148/chrome-win/chrome.exe'
const URL_ = process.argv[2] ?? 'http://127.0.0.1:5180/'
const PORT = Number(process.env.CDP_PORT ?? 9336)
const PROFILE = 'C:/Users/Administrator/AppData/Local/Temp/cbprobe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

if (!existsSync(CHROME)) {
  console.error('找不到 Chromium：', CHROME)
  process.exit(1)
}
rmSync(PROFILE, { recursive: true, force: true })
mkdirSync(PROFILE, { recursive: true })

const chrome = spawn(CHROME, [
  '--headless=new', '--no-sandbox', '--no-first-run', '--no-proxy-server',
  '--disable-dev-shm-usage', '--enable-unsafe-swiftshader', '--allow-file-access-from-files',
  `--user-data-dir=${PROFILE}`, `--remote-debugging-port=${PORT}`,
  '--window-size=1200,800', 'about:blank',
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
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true })
    ws.addEventListener('error', rej, { once: true })
  })

  let id = 0
  const send = (method, params = {}) => new Promise((res) => {
    const myId = ++id
    const onMessage = (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id === myId) {
        ws.removeEventListener('message', onMessage)
        res(msg.result)
      }
    }
    ws.addEventListener('message', onMessage)
    ws.send(JSON.stringify({ id: myId, method, params }))
  })

  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails
      console.log('❌ 未捕获异常:', d.text, d.exception?.description ?? '')
      exitCode = 1
    } else if (msg.method === 'Runtime.consoleAPICalled') {
      const text = msg.params.args.map((a) => a.value ?? a.description ?? '').join(' ')
      console.log(`[${msg.params.type}] ${text}`)
      if (msg.params.type === 'error') exitCode = 1
    } else if (msg.method === 'Network.loadingFailed') {
      console.log('⚠️ 资源加载失败:', msg.params.errorText, msg.params.type)
    }
  })

  await send('Runtime.enable')
  await send('Network.enable')
  await send('Page.enable')
  await send('Page.navigate', { url: URL_ })
  await sleep(6000)

  const probe = await send('Runtime.evaluate', {
    expression: `JSON.stringify({
      hasHandle: Boolean(window.__wildViewer),
      phase: window.__wildViewer ? window.__wildViewer.phase() : null,
      message: window.__wildViewer ? window.__wildViewer.message() : null,
      canvases: document.querySelectorAll('canvas').length,
    })`,
    returnByValue: true,
  })
  console.log('页内状态:', probe?.result?.value)

  ws.close()
} catch (err) {
  console.error('出错：', err?.message ?? err)
  exitCode = 1
} finally {
  chrome.kill()
}

process.exit(exitCode)
