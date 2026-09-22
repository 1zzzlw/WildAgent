import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { Sky } from 'three/examples/jsm/objects/Sky.js'
import { parseWildBlueprint, reconstructWildEntity } from '../../src/renderer/wildCoreAdapter'
import { BlueprintRenderInstance } from '../../src/renderer/blueprintRenderInstance'
import {
  createCelestialBody,
  syncSkyPreset,
  WorldEnvironmentMapRuntime,
} from '../../src/renderer/environmentRuntime'
import { WorldLightingRig } from '../../src/renderer/lightingRuntime'
import { WorldPostProcessingRuntime } from '../../src/renderer/postProcessingRuntime'
import {
  ENVIRONMENT_PRESETS,
  TIME_PRESETS,
} from '../../src/renderer/defaultWorldLook'
import type { TimePreset } from '../../src/renderer/defaultWorldLook'
import { deriveWorldAtmosphere } from '../../src/renderer/worldWeatherRuntime'
import {
  getWorldEnvironmentState,
  getWorldRenderingState,
} from '../../src/renderer/worldEnvironmentRuntime'

// ─────────────────────────────────────────────────────────────
// 为什么走 wildCoreAdapter + BlueprintRenderInstance 而不是自己拼：
//
// 这两个入口就是编辑器视口用的同一条链路（wild-core 解析 → 编译器展开组合
// 构件 → renderEntity 建网格/材质）。查看器的价值在于"看到引擎真实产出"，
// 所以这里**不允许**出现第二套材质或网格构造实现——一旦有，两个界面的差异
// 就不再能代表引擎行为，而只是本地代码的差异。
//
// wildCoreAdapter.reconstructWildEntity 会把「组件编译诊断 + 重建诊断 + core
// 诊断」合并进 entity.diagnostics，所以不需要再单独调一次 compileBlueprintComponents。
// BlueprintRenderInstance 负责材质作用域与几何释放，切换蓝图时 dispose 即可。
//
// 本文件只加**观察工具**（构件包围盒、曝光、楼层隔离），不碰几何与材质。
// ─────────────────────────────────────────────────────────────

interface BlueprintEntry {
  name: string
  file: string
}

// 位于 wild-web/lantu/。这里只列**当前工作集**里的蓝图；新做的逐份加进来。
const BLUEPRINTS: BlueprintEntry[] = [
  { name: '热带现代泳池别墅 · 照片还原（12×9）', file: 'modern_pool_villa.wild' },
]

// ── URL 取景参数（只服务于"可复现的截图"，不是渲染功能）─────────
// 为什么需要：离线软件光栅化器只能给几何体检，给不了真实光影；而真实光影必须
// 在真浏览器里看。要让"A 方案 vs B 方案"可比，取景就必须是**写死可复现**的，
// 不能靠手拖。故把机位做成 URL 参数，截图脚本直接拼。
//
//   ?cam=pool|front|aerial|iso|back|top   视角（默认 pool）
//   ?time=day|sunset|night                 时段（默认 day，走引擎 TIME_PRESETS）
//   ?env=minimal|meadow|alpine|desert|autumn  环境档（默认 minimal，走引擎 ENVIRONMENT_PRESETS）
//   ?exp=1.25                              曝光
//   ?panel=0                               隐藏左侧面板（出干净图）
//   ?grid=0                                隐藏网格地面（看悬空）
//   ?bbox=1                                打开构件包围盒
const QS = new URLSearchParams(location.search)
const qsNum = (key: string, fallback: number): number => {
  const raw = QS.get(key)
  if (raw === null) return fallback
  const value = Number(raw)
  return Number.isFinite(value) ? value : fallback
}

// 方向 = 相机相对建筑中心的**单位方向**（乘上自动求得的距离）。
// ⚠️ 本蓝图的泳池在 **−Z** 侧、正立面朝 −Z；从 −Z 看过去时屏幕右 = −X，
//    所以 +X 侧的门廊体量会出现在**画面左**——这正是照片里的关系。
const CAM_DIRS: Record<string, [number, number, number]> = {
  pool: [0.62, 0.30, -1.0],
  front: [0, 0.24, -1.0],
  aerial: [0.85, 1.25, -1.05],
  iso: [1, 0.72, 1.3],
  back: [0, 0.42, 1.0],
  top: [0.001, 1, 0.001],
}
const qsCam = QS.get('cam') ?? 'pool'
/** 当前机位名。resize 时要按它重算取景距离（依赖 aspect） */
let currentCam = CAM_DIRS[qsCam] ? qsCam : 'pool'
const CAM_DIR = CAM_DIRS[currentCam]

