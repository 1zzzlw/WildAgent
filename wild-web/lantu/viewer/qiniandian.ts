import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { parseWildBlueprint, reconstructWildEntity } from '../../src/renderer/wildCoreAdapter'
import { BlueprintRenderInstance } from '../../src/renderer/blueprintRenderInstance'
// 直接内嵌祈年殿蓝图，构建后成为自包含单文件，双击打开即渲染（不依赖 /bp 服务）。
import qiniandianRaw from '../qiniandian.wild?raw'

// 渲染器 / 场景
const app = document.getElementById('app') as HTMLElement
let renderer: THREE.WebGLRenderer
try {
  renderer = new THREE.WebGLRenderer({ antialias: true })
} catch (err) {
  const loading = document.getElementById('loading') as HTMLElement
  loading.textContent = `当前环境不支持 WebGL，无法渲染 3D 场景。请用 Chrome / Edge 打开此文件。`
  throw err
}
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
controls.autoRotate = true
controls.autoRotateSpeed = 0.9
controls.target.set(0, 4, 0)

let instance: BlueprintRenderInstance | null = null

function frameToBox(box: { min: number[]; max: number[] }): void {
  const min = new THREE.Vector3().fromArray(box.min)
  const max = new THREE.Vector3().fromArray(box.max)
  const size = max.clone().sub(min)
  const radius = size.length() * 0.5 || 10

  // 足迹居中归一化（生成器产出的是角点对齐坐标，祈年殿本身已是中心对齐，平移≈0）。
  instance?.setTransform({ position: [-(min.x + max.x) / 2, 0, -(min.z + max.z) / 2] })

  const center = new THREE.Vector3(0, (min.y + max.y) / 2, 0)
  controls.target.copy(center)
  const dist = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.4
  const dir = new THREE.Vector3(1, 0.72, 1.3).normalize()
  camera.position.copy(center).add(dir.multiplyScalar(dist))
  camera.near = Math.max(0.1, dist - radius * 4)
  camera.far = dist + radius * 8
  camera.updateProjectionMatrix()

  ground.position.y = min.y
  grid.position.y = min.y + 0.001

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

function renderStats(bp: any, entity: any, meshCount: number): void {
  const stats = document.getElementById('stats') as HTMLElement
  const bb = entity.boundingBox
  const dims = bb
    ? [bb.max[0] - bb.min[0], bb.max[1] - bb.min[1], bb.max[2] - bb.min[2]]
        .map((v: number) => v.toFixed(2))
        .join(' × ')
    : '-'
  const rows: Array<[string, string]> = [
    ['构件', `${bp.geometry?.elements?.length ?? 0} 基础 + ${bp.geometry?.components?.length ?? 0} 组合`],
    ['网格', String(meshCount)],
    ['材质', String(Object.keys(bp.materials ?? {}).length)],
    ['包围盒', `${dims} m`],
  ]
  stats.innerHTML = ''
  for (const [k, v] of rows) {
    const line = document.createElement('div')
    const key = document.createElement('span')
    key.className = 'k'
    key.textContent = `${k}：`
    const val = document.createElement('span')
    val.className = 'v'
    val.textContent = v
    line.append(key, val)
    stats.appendChild(line)
  }

  const diagnostics: any[] = entity.diagnostics ?? []
  const errors = diagnostics.filter((d) => d.level === 'error')
  const pill = document.getElementById('pill') as HTMLElement
  if (errors.length === 0) pill.style.display = 'inline-flex'
}

async function load(): Promise<void> {
  const loading = document.getElementById('loading') as HTMLElement
  try {
    const bp = parseWildBlueprint(qiniandianRaw)
    const entity = await reconstructWildEntity(bp)
    instance = new BlueprintRenderInstance('qiniandian-single')
    instance.update(entity)
    scene.add(instance.root)

    let meshCount = 0
    instance.root.traverse((obj) => {
      if ((obj as THREE.Mesh).isMesh) meshCount += 1
    })

    if (entity.boundingBox) frameToBox(entity.boundingBox)
    renderStats(bp, entity, meshCount)
    loading.style.display = 'none'
  } catch (err: any) {
    loading.textContent = `解析 / 重建失败：${err?.message ?? err}`
  }
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

load()
animate()
