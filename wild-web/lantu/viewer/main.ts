import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { parseBlueprint, reconstructEntity } from 'wild-core'
import { compileBlueprintComponents } from 'wild-compiler'
import { meshDataToGeometry } from '../../src/renderer/meshDataToGeometry'

// 项目中已有的蓝图样例（位于 wild-web/lantu/）
const BLUEPRINTS = [
  { name: '现代双层别墅（本次生成）', file: 'generated_modern_villa.wild' },
  { name: '新中式别墅 (1.wild)', file: '1.wild' },
  { name: '别墅 (bieshu)', file: 'bieshu.wild' },
  { name: '天坛 (tiantan)', file: 'tiantan.wild' },
  { name: '小木屋 (cabin)', file: 'cabin_v1.wild' },
  { name: '篮球 (basketball)', file: 'basketball_v1_1.wild' },
  { name: '檐口 (eave_extension)', file: 'eave_extension_v1_1.wild' },
]

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

const hemi = new THREE.HemisphereLight(0xbfd4ff, 0x46413a, 0.9)
scene.add(hemi)
const sun = new THREE.DirectionalLight(0xfff4e6, 2.2)
sun.position.set(16, 24, 12)
sun.castShadow = true
sun.shadow.mapSize.set(2048, 2048)
sun.shadow.camera.near = 1
sun.shadow.camera.far = 90
const s = 26
sun.shadow.camera.left = -s
sun.shadow.camera.right = s
sun.shadow.camera.top = s
sun.shadow.camera.bottom = -s
sun.shadow.bias = -0.0004
scene.add(sun)
scene.add(new THREE.AmbientLight(0xffffff, 0.25))

const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(240, 240),
  new THREE.MeshStandardMaterial({ color: 0x262b33, roughness: 1, metalness: 0 }),
)
ground.rotation.x = -Math.PI / 2
ground.position.y = -0.3
ground.receiveShadow = true
scene.add(ground)
const grid = new THREE.GridHelper(240, 120, 0x3a4150, 0x2c313b)
grid.position.y = -0.299
scene.add(grid)

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 600)
camera.position.set(20, 16, 24)
const controls = new OrbitControls(camera, renderer.domElement)
controls.enableDamping = true
controls.dampingFactor = 0.08
controls.target.set(5.5, 3, 3)

const sceneGroup = new THREE.Group()
scene.add(sceneGroup)
let currentMaterials: THREE.Material[] = []

function makeMaterial(p: any): THREE.Material {
  if (!p) return new THREE.MeshStandardMaterial({ color: 0x888888 })
  const isGlass = p.materialClass === 'glass' || (p.transmission ?? 0) > 0
  const mat = isGlass ? new THREE.MeshPhysicalMaterial() : new THREE.MeshStandardMaterial()
  const [r, g, b] = p.baseColor
  mat.color = new THREE.Color().setRGB(r, g, b, THREE.SRGBColorSpace).multiplyScalar(p.albedo ?? 1)
  mat.roughness = p.roughness ?? 0.8
  mat.metallic = p.metallic ?? 0
  if (isGlass) {
    mat.transmission = p.transmission ?? 0.9
    mat.ior = p.ior ?? 1.5
    mat.thickness = p.thickness ?? 0.012
    mat.roughness = Math.min(mat.roughness, 0.15)
    mat.transparent = true
  } else if (p.opacity !== undefined && p.opacity < 0.99) {
    mat.transparent = true
    mat.opacity = p.opacity
    mat.depthWrite = false
  }
  if (p.emissive) {
    const [er, eg, eb] = p.emissive
    mat.emissive = new THREE.Color().setRGB(er, eg, eb, THREE.SRGBColorSpace)
    mat.emissiveIntensity = p.emissiveIntensity ?? 1
  }
  mat.side = THREE.DoubleSide
  return mat
}

function clearScene(): void {
  for (const child of [...sceneGroup.children]) {
    sceneGroup.remove(child)
    child.traverse((obj: any) => {
      if (obj.geometry) obj.geometry.dispose()
    })
  }
  for (const m of currentMaterials) m.dispose()
  currentMaterials = []
}