// ── 渲染器 / 场景 ────────────────────────────────────────────
const app = document.getElementById('app') as HTMLElement
const renderer = new THREE.WebGLRenderer({ antialias: false })
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.shadowMap.enabled = true
renderer.shadowMap.type = THREE.PCFSoftShadowMap
// 静态场景：阴影只在内容/光照变化时重算（与编辑器视口一致）。
renderer.shadowMap.autoUpdate = false
renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.toneMappingExposure = 1.05
renderer.outputColorSpace = THREE.SRGBColorSpace
app.appendChild(renderer.domElement)

const scene = new THREE.Scene()

// ── 光照与环境：**全部来自引擎运行时** ─────────────────────────
// 这里刻意不再自己 new 光源，也不再自己造环境光。原因见环境运行时的文件头：
// 引擎的材质层（玻璃 transmission / 金属 envMapIntensity）是按"存在 scene.environment"
// 设计的，查看器一旦自搭光照，看到的就不是引擎行为，而是本地代码的行为。
const lightingRig = new WorldLightingRig(scene, { shadowMapSize: 2048 })
const sun = lightingRig.key
const environmentRuntime = new WorldEnvironmentMapRuntime(renderer, scene, {
  onRebuilt: () => {
    renderer.shadowMap.needsUpdate = true
  },
})
// 天空穹顶：与编辑器视口同一套时段预设 + 大气改写。
const sky = new Sky()
sky.scale.setScalar(450)
scene.add(sky)
const sunBody = createCelestialBody('sun')
const moonBody = createCelestialBody('moon')
scene.add(sunBody, moonBody)

// 时段 / 环境档：默认白天 + 极简，与编辑器默认一致；可用 URL 覆盖以便固定复现。
const TIME_IDS = ['day', 'sunset', 'night'] as const
const ENV_IDS = ['minimal', 'meadow', 'alpine', 'desert', 'autumn'] as const
const qsTime = QS.get('time') ?? 'day'
const qsEnv = QS.get('env') ?? 'minimal'
const timeOfDay: (typeof TIME_IDS)[number] = (TIME_IDS as readonly string[]).includes(qsTime)
  ? (qsTime as (typeof TIME_IDS)[number])
  : 'day'
const environmentId: (typeof ENV_IDS)[number] = (ENV_IDS as readonly string[]).includes(qsEnv)
  ? (qsEnv as (typeof ENV_IDS)[number])
  : 'minimal'
/** 关键光方向（夜晚取月亮方向，与编辑器同规则）。 */
const keyLightDirection = new THREE.Vector3(0, 1, 0)

const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(400, 400),
  new THREE.MeshStandardMaterial({ color: 0x262b33, roughness: 1, metalness: 0 }),
)
ground.rotation.x = -Math.PI / 2
ground.receiveShadow = true
scene.add(ground)

const grid = new THREE.GridHelper(400, 200, 0x3a4150, 0x2c313b)
scene.add(grid)

// 构件包围盒：只在需要判"蓝图还是引擎"时打开。
const bboxGroup = new THREE.Group()
scene.add(bboxGroup)

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 2000)
camera.position.set(20, 16, 24)
const controls = new OrbitControls(camera, renderer.domElement)
controls.enableDamping = true
controls.dampingFactor = 0.08
// 初始取景中心必须是"归一化之后的建筑中心"。建筑在加载时会被足迹居中到原点，
// 所以这里写死任何某份蓝图的具体中心（历史上写过 (5.5, 3, 3)）都会让加载前的
// 默认视角指向不存在的位置。
controls.target.set(0, 3, 0)

