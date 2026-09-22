/**
 * 运行时门禁：查看器里的光照/环境**必须来自引擎**，且真的生效。
 *
 * 静态门禁 `audit_lighting_single_source.mjs` 只能证明"没有人在引擎目录外写光照代码"，
 * 证明不了"IBL 真的挂上了"。本脚本在真浏览器里跑一次单文件产物，读查看器暴露的
 * 只读体检接口 `window.__wildViewer.lighting()`，断言：
 *   ① `scene.environment` 存在且是 Texture  ⇒ 材质层的玻璃/金属反射才有依据；
 *   ② 场景里 **没有 AmbientLight**          ⇒ 环境光只能来自 IBL，接触阴影不被洗掉；
 *   ③ 光源种类恰为 HemisphereLight + DirectionalLight（引擎骨架）；
 *   ④ 阴影贴图开启。
 *
 * 用法（须先构建单文件产物）：
 *   cd wild-web && node ../.workbuddy/diag/audit_viewer_lighting_runtime.mjs [url]
 * 退出码即结果（0 = 通过）。
 */
import { spawn } from 'node:child_process'
import { rmSync, mkdirSync } from 'node:fs'

const CHROME = process.env.CHROME
  ?? 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1148/chrome-win/chrome.exe'
const PORT = Number(process.env.CDP_PORT ?? 9351)
const PROFILE = 'C:/Users/Administrator/AppData/Local/Temp/cblightprobe'
const URL = process.argv[2]
  ?? 'file:///E:/AgentProject/WildAgent/wild-web/lantu/viewer/dist-standalone/index.html'

rmSync(PROFILE, { recursive: true, force: true })
mkdirSync(PROFILE, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const chrome = spawn(CHROME, [
  '--headless=new', '--no-sandbox', '--no-first-run', '--no-proxy-server',
  '--disable-dev-shm-usage', '--enable-unsafe-swiftshader',
  `--user-data-dir=${PROFILE}`, `--remote-debugging-port=${PORT}`,
  'about:blank',
], { stdio: 'ignore' })

let code = 1
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

  let id = 0
  const pending = new Map()
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id != null && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
    }
  })
  const send = (method, params = {}) => {
    const mid = ++id
    return new Promise((res, rej) => {
      pending.set(mid, { resolve: res, reject: rej })
      ws.send(JSON.stringify({ id: mid, method, params }))
      setTimeout(() => { if (pending.has(mid)) { pending.delete(mid); rej(new Error(`CDP 超时 ${method}`)) } }, 20000)
    })
  }
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    return r.exceptionDetails ? { __error: r.exceptionDetails.text } : r.result?.value
  }

  await send('Runtime.enable')
  await send('Page.enable')
  await send('Page.navigate', { url: URL })
  await sleep(6000)

  const raw = await evaluate(
    'JSON.stringify(window.__wildViewer && window.__wildViewer.lighting ? window.__wildViewer.lighting() : null)',
  )
  const info = raw ? JSON.parse(raw) : null

  console.log(`url: ${URL}`)
  console.log(`体检结果：${JSON.stringify(info, null, 2)}`)

  if (!info) {
    console.error('\n❌ 读不到 lighting() —— 查看器没暴露体检接口，或页面没起来。')
  } else {
    const failures = []
    if (!info.hasEnvironmentMap) failures.push('scene.environment 为空 ⇒ IBL 没挂上（玻璃/金属反射无依据）')
    else if (!info.environmentMapIsTexture) failures.push('scene.environment 不是 Texture')
    if (info.ambientLightCount > 0) failures.push(`场景里有 ${info.ambientLightCount} 个 AmbientLight ⇒ 本地自建环境光，会洗掉接触阴影`)
    const expected = ['DirectionalLight', 'HemisphereLight']
    const kinds = info.lightKinds ?? []
    if (kinds.length !== expected.length || expected.some((k) => !kinds.includes(k))) {
      failures.push(`光源种类 ${JSON.stringify(kinds)} ≠ 引擎骨架 ${JSON.stringify(expected)}`)
    }
    if (!info.shadowMapEnabled) failures.push('shadowMap.enabled = false')

    if (failures.length === 0) {
      console.log('\n✅ 通过：查看器光照来自引擎（IBL 已挂载 / 无自建环境光 / 光源骨架正确 / 阴影开启）。')
      code = 0
    } else {
      console.log('\n❌ 未通过：')
      for (const f of failures) console.log(`  · ${f}`)
    }
  }
  ws.close()
} catch (err) {
  console.error('出错：', err?.message ?? err)
} finally {
  chrome.kill()
}
process.exit(code)
