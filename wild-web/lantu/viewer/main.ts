import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { parseWildBlueprint, reconstructWildEntity } from '../../src/renderer/wildCoreAdapter'
import { BlueprintRenderInstance } from '../../src/renderer/blueprintRenderInstance'

// ─────────────────────────────────────────────────────────────
// 为什么走 wildCoreAdapter + BlueprintRenderInstance 而不是自己拼：
//
// 这两个入口就是编辑器视口用的同一条链路（wild-core 解析 → wild-compiler
// 展开组合构件 → renderEntity 建网格/材质）。查看器的价值在于"看到引擎真实
// 产出"，所以这里**不允许**出现第二套材质或网格构造实现——一旦有，两个界面
// 的差异就不再能代表引擎行为，而只是本地代码的差异。
//
// wildCoreAdapter.reconstructWildEntity 会把「组件编译诊断 + 重建诊断 + core
// 诊断」合并进 entity.diagnostics，所以不需要再单独调一次 compileBlueprintComponents。
// BlueprintRenderInstance 负责材质作用域与几何释放，切换蓝图时 dispose 即可。
// ─────────────────────────────────────────────────────────────

interface BlueprintEntry {
  name: string
  file: string
}

// 位于 wild-web/lantu/。新生成的别墅放第一位；其余为项目历史样例。
const BLUEPRINTS: BlueprintEntry[] = [
  { name: '现代双层别墅 · 知识库生成（12×9）', file: 'villa_modern_2f.wild' },
  { name: '现代双层别墅 · 旧样例（11×8）', file: 'generated_modern_villa.wild' },
  { name: '新中式别墅', file: '1.wild' },
  { name: '别墅 · bieshu', file: 'bieshu.wild' },
  { name: '天坛 · tiantan', file: 'tiantan.wild' },
  { name: '小木屋 · cabin', file: 'cabin_v1.wild' },
  { name: '篮球场 · basketball', file: 'basketball_v1_1.wild' },
  { name: '檐口 · eave_extension', file: 'eave_extension_v1_1.wild' },
]

// ── 渲染器 / 场景 ────────────────────────────────────────────
const app = document.getElementById('app') as HTMLElement
const renderer = new THREE.WebGLRenderer({ antialias: true })
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.shadowMap.enabled = true
renderer.shadowMap.type = THREE.PCFSoftShadowMap
renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.toneMappingExposure = 1.05
renderer.outputColorSpace = THREE.SRGBColorSpace
app.appendChild(renderer.domElement)

const scene = new THREE.Scene()
scene.background = new THREE.Color(0x0e1116)

scene.add(new THREE.HemisphereLight(0xbfd4ff, 0x46413a, 0.9))
scene.add(new THREE.AmbientLight(0xffffff, 0.25))

const sun = new THREE.DirectionalLight(0xfff4e6, 2.2)
sun.castShadow = true
sun.shadow.mapSize.set(2048, 2048)
sun.shadow.bias = -0.0004
scene.add(sun)

const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(400, 400),
  new THREE.MeshStandardMaterial({ color: 0x262b33, roughness: 1, metalness: 0 }),
)
ground.rotation.x = -Math.PI / 2
ground.receiveShadow = true
scene.add(ground)

const grid = new THREE.GridHelper(400, 200, 0x3a4150, 0x2c313b)
scene.add(grid)

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 2000)
camera.position.set(20, 16, 24)
const controls = new OrbitControls(camera, renderer.domElement)
controls.enableDamping = true
controls.dampingFactor = 0.08
// 初始取景中心必须是"归一化之后的建筑中心"。建筑在加载时会被足迹居中到原点，
// 所以这里写死任何某份蓝图的具体中心（历史上写过 (5.5, 3, 3)）都会让加载前的
// 默认视角指向不存在的位置。
controls.target.set(0, 3, 0)

// 当前蓝图实例。切换时 dispose 释放几何与材质作用域。
let instance: BlueprintRenderInstance | null = null
// 楼层隔离：每个网格的可见性由它自身的世界 Y 包围盒决定，`visibleMeshes` 记下
// 全部网格，切楼层时重新求值，避免"过滤后无法恢复"。
let allMeshes: THREE.Object3D[] = []
let levelBands: Array<{ label: string; lo: number; hi: number }> = []