// 后期合成链路（SSAO 接触阴影 / Bloom / FXAA / MSAA）—— 与编辑器同一套。
// 用 antialias:false + 合成 RT 的 MSAA，理由见 postProcessingRuntime 的文件头。
// ⚠️ 这里刻意**不再传 kernelRadius/minDistance/maxDistance**：这三个量的取值属于
// 引擎行为（接触阴影能压到多大的交界），传进来就等于查看器自己又定了一套。
// 之前两边恰好写了同样的数，所以看不出问题；一旦引擎侧调了半径，
// 查看器会静默停在旧值上 —— 正是 S0 之前"两套光影"的老毛病。
const postProcessing = new WorldPostProcessingRuntime(renderer, scene, camera, {
  msaaSamples: 4,
})
postProcessing.setSize(window.innerWidth, window.innerHeight)

// 当前蓝图实例。切换时 dispose 释放几何与材质作用域。
let instance: BlueprintRenderInstance | null = null
// 楼层隔离：每个网格的可见性由它自身的世界 Y 包围盒决定，`allMeshes` 记下
// 全部网格，切楼层时重新求值，避免"过滤后无法恢复"。
let allMeshes: THREE.Object3D[] = []
let levelBands: Array<{ label: string; lo: number; hi: number }> = []

// ── 时段 / 环境：与编辑器同一套策略，只是没有 UI ──────────────
// 太阳方向、主光方向、天空 uniform、环境贴图、曝光、光照强度全部按引擎预设推导，
// 所以"查看器出的图"与"编辑器视口看到的"是同一套光照，而不是两套近似。
//
// 标定倍率：曝光/主光/半球光的临时倍率，只服务标定脚本与 `?exp=` 这类截图覆盖。
// 之所以做成"倍率"而不是"绝对值"，是为了让 applyTimeAppearance() 可以反复调用
// （`setLook()` 会重跑它），否则一次绝对覆盖会在下次调用时被引擎预设抹掉 ——
// 那正是改造前 `?exp=` 的行为：它写的是绝对曝光，且只在启动时写一次。
let exposureOverride: number | null = null
let keyScale = 1
let hemisphereScale = 1
/**
 * 天空散射参数覆盖（标定用）。
 *
 * `rayleigh` / `turbidity` 直接决定天空**色相与亮度**，而天空同时是可见背景
 * 与 IBL 的光源，所以"哪个值才是天蓝"不能靠读 three 的文档猜 —— 官方示例给的
 * rayleigh 3 是"银河/黄昏"取向，套到正午会把天洗成灰白（实测 B−R 从 19 掉到 10）。
 * 这里留一个覆盖口，让标定脚本能在一轮里把 (rayleigh, turbidity) 扫完。
 */
let skyOverrides: { rayleigh?: number; turbidity?: number; mieCoefficient?: number } = {}

// 首帧必须无条件建好环境贴图与光照外观。
// ⚠️ 这一句的位置**不能**上移到这几个 `let` 之前：`applyTimeAppearance()` 会读
// `skyOverrides`，而 `let` 在初始化语句执行前处于 TDZ。曾经放在上面 —— 走 vite dev
// 时直接 `ReferenceError: Cannot access 'skyOverrides' before initialization`
// 把整个模块打断（连 `__wildViewer` 句柄都没建出来）；而打包构建因为把 `let`
// 提升到了前面，反而看不出问题 ⇒ **这类顺序错误只有 dev server 会报警**。
applyTimeAppearance()