function frameToBox(box: any): void {
  const min = new THREE.Vector3(...box.min)
  const max = new THREE.Vector3(...box.max)
  const center = min.clone().add(max).multiplyScalar(0.5)
  const size = max.clone().sub(min)
  const radius = size.length() * 0.5 || 10
  controls.target.copy(center)
  const dist = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.4
  const dir = new THREE.Vector3(1, 0.8, 1.3).normalize()
  camera.position.copy(center).add(dir.multiplyScalar(dist))
  camera.near = Math.max(0.1, dist - radius * 4)
  camera.far = dist + radius * 8
  camera.updateProjectionMatrix()
}

async function loadBlueprintText(text: string, label: string): Promise<void> {
  const bp: any = parseBlueprint(text)
  const compile = compileBlueprintComponents(bp)
  const entity: any = await reconstructEntity(compile.blueprint)
  clearScene()
  entity.meshes.forEach((meshData: any, i: number) => {
    const geo = meshDataToGeometry(meshData)
    const mat = makeMaterial(entity.materialParams[i])
    currentMaterials.push(mat)
    const mesh = new THREE.Mesh(geo, mat)
    const { position, rotation, scale } = meshData.transform
    mesh.position.set(position[0], position[1], position[2])
    mesh.rotation.set(rotation[0], rotation[1], rotation[2])
    mesh.scale.set(scale[0], scale[1], scale[2])
    mesh.castShadow = true
    mesh.receiveShadow = true
    sceneGroup.add(mesh)
  })
  frameToBox(entity.boundingBox)
  renderStats(label, bp, compile, entity)
}

function renderStats(label: string, bp: any, compile: any, entity: any): void {
  const stats = document.getElementById('stats') as HTMLElement
  const cmpErr = compile.diagnostics.filter((d: any) => d.level === 'error').length
  const cmpWarn = compile.diagnostics.filter((d: any) => d.level === 'warning').length
  const recErr = entity.diagnostics.filter((d: any) => d.level === 'error')
  const recWarn = entity.diagnostics.filter((d: any) => d.level === 'warning')
  const min = entity.boundingBox.min
  const max = entity.boundingBox.max
  const dims = [max[0] - min[0], max[1] - min[1], max[2] - min[2]].map((v: number) => v.toFixed(2))
  const errLine =
    recErr.length === 0
      ? `<span class="ok">组件编译 0 错误 · 重建 0 错误</span>`
      : `<span class="err">错误 ${cmpErr + recErr.length}：${recErr
          .slice(0, 5)
          .map((d: any) => `#${d.elementId}: ${d.message}`)
          .join(' ; ')}</span>`
  stats.innerHTML = `
    <div>名称：<b>${bp.meta?.name ?? label}</b></div>
    <div>类型 / 版本：<b>${bp.meta?.type ?? '-'}</b> · WILD ${bp.meta?.version ?? '-'}</div>
    <div>构件数：<b>${entity.meshes.length}</b> 网格 / <b>${entity.materialParams.length}</b> 材质</div>
    <div>包围盒尺寸 (X·Y·Z)：<b>${dims.join(' × ')}</b> m</div>
    <div class="${recErr.length === 0 ? 'ok' : 'err'}">组件编译诊断：${compile.diagnostics.length}（错误 ${cmpErr} / 警告 ${cmpWarn}）</div>
    <div class="${recErr.length === 0 ? 'ok' : 'err'}">重建诊断：错误 ${recErr.length} / 警告 ${recWarn.length}</div>
    <div>${errLine}</div>
  `
}

async function loadByFile(file: string, label: string): Promise<void> {
  const stats = document.getElementById('stats') as HTMLElement
  stats.innerHTML = '<div class="warn">正在加载并重建…</div>'
  try {
    const res = await fetch(`/bp/${encodeURIComponent(file)}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const text = await res.text()
    await loadBlueprintText(text, label)
  } catch (e: any) {
    stats.innerHTML = `<div class="err">加载失败：${e?.message ?? e}</div>`
  }
}

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
    const b = BLUEPRINTS.find((x) => x.file === sel.value)
    if (b) loadByFile(b.file, b.name)
  })
  const fileInput = document.getElementById('file') as HTMLInputElement
  fileInput.addEventListener('change', () => {
    const f = fileInput.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => loadBlueprintText(String(reader.result), f.name)
    reader.readAsText(f)
  })
  const spin = document.getElementById('spin') as HTMLInputElement
  spin.addEventListener('change', () => {
    controls.autoRotate = spin.checked
    controls.autoRotateSpeed = 1.2
  })
  const wire = document.getElementById('wire') as HTMLInputElement
  wire.addEventListener('change', () => {
    for (const m of currentMaterials) (m as any).wireframe = wire.checked
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