// ── 光影随包围盒缩放 ─────────────────────────────────────────
// 固定 ±26 的正交阴影框在 12m 别墅上尚可，但在跨度更大的蓝图上要么把建筑
// 切掉、要么让阴影精度浪费在空白区。按足迹半对角线推导。
function updateShadowExtent(radius: number): void {
  const extent = Math.max(14, radius * 1.5)
  sun.shadow.camera.left = -extent
  sun.shadow.camera.right = extent
  sun.shadow.camera.top = extent
  sun.shadow.camera.bottom = -extent
  sun.shadow.camera.near = 1
  sun.shadow.camera.far = extent * 6 + 40
  sun.shadow.camera.updateProjectionMatrix()
  const d = extent * 1.6
  sun.position.set(d, d * 1.5, d * 0.75).normalize().multiplyScalar(d * 1.6)
}

// ── 取景 ─────────────────────────────────────────────────────
function frameToBox(box: { min: number[]; max: number[] }): void {
  const min = new THREE.Vector3().fromArray(box.min)
  const max = new THREE.Vector3().fromArray(box.max)
  const size = max.clone().sub(min)
  const radius = size.length() * 0.5 || 10

  // 足迹居中归一化：生成器产出的是"角点对齐"坐标（x 从 0 到 12，而非 -6 到 6），
  // 而地面与网格钉在世界原点 ⇒ 不平移建筑就会偏离网格中心。
  // 只平移 X/Z；Y 不动，因为地面高度是设计值。
  instance?.setTransform({ position: [-(min.x + max.x) / 2, 0, -(min.z + max.z) / 2] })

  const center = new THREE.Vector3(0, (min.y + max.y) / 2, 0)
  controls.target.copy(center)
  const dist = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.4
  const dir = new THREE.Vector3(1, 0.72, 1.3).normalize()
  camera.position.copy(center).add(dir.multiplyScalar(dist))
  camera.near = Math.max(0.1, dist - radius * 4)
  camera.far = dist + radius * 8
  camera.updateProjectionMatrix()

  // 地面/网格贴建筑自身地面：用包围盒底面而不是写死的 -0.3
  // （不同蓝图的楼板厚度不同，写死会让建筑悬空或陷入地面）。
  ground.position.y = min.y
  grid.position.y = min.y + 0.001
  updateShadowExtent(radius)
}

// ── 楼层隔离 ─────────────────────────────────────────────────
// 楼层标高取自蓝图里的 floor 元素（楼板），而不是猜层高。
function buildLevelBands(bp: any, bbMinY: number, bbMaxY: number): void {
  const levels: number[] = []
  for (const el of bp.geometry?.elements ?? []) {
    if (el.type === 'floor' && Array.isArray(el.from) && Number.isFinite(el.from[1])) {
      levels.push(Number(el.from[1]))
    }
  }
  const unique = [...new Set(levels)].sort((a, b) => a - b)
  const bands: Array<{ label: string; lo: number; hi: number }> = []
  const lo = Math.min(bbMinY, unique[0] ?? bbMinY)
  if (unique.length >= 2) {
    for (let i = 0; i < unique.length; i += 1) {
      const bandLo = i === 0 ? lo : unique[i]
      const bandHi = i === unique.length - 1 ? bbMaxY + 1 : unique[i + 1]
      bands.push({
        label:
          i === unique.length - 1
            ? `第 ${i + 1} 层（${bandLo.toFixed(2)}m 以上，含屋顶）`
            : `第 ${i + 1} 层（${bandLo.toFixed(2)} ~ ${unique[i + 1].toFixed(2)}m）`,
        lo: bandLo,
        hi: bandHi,
      })
    }
  }
  levelBands = bands
}

function applyLevelFilter(index: number): void {
  const band = index > 0 ? levelBands[index - 1] : null
  for (const mesh of allMeshes) {
    if (!band) {
      mesh.visible = true
      continue
    }
    const box = new THREE.Box3().setFromObject(mesh)
    // 与楼层区间有交叠即显示（屋顶跨越二层与屋脊，会整体留在顶层）
    mesh.visible = box.max.y > band.lo + 1e-6 && box.min.y < band.hi - 1e-6
  }
}