function applyTimeAppearance(): void {
  const preset: TimePreset = { ...TIME_PRESETS[timeOfDay], ...skyOverrides }
  const environmentPreset = ENVIRONMENT_PRESETS[environmentId]
  const atmosphere = deriveWorldAtmosphere(
    getWorldEnvironmentState(),
    getWorldRenderingState().weatherEnabled,
  )
  const sunDirection = new THREE.Vector3().setFromSphericalCoords(
    1,
    THREE.MathUtils.degToRad(preset.sunPhi),
    THREE.MathUtils.degToRad(preset.sunTheta + environmentPreset.sunAzimuthOffset),
  )
  // 夜晚 sunPhi = 108° ⇒ 太阳落到地平线之下，主光必须改取月亮方向，
  // 否则平行光会从地面下方往上打，整晚没有有效方向光。
  keyLightDirection.copy(sunDirection)
  if (timeOfDay === 'night') keyLightDirection.negate()

  sky.visible = preset.skyVisible
  syncSkyPreset(sky, preset, atmosphere, sunDirection)
  scene.background = new THREE.Color(preset.background)
    .lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength)

  renderer.toneMappingExposure = exposureOverride
    ?? preset.exposure * environmentPreset.exposureScale * atmosphere.exposureScale

  lightingRig.applyAppearance({
    hemisphereSkyColor: preset.hemisphereSkyColor,
    hemisphereGroundColor: preset.hemisphereGroundColor,
    hemisphereIntensity: preset.hemisphereIntensity
      * environmentPreset.ambientLightScale
      * atmosphere.ambientLightScale
      * hemisphereScale,
    keyColor: preset.directionalColor,
    keyIntensity: preset.directionalIntensity
      * environmentPreset.directLightScale
      * atmosphere.directLightScale
      * keyScale,
  })

  // 日月精灵：与环境贴图里的太阳亮点同向，保证"看到的太阳"与"高光方向"一致。
  const r = 380
  sunBody.position.copy(sunDirection).multiplyScalar(r)
  moonBody.position.copy(sunDirection).multiplyScalar(-r)
  sunBody.scale.setScalar(26)
  moonBody.scale.setScalar(16)
  sunBody.visible = timeOfDay !== 'night' && preset.skyVisible
  moonBody.visible = timeOfDay === 'night' && preset.skyVisible

  environmentRuntime.schedule(preset, atmosphere, sunDirection, timeOfDay === 'night', true)
}

// ── 光影随包围盒缩放 ─────────────────────────────────────────
// 固定 ±26 的正交阴影框在 12m 别墅上尚可，但在跨度更大的蓝图上要么把建筑
// 切掉、要么让阴影精度浪费在空白区。推导交给引擎的 fitToBounds（与编辑器同一条）。
function updateShadowExtent(boxMin: THREE.Vector3, boxMax: THREE.Vector3): void {
  const center = boxMin.clone().add(boxMax).multiplyScalar(0.5)
  const size = boxMax.clone().sub(boxMin)
  lightingRig.fitToBounds(center, size, keyLightDirection, {
    onShadowsDirty: () => {
      renderer.shadowMap.needsUpdate = true
    },
  })
}

// ── 构件包围盒 ───────────────────────────────────────────────
// Box3Helper 每次构造都自带独立 geometry/material，清空时必须逐个 dispose，
// 否则反复切蓝图会持续泄漏显存。
function clearBBoxGroup(): void {
  for (const child of [...bboxGroup.children]) {
    const helper = child as THREE.Box3Helper
    const geo = helper.geometry
    const mat = helper.material
    if (geo) geo.dispose()
    if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
    else if (mat) (mat as THREE.Material).dispose()
    bboxGroup.remove(child)
  }
}

function rebuildBoundingBoxes(): void {
  clearBBoxGroup()
  const on = (document.getElementById('bbox') as HTMLInputElement).checked
  if (!on) return
  for (const mesh of allMeshes) {
    if (!mesh.visible) continue
    const m = mesh as THREE.Mesh
    if (!m.geometry) continue
    const box = new THREE.Box3().setFromObject(mesh)
    if (box.isEmpty()) continue
    // 构件尺寸太小或退化时不画，避免噪声框盖住建筑
    const size = box.getSize(new THREE.Vector3())
    if (size.length() < 0.02) continue
    const helper = new THREE.Box3Helper(box, 0x5b9dff)
    const mat = helper.material as THREE.LineBasicMaterial
    // 关掉深度测试：位置错误的构件即使被别的体量挡住也能看见，这对分诊很重要
    mat.depthTest = false
    mat.transparent = true
    mat.opacity = 0.75
    helper.renderOrder = 999
    bboxGroup.add(helper)
  }
}

