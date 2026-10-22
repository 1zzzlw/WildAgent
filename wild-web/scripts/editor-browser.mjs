/** 本地回归使用仓库基线相同的独立 Chromium/CDP，不连接用户浏览器。 */
import { spawn } from 'node:child_process'
import process from 'node:process'
import { mkdtemp, readFile, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir, homedir } from 'node:os'
import { join, dirname } from 'node:path'

class Session {
  constructor(ws) {
    this.ws = ws
    this.sequence = 0
    this.pending = new Map()
    this.errors = []
    ws.addEventListener('message', ({ data }) => {
      const message = JSON.parse(data)
      if (message.method === 'Runtime.exceptionThrown') this.errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text)
      if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
        const value=message.params.args.map(arg=>arg.value||arg.description||'').join(' ');
        if (/THREE.WebGLProgram|VALIDATE_STATUS|Shader Error/.test(value)) this.errors.push(value);
      }
      const entry = this.pending.get(message.id)
      if (!entry) return
      this.pending.delete(message.id)
      clearTimeout(entry.timer)
      message.error ? entry.reject(new Error(JSON.stringify(message.error))) : entry.resolve(message.result)
    })
  }
  send(method, params = {}) {
    const id = ++this.sequence
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('CDP 超时: '+method)) }, 45000)
      this.pending.set(id, { resolve, reject, timer })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
    return result.result.value
  }
  async click(selector) {
    const position = await this.evaluate(`(async () => {
      const el=document.querySelector(${JSON.stringify(selector)}); if(!el) throw Error('元素不存在');
      el.scrollIntoView({block:'nearest',inline:'nearest'});
      let previous='',stable=0,r;
      for(let i=0;i<30;i++) {
        r=el.getBoundingClientRect();const current=[r.x,r.y,r.width,r.height].map(v=>v.toFixed(1)).join(',');
        stable=current===previous?stable+1:0;previous=current;
        if(r.width>0&&r.height>0&&stable>=3) return {x:r.x+r.width/2,y:r.y+r.height/2};
        await new Promise(resolve=>setTimeout(resolve,50));
      }
      throw Error('点击目标未稳定或不可见');
    })()`)
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', clickCount: 1, ...position })
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', clickCount: 1, ...position })
  }
  async wait(expression, timeout = 25000) {
    const start = Date.now()
    while (Date.now()-start < timeout) {
      if (await this.evaluate(expression)) return
      await new Promise(resolve => setTimeout(resolve, 150))
    }
    throw new Error('页面等待超时: '+expression)
  }
  async upload(selector, path) {
    const { root } = await this.send('DOM.getDocument')
    const { nodeId } = await this.send('DOM.querySelector', { nodeId: root.nodeId, selector })
    if (!nodeId) throw new Error('未找到文件输入框')
    await this.send('DOM.setFileInputFiles', { nodeId, files: [path] })
  }
  async screenshot(path) {
    await mkdir(dirname(path), { recursive: true })
    const { data } = await this.send('Page.captureScreenshot', { format: 'png' })
    await writeFile(path, Buffer.from(data, 'base64'))
  }
  async resize(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
  }
}

async function connect(url) {
  const ws = new WebSocket(url)
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }) })
  return new Session(ws)
}

export async function launchEditorBrowser(url = 'http://127.0.0.1:5178/') {
  const profile = await mkdtemp(join(tmpdir(), 'wild-editor-browser-'))
  const executable = process.env.CHROMIUM_PATH || join(homedir(), 'AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe')
  const processHandle = spawn(executable, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir='+profile,
    '--remote-allow-origins=*', '--no-first-run', '--no-default-browser-check', '--enable-unsafe-swiftshader',
    '--ignore-gpu-blocklist', '--mute-audio', 'about:blank'], { stdio: 'ignore', windowsHide: true,
      env: { ...process.env, SystemRoot: 'C:\\Windows', WINDIR: 'C:\\Windows' } })
  let endpoint
  let launchError
  processHandle.on('error', error => { launchError = error })
  for (let i=0; i<100; i++) {
    if (launchError) throw launchError
    try {
      const [port] = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split(/\r?\n/)
      endpoint = (await (await fetch('http://127.0.0.1:'+port+'/json/version')).json()).webSocketDebuggerUrl
      if (endpoint) break
    } catch { /* 等待独立浏览器端口文件。 */ }
    await new Promise(resolve => setTimeout(resolve, 150))
  }
  if (!endpoint) { processHandle.kill(); throw new Error('本地 Chromium 启动失败') }
  const browser = await connect(endpoint)
  const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' })
  const page = await connect(endpoint.replace(/\/devtools\/browser\/.+$/, '/devtools/page/'+targetId))
  await page.send('Runtime.enable')
  await page.send('Page.enable')
  await page.resize(1440, 1000)
  await page.send('Page.navigate', { url })
  await page.wait('document.readyState === "complete"')
  return { page, async close() { page.ws.close(); browser.ws.close(); processHandle.kill() } }
}