function populateLevelSelect(): void {
  const sel = document.getElementById('level') as HTMLSelectElement
  sel.innerHTML = ''
  const all = document.createElement('option')
  all.value = '0'
  all.textContent = '全部楼层'
  sel.appendChild(all)
  levelBands.forEach((band, i) => {
    const opt = document.createElement('option')
    opt.value = String(i + 1)
    opt.textContent = band.label
    sel.appendChild(opt)
  })
  sel.disabled = levelBands.length === 0
  sel.onchange = () => applyLevelFilter(Number(sel.value))
}

// ── 面板渲染 ─────────────────────────────────────────────────
function el(tag: string, className?: string): HTMLElement {
  const node = document.createElement(tag)
  if (className) node.className = className
  return node
}

function row(parent: HTMLElement, key: string, value: string, mono = false): void {
  const line = el('div')
  const k = el('span', 'k')
  k.textContent = `${key}：`
  const v = el('span', `v${mono ? ' mono' : ''}`)
  v.textContent = value
  line.append(k, v)
  parent.appendChild(line)
}

function pill(text: string, kind: 'ok' | 'warn' | 'err'): HTMLElement {
  const node = el('span', `pill ${kind}`)
  node.textContent = text
  return node
}

function renderPanel(label: string, bp: any, entity: any, meshCount: number): void {
  const stats = document.getElementById('stats') as HTMLElement
  stats.innerHTML = ''

  const bb = entity.boundingBox
  const dims = bb
    ? [bb.max[0] - bb.min[0], bb.max[1] - bb.min[1], bb.max[2] - bb.min[2]]
        .map((v: number) => v.toFixed(2))
        .join(' × ')
    : '-'

  row(stats, '名称', bp.meta?.name ?? label)
  row(stats, '类型', `${bp.meta?.type ?? '-'} · WILD ${bp.meta?.version ?? '-'}`)
  row(stats, '网格', String(meshCount))
  row(stats, '基础构件', String(bp.geometry?.elements?.length ?? 0))
  row(stats, '组合构件', String(bp.geometry?.components?.length ?? 0))
  row(stats, '材质', String(Object.keys(bp.materials ?? {}).length))
  row(stats, '包围盒 X·Y·Z', `${dims} m`, true)

  const diagnostics: any[] = entity.diagnostics ?? []
  const errors = diagnostics.filter((d) => d.level === 'error')
  const warnings = diagnostics.filter((d) => d.level === 'warning')

  const status = el('div')
  status.style.marginTop = '8px'
  if (errors.length > 0) {
    status.appendChild(pill(`错误 ${errors.length}`, 'err'))
  } else if (warnings.length > 0) {
    status.appendChild(pill(`通过 · 警告 ${warnings.length}`, 'warn'))
  } else {
    status.appendChild(pill('引擎诊断全部通过', 'ok'))
  }
  stats.appendChild(status)

  if (diagnostics.length > 0) {
    const details = el('details') as HTMLDetailsElement
    if (errors.length > 0) details.open = true
    const summary = el('summary')
    summary.textContent = `诊断明细（${diagnostics.length}）`
    details.appendChild(summary)

    const list = el('ul', 'diag-list')
    const ordered = [...errors, ...warnings, ...diagnostics.filter(
      (d) => d.level !== 'error' && d.level !== 'warning',
    )]
    for (const d of ordered) {
      const item = el('li', d.level === 'error' ? 'err' : 'warn')
      if (d.elementId) {
        const idLine = el('span', 'diag-el')
        idLine.textContent = d.elementId
        item.appendChild(idLine)
      }
      // 用 textContent 而不是 innerHTML：诊断消息来自蓝图内容，不该被当标记解析
      item.appendChild(document.createTextNode(d.message ?? String(d)))
      list.appendChild(item)
    }
    details.appendChild(list)
    stats.appendChild(details)
  }
}

function renderMessage(html: string, kind: 'warn' | 'err'): void {
  const stats = document.getElementById('stats') as HTMLElement
  stats.innerHTML = ''
  const node = el('div', kind)
  node.textContent = html
  stats.appendChild(node)
}