// ── 取景 ─────────────────────────────────────────────────────
// 记下"归一化后的取景球"，供 URL 参数与调试句柄在加载完成后重新定机位。
// 不记的话，切换 cam 只能靠刷新页面 —— 而刷新会让截图脚本无法确定时机。
let frameState: {
  center: THREE.Vector3
  radius: number
  /** 取景盒（已含居中平移），用于按投影求紧致距离 */
  boxMin: THREE.Vector3
  boxMax: THREE.Vector3
} | null = null

// 取景要取**建筑本体**，不能取整份包围盒。
// 蓝图里一旦有场地/草坪板（几十米见方），整份包围盒会被它撑大，相机退到
// 只能看见一片草地、建筑小成一个点 —— 场地理应超出画面，而不是决定画面。
// 判据用 reconstructionReport 里逐构件的实际包围盒，只取结构性类型。
const STRUCTURE_TYPES = new Set(['wall', 'roof', 'column', 'beam', 'stair', 'body', 'primitive'])
const BOX3_KEYS = new Set(['bayWindow', 'balcony', 'canopy', 'cornice', 'chimney', 'ramp'])

function focusBoxOf(entity: any): { min: number[]; max: number[] } | null {
  const observations = entity?.reconstructionReport?.observations
  if (!Array.isArray(observations) || observations.length === 0) return null
  const min = [Infinity, Infinity, Infinity]
  const max = [-Infinity, -Infinity, -Infinity]
  let hits = 0
  for (const obs of observations) {
    if (!obs?.actualBounds) continue
    // 门窗/阳台这类组合构件也计入：它们贴着立面，不会把范围带偏
    const type = String(obs.sourceType ?? '')
    if (!STRUCTURE_TYPES.has(type) && !BOX3_KEYS.has(type)) continue
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], obs.actualBounds.min[axis])
      max[axis] = Math.max(max[axis], obs.actualBounds.max[axis])
    }
    hits += 1
  }
  if (hits === 0 || !min.every(Number.isFinite) || !max.every(Number.isFinite)) return null
  // 退化保护：某轴为 0 时不参与"球半径"，否则近扁平蓝图会算出一个极小的取景球
  return { min, max }
}

/** 按预设名重新定机位。加载完成前调用无效（此时没有 frameState）。 */
function applyCameraPreset(name: string): boolean {
  if (!frameState) return false
  const preset = CAM_DIRS[name] ?? CAM_DIRS.pool
  currentCam = CAM_DIRS[name] ? name : 'pool'
  const zAxis = new THREE.Vector3(...preset).normalize() // 中心 → 相机
  const up = new THREE.Vector3(0, 1, 0)
  const xAxis = new THREE.Vector3().crossVectors(up, zAxis)
  if (xAxis.lengthSq() < 1e-8) xAxis.set(1, 0, 0) // 正俯视：worldUp 与视线共线
  xAxis.normalize()
  const yAxis = new THREE.Vector3().crossVectors(zAxis, xAxis).normalize()

  // ⚠️ 不用"包围球半径 / sin(fov/2)"：包围球外接整个盒子的对角线，
  //    投影后的实际轮廓小得多，扁平蓝图（本别墅 41×11.7×30）会被顶到画面 1/4 处。
  //    改为逐角求"该角正好压住画面边缘"所需的最小距离，取最大值。
  const tanV = Math.tan((camera.fov * Math.PI) / 360)
  const tanH = tanV * camera.aspect
  const { center, boxMin, boxMax } = frameState
  let dist = 0
  const corner = new THREE.Vector3()
  for (let i = 0; i < 8; i += 1) {
    corner.set(
      (i & 1 ? boxMax : boxMin).x - center.x,
      (i & 2 ? boxMax : boxMin).y - center.y,
      (i & 4 ? boxMax : boxMin).z - center.z,
    )
    const cz = corner.dot(zAxis)
    dist = Math.max(
      dist,
      cz + Math.abs(corner.dot(xAxis)) / tanH,
      cz + Math.abs(corner.dot(yAxis)) / tanV,
    )
  }
  dist *= 1.06 // 极小留白，避免构件正好贴边

  camera.position.copy(center).add(zAxis.clone().multiplyScalar(dist))
  controls.target.copy(center)
  camera.near = Math.max(0.1, dist - frameState.radius * 4)
  camera.far = dist + frameState.radius * 8
  camera.updateProjectionMatrix()
  controls.update()
  return true
}

