/**
 * P7-A：真实渲染基线（CDP 直连，零外部依赖）。
 *
 * 为什么用裸 CDP 而不是 playwright：这条通路要长期可复现，依赖越少越好 ——
 * playwright 的版本升级会悄悄换 Chromium 与 GPU 后端，两次基线就不可比了。
 * 直接 `chrome.exe --remote-debugging-port` + WebSocket，浏览器版本由
 * ``CHROMIUM_PATH`` 显式指定，渲染结果只随仓库源码与这个路径变。
 *
 * 🔴 出图**必须**是引擎渲染：three 的 WebGLRenderer 在 Node 里没有 GL 上下文，
 * 软件光栅化替出来的图不是"实际引擎看到的图"。这里在真实 Chromium 里跑 three。
 *
 * 固定项（P7 第 2 条）：引擎（本地 wild-core 源码）、灯光、背景、相机规则、
 * 输出尺寸全部写死在 ``RENDER_SETTINGS``。改动必须同步 ``BASELINE_VERSION``。
 *
 * 用法：node scripts/render-baseline.mjs <blueprint.json> <输出目录> [chrome路径]
 */
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdir, mkdtemp, readdir, readFile, writeFile } from 'node:fs/promises'
import { homedir, tmpdir } from 'node:os'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createServer } from 'vite'

async function sourceDigest(directories) {
  const hash = createHash('sha256')
  async function walk(directory) {
    for (const entry of (await readdir(directory, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) await walk(path)
      else if (/\.(ts|json)$/.test(entry.name)) {
        hash.update(relative(resolve(root, '..'), path).replaceAll('\\', '/'))
        hash.update(await readFile(path))
      }
    }
  }
  for (const directory of directories) await walk(directory)
  hash.update(await readFile(join(coreRoot, 'schema.json')))
  return hash.digest('hex')
}

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const coreRoot = resolve(root, '..', 'wild-core')

export const RENDER_SETTINGS = Object.freeze({
  width: 1280,
  height: 960,
  background: 0xdfe4ea,
  sun: { azimuthDeg: 135, elevationDeg: 42, intensity: 2.1, color: 0xfff4e2 },
  ambient: { sky: 0xdfe9f5, ground: 0x9a958c, intensity: 0.85 },
  ground: { color: 0x8d9083, y: -0.02 },
  toneMappingExposure: 1.0,
})

export const BASELINE_VERSION = 'p7a.3'

/** 四个视角。方位角用度；`top` 拉近一点，其余一致，保证不同尺度同一构图。 */
const VIEWS = [
  { name: 'front', azimuthDeg: 180, polarDeg: 78 },
  { name: 'side', azimuthDeg: 270, polarDeg: 78 },
  { name: 'top', azimuthDeg: 180, polarDeg: 18 },
  { name: 'perspective', azimuthDeg: 225, polarDeg: 68 },
]

const DEFAULT_CHROMIUM = join(
  homedir(), 'AppData', 'Local', 'ms-playwright', 'chromium-1243',
  'chrome-win64', 'chrome.exe',
)

async function loadCore() {
  const parserPath = join(coreRoot, 'src/primitive/parser.ts').replaceAll('\\', '/')
  const corePath = join(coreRoot, 'src/primitive/index.ts').replaceAll('\\', '/')
  const compilerPath = join(coreRoot, 'src/compiler/index.ts').replaceAll('\\', '/')
  const virtualEntry = `
export { parseBlueprint } from 'wildsrc:parser';
export { reconstructEntity } from 'wildsrc:core';
export { compileBlueprintComponents } from 'wildsrc:compiler';
export * as THREE from 'three';
export { createSceneGroupFromEntity } from '/src/renderer/renderEntity.ts';
export { configureKtx2Rendering, configureMaterialRendering } from '/src/renderer/materialAdapter.ts';
`
  const server = await createServer({
    root,
    logLevel: 'silent',
    server: { host: '127.0.0.1', port: 0, fs: { allow: [root, coreRoot] } },
    plugins: [{
      name: 'wild-render-entry',
      configureServer(server) {
        server.middlewares.use('/__baseline', (_req, res) => {
          res.setHeader('Content-Type', 'text/html')
          res.end('<!doctype html><html><body></body></html>')
        })
      },
      resolveId: (id) => (
        id === 'virtual:wild-render' ? '\0virtual:wild-render'
          : id === 'wildsrc:parser' ? parserPath
            : id === 'wildsrc:core' ? corePath
              : id === 'wildsrc:compiler' ? compilerPath : null
      ),
      load: (id) => (id === '\0virtual:wild-render' ? virtualEntry : null),
    }],
  })
  await server.listen()
  return server
}

/** 起一个 headless Chromium，开 CDP，返回 ws 端点。 */
async function launchChromium(executable) {
  const profile = await mkdtemp(join(tmpdir(), 'wild-render-'))
  let launchError
  // 独立临时目录与系统分配端口，避免连到用户已有浏览器。
  const child = spawn(executable, [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    '--remote-allow-origins=*',
    '--hide-scrollbars',
    '--mute-audio',
    '--no-first-run',
    '--disable-dev-shm-usage',
    // 硬件加速：本机有 GPU 时走真实 GL；没有时退回 SwiftShader 软件光栅化
    //（仍然是 Chromium 的 WebGL 实现，仍然是引擎渲染）。
    '--enable-unsafe-swiftshader',
    '--ignore-gpu-blocklist',
    '--use-angle=default',
    'about:blank',
  ], { stdio: 'ignore', windowsHide: true })
  child.on('error', (error) => { launchError = error })

  const deadline = Date.now() + 20000
  let endpoint = null
  while (Date.now() < deadline) {
    try {
      if (launchError) throw launchError
      const [port] = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).trim().split(/\r?\n/)
      const response = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(1000) })
      const info = await response.json()
      endpoint = info.webSocketDebuggerUrl
      break
    } catch {
      if (launchError) throw launchError
      await new Promise((r) => setTimeout(r, 250))
    }
  }
  if (!endpoint) {
    child.kill()
    throw new Error('Chromium 未能在 20s 内开出 CDP 端点')
  }
  return { child, endpoint }
}