// ── 加载 ─────────────────────────────────────────────────────
async function loadBlueprintText(text: string, label: string): Promise<void> {
  renderMessage('正在编译并重建…', 'warn')
  // 让浏览器先把这个中间态画出来，否则同步的解析/编译会把界面卡住
  await new Promise((resolve) => requestAnimationFrame(resolve))

  let entity: any
  let bp: any
  try {
    bp = parseWildBlueprint(text)
    // 注意：reconstructWildEntity 内部会自行 compileBlueprintComponents，
    // 且会把渲染私有字段原地写进它自己那份编译产物。这里不要重复编译。
    entity = await reconstructWildEntity(bp)
  } catch (err: any) {
    renderMessage(`解析 / 重建失败：${err?.message ?? err}`, 'err')
    return
  }

  // 替换实例：先释放旧几何与材质作用域，再建新的
  if (instance) {
    scene.remove(instance.root)
    instance.dispose()
  }
  instance = new BlueprintRenderInstance(`viewer-${Date.now()}`)
  instance.update(entity)
  scene.add(instance.root)

  // 逐网格的可见性由楼层过滤决定，先收集
  allMeshes = []
  instance.root.traverse((obj) => {
    if ((obj as THREE.Mesh).isMesh) allMeshes.push(obj)
  })
  // 线框开关改的是共享的缓存材质，切蓝图时要显式复位，否则会残留
  const wireBox = document.getElementById('wire') as HTMLInputElement
  for (const mesh of allMeshes) {
    const mats = Array.isArray((mesh as THREE.Mesh).material)
      ? ((mesh as THREE.Mesh).material as THREE.Material[])
      : [(mesh as THREE.Mesh).material as THREE.Material]
    for (const m of mats) (m as any).wireframe = wireBox.checked
  }

  const bb = entity.boundingBox
  if (bb) {
    buildLevelBands(bp, bb.min[1], bb.max[1])
    frameToBox(bb)
  }
  populateLevelSelect()
  applyLevelFilter(0)
  renderPanel(label, bp, entity, allMeshes.length)
}

async function loadByFile(file: string, label: string): Promise<void> {
  try {
    const res = await fetch(`/bp/${encodeURIComponent(file)}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await loadBlueprintText(await res.text(), label)
  } catch (err: any) {
    renderMessage(`加载失败：${err?.message ?? err}`, 'err')
  }
}

// ── UI 绑定 ──────────────────────────────────────────────────
function initUI(): void {
  const sel = document.getElementById('bp') as HTMLSelectElement
  BLUEPRINTS.forEach((b, i) => {
    const opt = document.createElement('option')
    opt.value = b.file
    opt.textContent = b.name
    if (i === 0) opt.selected = true
    sel.appendChild(opt)
  })
  sel.addEventListener('change', () => {
    const entry = BLUEPRINTS.find((x) => x.file === sel.value)
    if (entry) loadByFile(entry.file, entry.name)
  })

  const fileInput = document.getElementById('file') as HTMLInputElement
  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => loadBlueprintText(String(reader.result), file.name)
    reader.onerror = () => renderMessage('读取本地文件失败。', 'err')
    reader.readAsText(file)
  })

  const spin = document.getElementById('spin') as HTMLInputElement
  spin.addEventListener('change', () => {
    controls.autoRotate = spin.checked
    controls.autoRotateSpeed = 1.2
  })

  const wire = document.getElementById('wire') as HTMLInputElement
  wire.addEventListener('change', () => {
    for (const mesh of allMeshes) {
      const m = (mesh as THREE.Mesh).material
      const mats = Array.isArray(m) ? m : [m]
      for (const mat of mats) (mat as any).wireframe = wire.checked
    }
  })

  const gridToggle = document.getElementById('gridToggle') as HTMLInputElement
  gridToggle.addEventListener('change', () => {
    grid.visible = gridToggle.checked
    ground.visible = gridToggle.checked
  })
}

function animate(): void {
  requestAnimationFrame(animate)
  controls.update()
  renderer.render(scene, camera)
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
})

initUI()
animate()
loadByFile(BLUEPRINTS[0].file, BLUEPRINTS[0].name)