/**
 * `box` = 整份包围盒（定位地面/阴影范围/足迹居中）
 * `focus` = 建筑本体包围盒（定相机距离与目标点），缺省退回整份
 */
function frameToBox(box: { min: number[]; max: number[] }, focus?: { min: number[]; max: number[] } | null): void {
  const min = new THREE.Vector3().fromArray(box.min)
  const max = new THREE.Vector3().fromArray(box.max)
  const size = max.clone().sub(min)
  const radius = size.length() * 0.5 || 10

  // 足迹居中归一化：生成器产出的是"角点对齐"坐标（x 从 0 到 12，而非 -6 到 6），
  // 而地面与网格钉在世界原点 ⇒ 不平移建筑就会偏离网格中心。
  // 只平移 X/Z；Y 不动，因为地面高度是设计值。
  // ⚠️ 居中按**整份**包围盒算：场地理应与建筑一起居中，只居中建筑会让场地偏心。
  instance?.setTransform({ position: [-(min.x + max.x) / 2, 0, -(min.z + max.z) / 2] })

  const fMin = focus ? new THREE.Vector3().fromArray(focus.min) : min
  const fMax = focus ? new THREE.Vector3().fromArray(focus.max) : max
  const fSize = fMax.clone().sub(fMin)
  const fCenter = fMin.clone().add(fMax).multiplyScalar(0.5)
  const focusRadius = fSize.length() * 0.5 || radius

  // 居中平移量（与上面 setTransform 用的是同一个）
  const shift = new THREE.Vector3(-(min.x + max.x) / 2, 0, -(min.z + max.z) / 2)

  frameState = {
    // 取景中心必须按"居中平移后"的坐标算：建筑已经被移到原点附近
    center: new THREE.Vector3(fCenter.x + shift.x, fCenter.y, fCenter.z + shift.z),
    radius: focusRadius,
    boxMin: fMin.clone().add(shift),
    boxMax: fMax.clone().add(shift),
  }
  applyCameraPreset(qsCam)

  // 地面/网格贴建筑自身地面：用包围盒底面而不是写死的 -0.3
  // （不同蓝图的楼板厚度不同，写死会让建筑悬空或陷入地面）。
  ground.position.y = min.y
  grid.position.y = min.y + 0.001
  // 阴影范围按**整份**包围盒（含居中平移后的世界坐标）：场地也要接住影子
  updateShadowExtent(frameState.boxMin, frameState.boxMax)
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
  rebuildBoundingBoxes()
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

// 诊断按"数据 / 视觉"粗分，服务于分诊：数据类要改蓝图，视觉类才轮到引擎。
function classifyDiagnostic(d: any): 'data' | 'visual' | 'other' {
  const msg = String(d.message ?? '')
  if (/悬空|穿透|越界|不存在|重复|超出|未命中|无法解析|parentWall|宿主|落在/.test(msg)) {
    return 'data'
  }
  if (/材质|贴图|光照|法线|剔除|阴影|颜色|纹理|透明度|反射/.test(msg)) return 'visual'
  return 'other'
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
    const dataCount = diagnostics.filter((d) => classifyDiagnostic(d) === 'data').length
    const visualCount = diagnostics.filter((d) => classifyDiagnostic(d) === 'visual').length
    const hint = el('div')
    hint.style.marginTop = '6px'
    hint.style.fontSize = '11px'
    hint.style.color = '#8b95a5'
    hint.textContent = `其中疑似数据类 ${dataCount} · 视觉类 ${visualCount} —— 数据类先改蓝图`
    stats.appendChild(hint)

    const details = el('details') as HTMLDetailsElement
    if (errors.length > 0) details.open = true
    const summary = el('summary')
    summary.textContent = `诊断明细（${diagnostics.length}）`
    details.appendChild(summary)

    const list = el('ul', 'diag-list')
    const ordered = [
      ...errors,
      ...warnings,
      ...diagnostics.filter((d) => d.level !== 'error' && d.level !== 'warning'),
    ]
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
// 加载阶段是要暴露给截图脚本的：`--screenshot + --virtual-time-budget` 那套
// 无法判断异步重建是否已完成，实测会截到"只有地面、建筑还没进来"的空帧。
let loadPhase: 'idle' | 'loading' | 'ready' | 'error' = 'idle'
let lastMessage = ''

async function loadBlueprintText(text: string, label: string): Promise<void> {
  loadPhase = 'loading'
  lastMessage = '正在编译并重建…'
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
    loadPhase = 'error'
    lastMessage = `解析 / 重建失败：${err?.message ?? err}`
    renderMessage(lastMessage, 'err')
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
    frameToBox(bb, focusBoxOf(entity))
  }
  populateLevelSelect()
  applyLevelFilter(0)
  rebuildBoundingBoxes()
  renderPanel(label, bp, entity, allMeshes.length)
  loadPhase = 'ready'
  lastMessage = ''
}

async function loadByFile(file: string, label: string): Promise<void> {
  try {
    const res = await fetch(`/bp/${encodeURIComponent(file)}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await loadBlueprintText(await res.text(), label)
  } catch (err: any) {
    loadPhase = 'error'
    lastMessage = `加载失败：${err?.message ?? err}`
    renderMessage(lastMessage, 'err')
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
    rebuildBoundingBoxes()
  })

  const gridToggle = document.getElementById('gridToggle') as HTMLInputElement
  gridToggle.addEventListener('change', () => {
    grid.visible = gridToggle.checked
    ground.visible = gridToggle.checked
  })

  const bbox = document.getElementById('bbox') as HTMLInputElement
  bbox.addEventListener('change', () => rebuildBoundingBoxes())

  const exposure = document.getElementById('exposure') as HTMLInputElement
  const exposureVal = document.getElementById('exposureVal') as HTMLElement
  exposure.addEventListener('input', () => {
    const v = Number(exposure.value)
    // 写进 exposureOverride 而不是直接写 renderer：否则下一次 applyTimeAppearance()
    // （切时段/环境档、或标定脚本 setLook）会把滑杆的取值冲掉。
    exposureOverride = v
    renderer.toneMappingExposure = v
    exposureVal.textContent = v.toFixed(2)
  })

  // ── URL 覆盖（截图脚本用；不传参数则行为与手工打开完全一致）──
  if (QS.has('exp')) {
    const v = qsNum('exp', 1.05)
    exposure.value = String(v)
    exposureOverride = v
    exposureVal.textContent = v.toFixed(2)
  }
  // key / hemi 是**相对倍率**（不是绝对值）：标定曝光与光强的配比时，
  // 需要在"引擎预设"这条基线上叠加偏移，而不是把预设整条替换掉。
  if (QS.has('key')) keyScale = qsNum('key', 1)
  if (QS.has('hemi')) hemisphereScale = qsNum('hemi', 1)
  if (QS.has('exp') || QS.has('key') || QS.has('hemi')) applyTimeAppearance()
  if (QS.get('panel') === '0') {
    ;(document.getElementById('panel') as HTMLElement).style.display = 'none'
    ;(document.getElementById('hint') as HTMLElement).style.display = 'none'
  }
  if (QS.has('grid')) {
    gridToggle.checked = QS.get('grid') !== '0'
    grid.visible = gridToggle.checked
    ground.visible = gridToggle.checked
  }
  if (QS.get('bbox') === '1') bbox.checked = true
}

function animate(): void {
  requestAnimationFrame(animate)
  controls.update()
  postProcessing.render()
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
  postProcessing.setSize(window.innerWidth, window.innerHeight)
  // 取景距离依赖 aspect（tanH = tanV × aspect）⇒ 窗口比例一变就得重算，
  // 否则宽屏下建筑会重新贴边或缩小。
  applyCameraPreset(currentCam)
})

initUI()
animate()

// ── 自包含构建（单文件 HTML）──────────────────────────────────
// `dist/index.html` 是**给静态服务器**用的：它引用的是绝对路径 `/assets/…`，
// 一旦用 file:// 双击打开就会变成 `file:///E:/assets/…` 被 CORS 拦掉（实测白屏、
// 0 个 canvas）。所以单文件版把**蓝图文本在构建期内联进页面**，不做任何 fetch。
const INLINE_BLUEPRINT = (window as any).__WILD_INLINE_BLUEPRINT__ as string | undefined
const INLINE_LABEL = (window as any).__WILD_INLINE_LABEL__ as string | undefined

if (INLINE_BLUEPRINT) {
  // 内联模式下没有 /bp 中间件，蓝图下拉框里的其它项必然 404 —— 直接收起来，
  // 只留「加载本地 .wild」（那条走 FileReader，不依赖服务器）。
  const bpField = document.getElementById('bpField')
  if (bpField) bpField.style.display = 'none'
  loadBlueprintText(INLINE_BLUEPRINT, INLINE_LABEL ?? BLUEPRINTS[0].name)
} else {
  loadByFile(BLUEPRINTS[0].file, BLUEPRINTS[0].name)
}

// ── 调试句柄（只给截图脚本用）────────────────────────────────
// 截图脚本需要三件事：① 知道"重建真的完成了"；② 在不刷新的前提下换机位；
// ③ 核实光照确实来自引擎（IBL 到位、没有本地自建的环境光）。
// 只暴露这三类**只读**信息，不把 renderer / scene / instance 交出去 —— 一旦交出去，
// 外部脚本就有机会自己造网格或材质，查看器"只反映引擎产出"的前提就破了。
;(window as any).__wildViewer = {
  ready: () => loadPhase === 'ready',
  phase: () => loadPhase,
  message: () => lastMessage,
  cams: () => Object.keys(CAM_DIRS),
  setCam: (name: string) => applyCameraPreset(name),
  /** 光照体检：环境贴图是否真的挂上、场景里有没有被本地塞进环境光。 */
  lighting: () => {
    const lights = scene.children.filter((child) => (child as THREE.Light).isLight) as THREE.Light[]
    return {
      timeOfDay,
      environmentId,
      // `scene.environment` 是材质层（玻璃 transmission / 金属 envMapIntensity）的前提
      hasEnvironmentMap: scene.environment !== null,
      environmentMapIsTexture: Boolean(scene.environment && (scene.environment as THREE.Texture).isTexture),
      // AmbientLight 会洗掉接触阴影；引擎刻意只用半球光 + 关键光 + IBL
      ambientLightCount: lights.filter((light) => (light as THREE.AmbientLight).isAmbientLight).length,
      lightCount: lights.length,
      lightKinds: lights.map((light) => light.type).sort(),
      shadowMapEnabled: renderer.shadowMap.enabled,
    }
  },
  /**
   * 当前**实际生效**的外观数值（不是预设里的标称值）。
   * 曝光标定要看的正是这一层：预设 × 环境档 × 天气 × 标定倍率之后的合成结果。
   */
  look: () => ({
    timeOfDay,
    environmentId,
    exposure: renderer.toneMappingExposure,
    exposureOverride,
    keyScale,
    hemisphereScale,
    keyIntensity: sun.intensity,
    hemisphereIntensity: lightingRig.hemisphere.intensity,
    keyColor: `#${sun.color.getHexString()}`,
    toneMapping: renderer.toneMapping,
    sky: { ...TIME_PRESETS[timeOfDay], ...skyOverrides }.rayleigh,
    // 报告里要能对上"这一张图是用哪组散射参数出的"
    skyTurbidity: { ...TIME_PRESETS[timeOfDay], ...skyOverrides }.turbidity,
  }),
  /**
   * 标定用：临时叠一层倍率并重跑外观。`exposure: null` 表示回到引擎预设推导的曝光。
   * 只给标定/出图脚本用，UI 不走这里。
   */
  setLook: (overrides: {
    exposure?: number | null
    key?: number
    hemi?: number
    sky?: { rayleigh?: number; turbidity?: number; mieCoefficient?: number }
  } = {}) => {
    if (overrides.exposure !== undefined) exposureOverride = overrides.exposure
    if (overrides.key !== undefined) keyScale = overrides.key
    if (overrides.hemi !== undefined) hemisphereScale = overrides.hemi
    if (overrides.sky !== undefined) skyOverrides = { ...skyOverrides, ...overrides.sky }
    applyTimeAppearance()
    return (window as any).__wildViewer.look()
  },
}