/** 极简 CDP 客户端（只用到本页需要的两件事：求值 + 建页）。 */
class CdpSession {
  constructor(ws) {
    this.ws = ws
    this.nextId = 1
    this.pending = new Map()
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data)
      const entry = this.pending.get(message.id)
      if (!entry) return
      this.pending.delete(message.id)
      clearTimeout(entry.timer)
      if (message.error) entry.reject(new Error(JSON.stringify(message.error)))
      else entry.resolve(message.result)
    })
  }

  send(method, params = {}) {
    const id = this.nextId++
    return new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        rejectPromise(new Error(`CDP 超时: ${method}`))
      }, 60000)
      this.pending.set(id, { resolve: resolvePromise, reject: rejectPromise, timer })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }

  async evaluate(expression, awaitPromise = true) {
    const result = await this.send('Runtime.evaluate', {
      expression, awaitPromise, returnByValue: true,
    })
    if (result.exceptionDetails) {
      throw new Error(`页面求值失败：${JSON.stringify(result.exceptionDetails).slice(0, 600)}`)
    }
    return result.result.value
  }
}

async function main() {
  const blueprintPath = process.argv[2]
  const outDir = process.argv[3] || join(root, '..', 'wild-server', '.workbuddy', 'diag', 'p7_baseline')
  const chromePath = process.argv[4] || process.env.CHROMIUM_PATH || DEFAULT_CHROMIUM
  if (!blueprintPath) {
    console.error('用法: node scripts/render-baseline.mjs <blueprint.json> <输出目录> [chrome路径]')
    return 2
  }
  await mkdir(outDir, { recursive: true })

  const rawBlueprint = await readFile(blueprintPath, 'utf8')
  const server = await loadCore()
  let child
  try {
    const launched = await launchChromium(chromePath)
    child = launched.child
    const endpoint = launched.endpoint
    const browserWs = new WebSocket(endpoint)
    await new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => rejectPromise(new Error('浏览器 WebSocket 超时')), 10000)
      browserWs.addEventListener('open', () => { clearTimeout(timer); resolvePromise() }, { once: true })
      browserWs.addEventListener('error', rejectPromise, { once: true })
    })
    const browser = new CdpSession(browserWs)
    const browserVersion = await browser.send('Browser.getVersion')
    const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' })

    const pageWs = new WebSocket(endpoint.replace(/\/devtools\/browser\/.*$/, `/devtools/page/${targetId}`))
    await new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => rejectPromise(new Error('页面 WebSocket 超时')), 10000)
      pageWs.addEventListener('open', () => { clearTimeout(timer); resolvePromise() }, { once: true })
      pageWs.addEventListener('error', rejectPromise, { once: true })
    })
    const page = new CdpSession(pageWs)
    await page.send('Runtime.enable')
    await page.send('Emulation.setDeviceMetricsOverride', {
      width: RENDER_SETTINGS.width, height: RENDER_SETTINGS.height,
      deviceScaleFactor: 1, mobile: false,
    })

    const origin = server.resolvedUrls.local[0]
    await page.send('Page.enable')
    const loaded = new Promise((resolveLoad, rejectLoad) => {
      const timer = setTimeout(() => rejectLoad(new Error('页面加载超时')), 15000)
      const listener = (event) => {
        if (JSON.parse(event.data).method !== 'Page.loadEventFired') return
        clearTimeout(timer)
        pageWs.removeEventListener('message', listener)
        resolveLoad()
      }
      pageWs.addEventListener('message', listener)
    })
    await page.send('Page.navigate', { url: origin + '__baseline' })
    await loaded
    const result = await page.evaluate(`(async () => {
      const { THREE, parseBlueprint, compileBlueprintComponents, reconstructEntity,
              createSceneGroupFromEntity, configureKtx2Rendering, configureMaterialRendering }
        = await import(${JSON.stringify(origin + '@id/__x00__virtual:wild-render')});
      const blueprint = parseBlueprint(${JSON.stringify(rawBlueprint)});
      const compilation = compileBlueprintComponents(blueprint);
      const entity = await reconstructEntity(compilation.blueprint);
      const settings = ${JSON.stringify(RENDER_SETTINGS)};
      const views = ${JSON.stringify(VIEWS)};
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(settings.background);
      const canvas = document.createElement('canvas');
      const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
      configureKtx2Rendering(renderer);
      configureMaterialRendering(renderer.capabilities.getMaxAnisotropy());
      let pendingTextures = 0;
      const textureErrors = [];
      const manager = THREE.DefaultLoadingManager;
      const originalStart = manager.itemStart.bind(manager);
      const originalEnd = manager.itemEnd.bind(manager);
      manager.itemStart = (url) => { pendingTextures++; originalStart(url); };
      manager.itemEnd = (url) => { pendingTextures--; originalEnd(url); };
      manager.onError = (url) => textureErrors.push(url);
      const meshErrors = [];
      const originalError = console.error;
      console.error = (...args) => { meshErrors.push(String(args[0])); originalError(...args); };
      const group = createSceneGroupFromEntity(entity);
      console.error = originalError;
      if (meshErrors.length) throw new Error('网格创建失败: ' + meshErrors.join(','));
      scene.add(group);
      const deadline = Date.now() + 30000;
      while (pendingTextures > 0 && Date.now() < deadline) await new Promise(r => setTimeout(r, 50));
      if (pendingTextures || textureErrors.length) throw new Error('纹理未加载完成: ' + textureErrors.join(','));
      if (!entity.meshes.length || !group.children.length) throw new Error('场景没有可渲染网格');
      let unmapped = entity.meshes.filter((m, i) => !entity.materialParams[i]).length;
      group.traverse(object => { if (object.userData.errorReason) throw new Error(object.userData.errorReason); });
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(600, 600),
        new THREE.MeshStandardMaterial({ color: settings.ground.color, roughness: 1 }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = settings.ground.y;
      scene.add(ground);

      const sun = new THREE.DirectionalLight(settings.sun.color, settings.sun.intensity);
      const az = (settings.sun.azimuthDeg * Math.PI) / 180;
      const el = (settings.sun.elevationDeg * Math.PI) / 180;
      sun.position.set(
        Math.cos(el) * Math.sin(az) * 200, Math.sin(el) * 200, Math.cos(el) * Math.cos(az) * 200,
      );
      scene.add(sun);
      scene.add(new THREE.HemisphereLight(
        settings.ambient.sky, settings.ambient.ground, settings.ambient.intensity,
      ));

      renderer.setSize(settings.width, settings.height, false);
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = settings.toneMappingExposure;
      document.body.appendChild(renderer.domElement);
      const camera = new THREE.PerspectiveCamera(
        45, settings.width / settings.height, 0.1, 3000,
      );

      const box = new THREE.Box3(
        new THREE.Vector3().fromArray(entity.boundingBox.min),
        new THREE.Vector3().fromArray(entity.boundingBox.max),
      );
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      const radius = Math.max(1, sphere.radius);

      const shots = [];
      for (const view of views) {
        const azimuth = (view.azimuthDeg * Math.PI) / 180;
        const polar = (view.polarDeg * Math.PI) / 180;
        // 取景规则与建筑尺度无关：按包围球半径定距离。
        //俯视要看得见**体量轮廓与外轮廓关系**，太近只剩屋面 —— 这是判断
        // "L 形是否被一整块屋顶盖住"的唯一视角，距离必须比立面远。
        const distance = radius * (view.name === 'top' ? 3.4 : 2.6);
        camera.position.set(
          sphere.center.x + distance * Math.sin(polar) * Math.sin(azimuth),
          sphere.center.y + distance * Math.cos(polar),
          sphere.center.z + distance * Math.sin(polar) * Math.cos(azimuth),
        );
        camera.lookAt(sphere.center);
        renderer.render(scene, camera);
        shots.push({ name: view.name, dataUrl: canvas.toDataURL('image/png') });
      }
      const gl = renderer.getContext();
      return {
        shots,
        meshCount: entity.meshes.length,
        materialCount: entity.materialParams.length,
        boundingBox: entity.boundingBox,
        compileErrors: compilation.diagnostics.filter(d => d.level === 'error').length,
        reconstructErrors: entity.diagnostics.filter(d => d.level === 'error').length,
        unmappedMaterials: unmapped,
        glVendor: gl.getParameter(gl.VENDOR),
        glRenderer: gl.getParameter(gl.RENDERER),
      };
    })()`, true)

    const written = []
    for (const shot of result.shots) {
      const base64 = String(shot.dataUrl).split(',')[1] || ''
      const file = join(outDir, `${shot.name}.png`)
      await writeFile(file, Buffer.from(base64, 'base64'))
      written.push({ view: shot.name, file, bytes: Buffer.from(base64, 'base64').length })
    }
    const manifest = {
      baselineVersion: BASELINE_VERSION,
      inputSha256: createHash('sha256').update(rawBlueprint).digest('hex'),
      renderer: 'wild-web/createSceneGroupFromEntity',
      settings: RENDER_SETTINGS,
      views: VIEWS.map((view) => view.name),
      chromium: chromePath,
      browserVersion,
      sourceDigest: await sourceDigest([join(coreRoot, 'src'), join(root, 'src/renderer')]),
      glRenderer: result.glRenderer,
      glVendor: result.glVendor,
      meshCount: result.meshCount,
      materialCount: result.materialCount,
      unmappedMaterials: result.unmappedMaterials,
      boundingBox: result.boundingBox,
      compileErrors: result.compileErrors,
      reconstructErrors: result.reconstructErrors,
      shots: written,
    }
    manifest.contextSha256 = createHash('sha256').update(JSON.stringify({
      sourceDigest: manifest.sourceDigest, settings: manifest.settings, views: VIEWS,
      browser: browserVersion.product, glRenderer: manifest.glRenderer,
    })).digest('hex')
    await writeFile(join(outDir, 'render_manifest.json'), JSON.stringify(manifest, null, 2), 'utf8')
    console.log(JSON.stringify(manifest, null, 2))

    // P7 第 4 条：截不到图必须标失败，不给空白图打质量分。
    if (manifest.compileErrors || manifest.reconstructErrors || manifest.unmappedMaterials) {
      console.error('引擎侧有错误诊断，渲染结果不可用于评价')
      return 1
    }
    const blank = written.filter((shot) => shot.bytes < 2000)
    if (!written.length || blank.length) {
      console.error(`渲染失败：${blank.length} 张图空/近空（${blank.map((s) => s.view).join(',')}）`)
      return 1
    }
    return 0
  } finally {
    child?.kill()
    await server.close()
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exit(await main())
}