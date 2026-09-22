<template>
  <div class="canvas-viewport" ref="containerRef">
    <!-- 展示3D视图的区域 -->
    <canvas ref="canvasRef"></canvas>
    <div class="viewport-overlay">
      <div v-if="viewMode === 'editor'" class="stats">
        <div v-if="sceneStore.document">
          基础: {{ sceneStore.document.blueprint.geometry.elements?.length || 0 }} ·
          组合: {{ sceneStore.document.blueprint.geometry.components?.length || 0 }}
        </div>
        <div v-if="sceneStore.reconstructed">
          网格: {{ sceneStore.reconstructed.meshes.length }}
        </div>
        <div v-if="sceneStore.reconstructed?.diagnostics?.length" class="diagnostics">
          诊断: {{ sceneStore.reconstructed.diagnostics.length }}
        </div>
        <div v-if="sceneStore.isReconstructing">
          重建中...
        </div>
      </div>
      <div class="viewport-toolbar">
        <button
          type="button"
          class="viewport-action"
          :title="`切换到${nextTimePreset.label}`"
          :aria-label="`当前${activeTimePreset.label}，切换到${nextTimePreset.label}`"
          @click="cycleTimeOfDay"
        >
          <span aria-hidden="true">{{ activeTimePreset.icon }}</span>
          <span>{{ activeTimePreset.label }}</span>
        </button>
        <button
          type="button"
          class="viewport-action"
          :title="`切换场景，当前为${activeEnvironmentPreset.label}`"
          :aria-label="`当前${activeEnvironmentPreset.label}场景，切换到下一个场景`"
          @click="cycleEnvironmentPreset"
        >
          <span aria-hidden="true">{{ activeEnvironmentPreset.icon }}</span>
          <span>{{ activeEnvironmentPreset.label }}</span>
        </button>
        <button type="button" class="viewport-action" @click="cycleCameraPreset">
          <span aria-hidden="true">📷</span>
          <span>{{ activeCameraPreset.label }}</span>
        </button>
        <button type="button" class="viewport-action" @click="cycleQuality">
          <span aria-hidden="true">◆</span>
          <span>{{ activeQualityPreset.label }}</span>
        </button>
        <button
          type="button"
          :class="['viewport-action', { active: viewMode === 'presentation' }]"
          @click="toggleViewMode"
        >
          <span aria-hidden="true">{{ viewMode === 'presentation' ? '▣' : '▢' }}</span>
          <span>{{ viewMode === 'presentation' ? '展示' : '编辑' }}</span>
        </button>
      </div>
      <div class="fps-meter" :class="fpsTier" title="实时帧率">FPS {{ fps }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { useUIStore } from '../../stores/uiStore'
import { useWorldPackageStore } from '../../stores/worldPackageStore'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { Sky } from 'three/examples/jsm/objects/Sky.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import {
  configureKtx2Rendering,
  configureMaterialRendering,
  disposeKtx2Rendering,
  MaterialCache,
} from '../../renderer/materialAdapter'
import {
  clearSceneObjectResources,
  toggleRuntimeInteraction,
} from '../../renderer/renderEntity'
import { WorldRuntime } from '../../renderer/worldRuntime'
import {
  createEditorWorldDocument,
  saveWorldDocument,
} from '../../renderer/worldDocumentPersistence'
import { worldLookRuntime } from '../../renderer/worldLookRuntime'
import {
  getWorldEnvironmentState,
  getWorldRenderingState,
  subscribeWorldEnvironment,
  subscribeWorldRendering,
  updateWorldEnvironmentState,
  updateWorldRenderingState,
} from '../../renderer/worldEnvironmentRuntime'
import {
  deriveWorldAtmosphere,
  WorldWeatherVisuals,
  type WorldAtmosphereAppearance,
} from '../../renderer/worldWeatherRuntime'
import {
  getWorldEffectState,
  getWorldEffectUniforms,
  setWorldEffectTime,
  subscribeWorldEffects,
} from '../../renderer/worldEffectRuntime'
import { WorldCloudLayer } from '../../renderer/worldCloudLayer'
import { applyGroundWeatherMaterial } from '../../renderer/groundWeatherMaterial'
import {
  createCelestialBody,
  syncSkyPreset,
  WorldEnvironmentMapRuntime,
} from '../../renderer/environmentRuntime'
import { WorldLightingRig } from '../../renderer/lightingRuntime'
import { WorldPostProcessingRuntime } from '../../renderer/postProcessingRuntime'
import {
  CAMERA_ORDER,
  CAMERA_PRESETS,
  ENVIRONMENT_ORDER,
  ENVIRONMENT_PRESETS,
  QUALITY_ORDER,
  QUALITY_PRESETS,
  TIME_ORDER,
  TIME_PRESETS,
  type CameraPresetId,
  type EnvironmentPresetId,
  type QualityLevel,
  type TimeOfDay,
  type TimePreset,
  type ViewMode,
} from '../../renderer/defaultWorldLook'
import {
  getRenderedElementIds,
  resolveSelectableId,
  selectionAfterClick,
  type SelectionMode,
} from '../../wild/componentSelection'
import { createComponentTranslationChanges } from '../../wild/componentDrag'
import { createPatch } from '../../wild/scenePatch'

const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const uiStore = useUIStore()
const worldPackageStore = useWorldPackageStore()

const timeOfDay = ref<TimeOfDay>('day')
const viewMode = ref<ViewMode>('editor')
const qualityLevel = ref<QualityLevel>('medium')
const cameraPresetId = ref<CameraPresetId>('corner')
const environmentPresetId = ref<EnvironmentPresetId>('minimal')
const activeTimePreset = computed(() => TIME_PRESETS[timeOfDay.value])
const activeQualityPreset = computed(() => QUALITY_PRESETS[qualityLevel.value])
const activeCameraPreset = computed(() => CAMERA_PRESETS[cameraPresetId.value])
const activeEnvironmentPreset = computed(() => ENVIRONMENT_PRESETS[environmentPresetId.value])
const fps = ref(0)
const fpsTier = computed(() => fps.value >= 50 ? 'good' : fps.value >= 30 ? 'ok' : 'bad')
const nextTimePreset = computed(() => {
  const nextIndex = (TIME_ORDER.indexOf(timeOfDay.value) + 1) % TIME_ORDER.length
  return TIME_PRESETS[TIME_ORDER[nextIndex]]
})

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let transformControls: TransformControls | null = null
let animationFrameId: number | null = null
let renderLoopActive = false
let resizeObserver: ResizeObserver | null = null
let sceneGroup: THREE.Group | null = null
let materialCache: MaterialCache | null = null
let worldRuntime: WorldRuntime | null = null
let gridHelper: THREE.GridHelper | null = null
let environmentRuntime: WorldEnvironmentMapRuntime | null = null
let lightingRig: WorldLightingRig | null = null
let sky: Sky | null = null
let sunBody: THREE.Sprite | null = null
let moonBody: THREE.Sprite | null = null
let weatherVisuals: WorldWeatherVisuals | null = null
let cloudLayer: WorldCloudLayer | null = null
let hemisphereLight: THREE.HemisphereLight | null = null
let directionalLight: THREE.DirectionalLight | null = null
let shadowGround: THREE.Mesh<THREE.PlaneGeometry, THREE.ShadowMaterial> | null = null
let presentationGround: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial> | null = null
let builtInEnvironment: THREE.Group | null = null
let postProcessing: WorldPostProcessingRuntime | null = null
// 以下四个只是 postProcessing 的别名；真正的构造/尺寸/采样数/释放都在引擎运行时里。
let composer: EffectComposer | null = null
let ssaoPass: SSAOPass | null = null
let bloomPass: UnrealBloomPass | null = null
let fxaaPass: ShaderPass | null = null
// 合成链路 MSAA 采样数：默认 4x；帧率降级时减半——像素比已经降了，几何锯齿不该完全失守。
const DEFAULT_MSAA_SAMPLES = 4
const DEGRADED_MSAA_SAMPLES = 2
const sunDirection = new THREE.Vector3()
// 主光（定向光 + 阴影相机）实际使用的方向。与 sunDirection 的区别只在夜晚：
// night 档 sunPhi = 108° > 90° ⇒ sunDirection.y < 0（太阳落到地平线之下），
// 若直接拿它当主光方向，主光会被放到地面之下面朝上打光，等于整晚没有有效方向光。
// 此时主光应取月亮方向 —— 与 moonBody（= center − sunDirection × r）一致。
// 天空 uniform 与日月实体继续用 sunDirection，不受影响。
const keyLightDirection = new THREE.Vector3(0, 1, 0)
const weatherClock = new THREE.Clock()
const lightingCenter = new THREE.Vector3()
const sceneBoundsCenter = new THREE.Vector3()
const sceneBoundsSize = new THREE.Vector3(8, 4, 8)
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
const instanceMatrix = new THREE.Matrix4()
const instanceWorldMatrix = new THREE.Matrix4()
// 场景尺度参照：内置环境半径、日月大小、天气层范围、雾都以它为准。
// 刻意【不随太阳高度角变化】，否则切换时段时山体/远树会整体跳位。
let lightingExtent = 8
// 阴影正交框半宽：必须随太阳高度角放大（低角度下落影行程会指数级增长）。
let shadowExtent = 8
let environmentGroundY = 0
let hasSceneBounds = false
let hasFramedScene = false
let needsRender = true
let pointerDownPosition: { x: number; y: number } | null = null
let selectionHelpers: THREE.Box3Helper[] = []
let dragAnchor: THREE.Object3D | null = null
let dragStartPosition: THREE.Vector3 | null = null
let dragComponentId: string | null = null
let dragTargetPositions = new Map<THREE.Object3D, THREE.Vector3>()
let suppressSelectionClick = false
let unsubscribeWorldLook: (() => void) | null = null
let unsubscribeWorldEnvironment: (() => void) | null = null
let unsubscribeWorldRendering: (() => void) | null = null
let unsubscribeWorldEffects: (() => void) | null = null
let effectClock = 0
let fpsSmoothed = 60
let adaptiveQualityApplied = false
let lastShadowDirtyTime = 0
const SHADOW_DIRTY_THROTTLE_MS = 120
// 拖动结束时补一次阴影刷新用的尾沿定时器。
let trailingShadowDirtyTimer: ReturnType<typeof setTimeout> | null = null
// 环境贴图（PMREM）的去重、节流与生命周期全部由 engine 侧的
// WorldEnvironmentMapRuntime 持有，组件只负责"什么时候用什么预设"。
// 阴影贴花的亮度比（线性空间）：等价于原先 0x26352d 在极简地面 0x747b73 上的关系。
const SHADOW_DECAL_LUMA_RATIO = 0.162

onMounted(() => {
  unsubscribeWorldLook = worldLookRuntime.subscribe(() => {
    // WILD 光影 profile 切换是离散动作，环境贴图必须立即重建。
    applyTimePreset(true)
    applyQualityPreset()
  })
  unsubscribeWorldEnvironment = subscribeWorldEnvironment(() => {
    // 时段切换同样走这条通道，但它属于离散动作；天气滑杆则是连续输入。
    const timeChanged = syncTimePresetFromWorldEnvironment()
    applyTimePreset(timeChanged)
    markNeedsRender()
  })
  unsubscribeWorldRendering = subscribeWorldRendering(() => {
    applyTimePreset(true)
    markNeedsRender()
  })
  unsubscribeWorldEffects = subscribeWorldEffects(() => {
    cloudLayer?.setVisible(getWorldEffectState().clouds)
    weatherVisuals?.setEnvironment(getWorldEnvironmentState(), getWorldRenderingState().weatherEnabled)
    configureSceneFog()
    applyGroundVisibility()
    markNeedsRender()
  })
  initThreeJS()
  void worldPackageStore.initialize().then(() => worldPackageStore.restorePreferredLook())
  startRenderLoop()
})

onUnmounted(() => {
  unsubscribeWorldLook?.()
  unsubscribeWorldLook = null
  unsubscribeWorldEnvironment?.()
  unsubscribeWorldEnvironment = null
  unsubscribeWorldRendering?.()
  unsubscribeWorldRendering = null
  unsubscribeWorldEffects?.()
  unsubscribeWorldEffects = null
  cleanup()
})

watch(() => sceneStore.reconstructed, () => {
  updateScene()
})
watch(() => sceneStore.document?.id, () => {
  hasFramedScene = false
})
watch(() => [...selectionStore.selectedIds], () => {
  syncSelectionHighlights()
  syncComponentTransformControl()
})
watch([
  () => sceneStore.document?.revision,
  () => worldPackageStore.activeProfileId,
  () => worldPackageStore.materialPackages.map(item => item.manifest.packageId).join('|'),
  () => JSON.stringify(worldPackageStore.environment),
], persistEditorWorldState)

function initThreeJS() {
  if (!canvasRef.value || !containerRef.value) return

  renderer = new THREE.WebGLRenderer({
    canvas: canvasRef.value,
    // 恒定 false：主光栅化走 EffectComposer 的离屏 RT，canvas 默认帧缓冲只用来贴最终一张全屏四边形，
    // 这里的 MSAA 既无效又白占显存。几何抗锯齿改在合成离线 RT 上做（见 applySceneMsaa）。
    antialias: false,
    powerPreference: 'high-performance',
  })
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  // 静态场景 + 轨道相机：阴影只依赖灯光与物体，不依赖相机视角。
  // 关闭每帧自动重算，仅在内容/灯光变化时按需刷新，消除拖动视角时的阴影重渲开销。
  renderer.shadowMap.autoUpdate = false
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05
  configureMaterialRendering(renderer.capabilities.getMaxAnisotropy(), markNeedsRender)
  configureKtx2Rendering(renderer)

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0xb9c9d8)
  worldLookRuntime.setActivationContext({ renderer, scene })

  const aspect = containerRef.value.clientWidth / containerRef.value.clientHeight
  camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 2000)
  camera.position.set(12, 10, 12)

  // 后期合成链路（SSAO 接触阴影 / Bloom / FXAA / MSAA）由引擎侧持有，
  // 组件只决定"当前画质档开哪几项"。四个别名只为让既有策略代码少改。
  postProcessing = new WorldPostProcessingRuntime(renderer, scene, camera, {
    msaaSamples: DEFAULT_MSAA_SAMPLES,
  })
  composer = postProcessing.composer
  ssaoPass = postProcessing.ssao
  bloomPass = postProcessing.bloom
  fxaaPass = postProcessing.fxaa

  controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0, 1.5, 0)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.addEventListener('change', markNeedsRender)
  controls.update()

  transformControls = new TransformControls(camera, renderer.domElement)
  transformControls.setMode('translate')
  transformControls.setSpace('world')
  transformControls.setSize(0.72)
  transformControls.addEventListener('mouseDown', handleTransformMouseDown)
  transformControls.addEventListener('objectChange', handleTransformObjectChange)
  transformControls.addEventListener('mouseUp', handleTransformMouseUp)
  transformControls.addEventListener('dragging-changed', handleTransformDraggingChanged)
  scene.add(transformControls)

  renderer.domElement.addEventListener('pointerdown', handlePointerDown)
  renderer.domElement.addEventListener('pointerup', handlePointerUp)
  renderer.domElement.addEventListener('contextmenu', handleContextMenu)

  sky = new Sky()
  sky.scale.setScalar(450)
  scene.add(sky)
  sunBody = createCelestialBody('sun')
  moonBody = createCelestialBody('moon')
  scene.add(sunBody, moonBody)
  weatherVisuals = new WorldWeatherVisuals(scene)
  cloudLayer = new WorldCloudLayer(scene)
  cloudLayer.setVisible(getWorldEffectState().clouds)

  // 环境贴图（IBL）运行时：离屏环境场景 + PMREM 全部由引擎侧持有。
  // 组件只是它的调用方 —— 这样 `lantu/viewer` 与离线出图脚本能拿到**同一份** IBL，
  // 而不是各自在本地再搭一套光照。
  environmentRuntime = new WorldEnvironmentMapRuntime(renderer, scene, {
    onRebuilt: markNeedsRender,
  })

  // 光照骨架（半球光 + 关键光/阴影）同样由引擎侧持有；这里只保留两个别名，
  // 因为组件里有大量"按当前预设改颜色/强度"的策略代码要写这两个光源。
  lightingRig = new WorldLightingRig(scene, { shadowMapSize: 2048 })
  hemisphereLight = lightingRig.hemisphere
  directionalLight = lightingRig.key
  // 首帧必须无条件建好环境贴图。
  applyTimePreset(true)

  shadowGround = new THREE.Mesh(
    new THREE.PlaneGeometry(400, 400),
    new THREE.ShadowMaterial({ color: 0x26352d, opacity: ENVIRONMENT_PRESETS.minimal.shadowOpacity }),
  )
  shadowGround.name = 'ShadowGround'
  shadowGround.rotation.x = -Math.PI / 2
  shadowGround.position.y = -0.002
  shadowGround.renderOrder = 2
  shadowGround.receiveShadow = true
  scene.add(shadowGround)

  const groundTexture = createGroundTexture()
  presentationGround = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshStandardMaterial({
      map: groundTexture,
      color: TIME_PRESETS.day.groundColor,
      roughness: 0.92,
      metalness: 0,
    }),
  )
  presentationGround.userData.groundTexture = groundTexture
  presentationGround.name = 'PresentationGround'
  presentationGround.rotation.x = -Math.PI / 2
  presentationGround.position.y = -0.004
  presentationGround.scale.set(200, 200, 1)
  // 地面本体负责受光，透明 ShadowMaterial 单独叠加可控的建筑投影，避免阴影重复变黑。
  presentationGround.receiveShadow = false
  presentationGround.visible = false
  scene.add(presentationGround)
  applyGroundWeatherMaterial(presentationGround.material)

  builtInEnvironment = new THREE.Group()
  builtInEnvironment.name = 'BuiltInEnvironment'
  builtInEnvironment.visible = false
  scene.add(builtInEnvironment)
  rebuildBuiltInEnvironment()
  applyEnvironmentAppearance()
  
  // 创建GridHelper并保持引用，确保不会被误删除
  // 添加到场景根层级，不是sceneGroup
  gridHelper = new THREE.GridHelper(20, 20, 0x444444, 0x333333)
  gridHelper.name = 'GridHelper'
  gridHelper.position.y = 0  // 确保在地面
  scene.add(gridHelper)
  worldRuntime = new WorldRuntime('editor-world')
  worldRuntime.loadChunk('editor-active')
  const activeInstance = worldRuntime.ensureInstance({
    instanceId: 'editor:active-blueprint',
    blueprintId: 'editor:current',
    chunkId: 'editor-active',
    transform: { position: [0, 0, 0] },
  })
  sceneGroup = activeInstance.root
  materialCache = activeInstance.materialScope
  scene.add(worldRuntime.root)
  
  if (typeof ResizeObserver !== 'undefined' && containerRef.value) {
    resizeObserver = new ResizeObserver(() => handleResize())
    resizeObserver.observe(containerRef.value)
  } else {
    window.addEventListener('resize', handleResize)
  }
  applyQualityPreset()
  applyViewMode()
  handleResize()
}

function persistEditorWorldState(): void {
  if (!sceneStore.document) return
  saveWorldDocument(createEditorWorldDocument(sceneStore.document, {
    materialLibraries: worldPackageStore.materialPackages.map(item => item.manifest.packageId),
    renderProfile: worldPackageStore.activeProfileId,
    environment: worldPackageStore.environment,
  }))
}

function handleResize() {
  if (!containerRef.value || !renderer || !camera) return
  const width = containerRef.value.clientWidth
  const height = containerRef.value.clientHeight
  camera.aspect = width / height
  camera.updateProjectionMatrix()
  renderer.setSize(width, height)
  postProcessing?.setSize(width, height)
  markNeedsRender()
}

function startRenderLoop() {
  renderLoopActive = true
  weatherClock.start()
  markNeedsRender()
}

function scheduleRenderFrame() {
  if (!renderLoopActive || animationFrameId !== null) return
  animationFrameId = requestAnimationFrame(renderFrame)
}

function renderFrame() {
  animationFrameId = null
  if (!renderLoopActive) return
  const delta = weatherClock.getDelta()
  const controlsAnimating = controls?.update() ?? false
  const effects = getWorldEffectState()
  const effectsAnimating = effects.clouds || effects.ripples
  if (effectsAnimating) {
    effectClock += Math.min(0.05, Math.max(0, delta))
    setWorldEffectTime(effectClock)
    needsRender = true
  }
  const weatherAnimating = weatherVisuals?.tick(delta) ?? false
  if (weatherAnimating || controlsAnimating) needsRender = true
  // 按需渲染休眠后的第一帧包含较长空闲时间，不能拿它计算实时 FPS。
  if (delta > 0.0005 && delta < 0.25) {
    fpsSmoothed = fpsSmoothed * 0.9 + (1 / delta) * 0.1
    fps.value = Math.round(fpsSmoothed)
  }
  // 帧率自适应降级：持续低于 30fps 时关 SSAO/Bloom 并降像素比，保交互流畅。
  // 只在低档降一次，避免反复切换；手动切换质量档会重置标记。
  if (!adaptiveQualityApplied && fpsSmoothed < 30 && fpsSmoothed > 0) {
    adaptiveQualityApplied = true
    const ratio = renderer?.getPixelRatio() ?? 1
    if (ratio > 1) renderer?.setPixelRatio(Math.max(1, ratio * 0.66))
    postProcessing?.setPixelRatio(renderer?.getPixelRatio() ?? 1)
    if (ssaoPass) ssaoPass.enabled = false
    if (bloomPass) bloomPass.enabled = false
    if (fxaaPass) fxaaPass.enabled = true
    postProcessing?.setMsaaSamples(DEGRADED_MSAA_SAMPLES)
    handleResize()
  }
  if (needsRender && renderer && scene && camera) {
    if (composer) composer.render()
    else renderer.render(scene, camera)
    needsRender = false
  }
  if (controlsAnimating || weatherAnimating || effectsAnimating || needsRender) {
    scheduleRenderFrame()
  }
}

function ensureGridVisible() {
	  if (!gridHelper || !scene) return
	  if (!scene.children.includes(gridHelper)) {
	    scene.add(gridHelper)
	  }
	  gridHelper.visible = viewMode.value === 'editor'
	}

function resetSceneBounds() {
  hasSceneBounds = false
  lightingExtent = 8
  shadowExtent = 8
  environmentGroundY = 0
  sceneBoundsCenter.set(0, 0, 0)
  sceneBoundsSize.set(8, 4, 8)
  // 清掉足迹居中归一化留下的平移，避免空场景/下次加载时继承上一次的偏移。
  if (sceneGroup) sceneGroup.position.set(0, 0, 0)
  if (shadowGround) shadowGround.position.y = -0.002
  if (presentationGround) {
    presentationGround.position.y = -0.004
    presentationGround.scale.set(200, 200, 1)
  }
  if (gridHelper) gridHelper.position.y = 0
  rebuildBuiltInEnvironment()
}

function updateScene() {
  if (!scene || !sceneGroup || !materialCache) return

  const entity = sceneStore.reconstructed
  if (!entity) {
    // 清空蓝图实例，但保留场景灯光、地面和 GridHelper。
    clearSceneObjectResources(sceneGroup)
    materialCache.clear()
    // 重置相机到初始位置，确保GridHelper可见
    if (controls && camera) {
      controls.target.set(0, 0, 0)
      camera.position.set(12, 10, 12)
      controls.update()
    }
    hasFramedScene = false
    resetSceneBounds()
    ensureGridVisible()
    syncSelectionHighlights()
    syncComponentTransformControl()
    markNeedsRender()
    return
  }

  worldRuntime?.updateInstance('editor:active-blueprint', entity)
  markShadowsDirty()

  // 空场景（0 个构件）：重置相机到初始位置，防止上次的 camera 位置导致 grid 不可见
  if (!entity.meshes || entity.meshes.length === 0) {
    if (controls && camera) {
      controls.target.set(0, 0, 0)
      camera.position.set(12, 10, 12)
      controls.update()
    }
    resetSceneBounds()
    ensureGridVisible()
    syncSelectionHighlights()
    syncComponentTransformControl()
    return
  }

  if (entity.boundingBox) {
    const bbox = entity.boundingBox
    const center = new THREE.Vector3(
      (bbox.min[0] + bbox.max[0]) / 2,
      (bbox.min[1] + bbox.max[1]) / 2,
      (bbox.min[2] + bbox.max[2]) / 2
    )
    const size = new THREE.Vector3(
      bbox.max[0] - bbox.min[0],
      bbox.max[1] - bbox.min[1],
      bbox.max[2] - bbox.min[2]
    )
    const maxDim = Math.max(size.x, size.y, size.z)

    // ── 足迹居中归一化 ──
    // 生成器产出的是"角点对齐"坐标（例如 x 从 0 到 11.5，而不是 -5.75 到 5.75）。
    // 实测 7 份样例蓝图：5 份足迹中心偏离世界原点，4 份超过 0.5m，最大偏 6.4m；
    // 而网格、地面、内置环境全都钉在世界原点上 ⇒ 建筑看着明显偏到一边，
    // 偏移大的还会捅出 20×20 的网格范围（如 generated_modern_villa 的 x 跨 -0.5~11.5）。
    // 这里只做【显示层归一化】：把预览实例整体平移，让"足迹中心落在原点"。
    // 不碰文档坐标：拖拽改的是对象局部 position，保存读的是文档，两者都不受影响。
    // Y 不平移，以保持建筑与自身地面的关系（gridHelper.y = bbox.min[1]）。
    if (sceneGroup) sceneGroup.position.set(-center.x, 0, -center.z)
    // 归一化后模型在世界空间里就落在原点上，所以后续所有"以中心为参照"的逻辑
    // （方向光与阴影相机、内置环境、网格与地面）统一改用归一化后的中心。
    center.x = 0
    center.z = 0

    sceneBoundsCenter.copy(center)
    sceneBoundsSize.copy(size)
    hasSceneBounds = true
    environmentGroundY = bbox.min[1]

    updateLightingToBounds(center, size)
    if (shadowGround) shadowGround.position.y = bbox.min[1] - 0.002
    if (presentationGround) {
      presentationGround.position.y = bbox.min[1] - 0.004
      const groundSize = Math.max(200, maxDim * 12)
      presentationGround.scale.set(groundSize, groundSize, 1)
    }
    if (gridHelper) gridHelper.position.y = bbox.min[1]
    rebuildBuiltInEnvironment()

    if (!hasFramedScene && controls && camera) {
      frameCameraToBounds(center, size)
      hasFramedScene = true
    }
  }
  
  ensureGridVisible()
  applyViewMode()
  markNeedsRender()
}

function handlePointerDown(event: PointerEvent) {
  if (viewMode.value === 'presentation') return
  // 选择只响应主按键。右键由 contextmenu 独占，不能先改变选中高亮。
  if (event.button !== 0) {
    pointerDownPosition = null
    return
  }
  pointerDownPosition = { x: event.clientX, y: event.clientY }
}

function handlePointerUp(event: PointerEvent) {
  if (viewMode.value === 'presentation') return
  if (suppressSelectionClick) {
    suppressSelectionClick = false
    pointerDownPosition = null
    return
  }
  if (event.button !== 0) {
    pointerDownPosition = null
    return
  }
  if (!pointerDownPosition || !renderer || !camera || !sceneGroup) return
  const distance = Math.hypot(
    event.clientX - pointerDownPosition.x,
    event.clientY - pointerDownPosition.y,
  )
  pointerDownPosition = null
  if (distance > 5) return

  const rect = renderer.domElement.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return
  pointer.x = (event.clientX - rect.left) / rect.width * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)

  const hit = raycaster.intersectObjects(sceneGroup.children, true)
    .find(intersection => Boolean(getIntersectionElementId(intersection)))
  const elementId = hit ? getIntersectionElementId(hit) : null
  if (!elementId) {
    selectionStore.clearSelection()
    return
  }

  const mapping = sceneStore.reconstructed?.componentMapping
  const selectableId = mapping ? resolveSelectableId(elementId, mapping) : elementId
  const mode: SelectionMode = event.ctrlKey || event.metaKey
    ? 'toggle'
    : event.shiftKey
      ? 'add'
      : 'replace'
  selectionStore.setSelection(selectionAfterClick(selectionStore.selectedIds, selectableId, mode))
  uiStore.setRightActivePanel('properties')
}

/** 左键保留给选中高亮；右键命中窗扇、门扇或灯泡时执行对应交互。 */
function handleContextMenu(event: MouseEvent) {
  if (viewMode.value === 'presentation') return
  if (!renderer || !camera || !sceneGroup) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = (event.clientX - rect.left) / rect.width * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const intersections = raycaster.intersectObjects(sceneGroup.children, true)
  let interactionObject = intersections
    .find(intersection => intersection.object.userData.interaction)
    ?.object

  // 灯座与灯泡属于同一组件；右键命中灯座时转发给灯泡。窗户不做这种
  // 转发，确保点击左/右窗扇时只开合实际命中的那一扇。
  if (!interactionObject) {
    const mapping = sceneStore.reconstructed?.componentMapping
    const clickedElementId = intersections
      .map(getIntersectionElementId)
      .find((elementId): elementId is string => Boolean(elementId))
    if (mapping && clickedElementId) {
      const selectableId = resolveSelectableId(clickedElementId, mapping)
      const component = sceneStore.document?.blueprint.geometry.components
        ?.find(item => item.id === selectableId)
      if (component?.type === 'light') {
        sceneGroup.traverse(object => {
          if (interactionObject || object.userData.interaction?.kind !== 'light') return
          const elementId = typeof object.userData.elementId === 'string'
            ? object.userData.elementId
            : null
          if (elementId && resolveSelectableId(elementId, mapping) === selectableId) {
            interactionObject = object
          }
        })
      }
    }
  }

  if (interactionObject && toggleRuntimeInteraction(interactionObject, markNeedsRender)) {
    event.preventDefault()
  }
}

function getIntersectionElementId(intersection: THREE.Intersection): string | null {
  const object = intersection.object
  if (object instanceof THREE.InstancedMesh && typeof intersection.instanceId === 'number') {
    return object.userData.instanceElementIds?.[intersection.instanceId] || null
  }
  return typeof object.userData.elementId === 'string' ? object.userData.elementId : null
}

function syncSelectionHighlights() {
  clearSelectionHelpers()
  if (
    viewMode.value === 'presentation'
    || !scene
    || !sceneGroup
    || !sceneStore.reconstructed
  ) {
    markNeedsRender()
    return
  }

  const mapping = sceneStore.reconstructed.componentMapping
  sceneGroup.updateMatrixWorld(true)
  for (const selectedId of selectionStore.selectedIds) {
    const renderedIds = new Set(getRenderedElementIds(selectedId, mapping))
    const box = collectElementBounds(renderedIds)
    if (box.isEmpty()) continue
    const helper = new THREE.Box3Helper(box, 0x35d7ff)
    const material = helper.material as THREE.LineBasicMaterial
    helper.name = `Selection:${selectedId}`
    material.depthTest = false
    material.transparent = true
    material.opacity = 0.95
    helper.renderOrder = 999
    selectionHelpers.push(helper)
    scene.add(helper)
  }
  markNeedsRender()
}

function collectElementBounds(elementIds: Set<string>): THREE.Box3 {
  const bounds = new THREE.Box3()
  if (!sceneGroup) return bounds

  sceneGroup.traverse(object => {
    if (object instanceof THREE.InstancedMesh) {
      const ids = object.userData.instanceElementIds as Array<string | undefined> | undefined
      if (!ids) return
      object.geometry.computeBoundingBox()
      const geometryBounds = object.geometry.boundingBox
      if (!geometryBounds) return
      ids.forEach((elementId, index) => {
        if (!elementId || !elementIds.has(elementId)) return
        object.getMatrixAt(index, instanceMatrix)
        instanceWorldMatrix.multiplyMatrices(object.matrixWorld, instanceMatrix)
        bounds.union(geometryBounds.clone().applyMatrix4(instanceWorldMatrix))
      })
      return
    }
    if (!(object instanceof THREE.Mesh)) return
    const elementId = object.userData.elementId
    if (typeof elementId !== 'string' || !elementIds.has(elementId)) return
    object.geometry.computeBoundingBox()
    if (object.geometry.boundingBox) {
      bounds.union(object.geometry.boundingBox.clone().applyMatrix4(object.matrixWorld))
    }
  })
  return bounds
}

function clearSelectionHelpers() {
  for (const helper of selectionHelpers) {
    scene?.remove(helper)
    helper.geometry.dispose()
    const materials = Array.isArray(helper.material) ? helper.material : [helper.material]
    materials.forEach(material => material.dispose())
  }
  selectionHelpers = []
}

/** 仅给显式开启 draggable 的单选组合构件显示 Element 编辑器的三轴移动控件。 */
function syncComponentTransformControl() {
  clearComponentTransformControl()
  if (
    viewMode.value === 'presentation'
    || !scene
    || !sceneGroup
    || !transformControls
    || !sceneStore.reconstructed
    || selectionStore.selectedIds.length !== 1
  ) return
  const componentId = selectionStore.selectedIds[0]
  const component = sceneStore.document?.blueprint.geometry.components
    ?.find(item => item.id === componentId)
  if (!component?.draggable) return

  const renderedIds = new Set(getRenderedElementIds(
    componentId,
    sceneStore.reconstructed.componentMapping,
  ))
  const targets: THREE.Object3D[] = []
  sceneGroup.traverse(object => {
    if (!(object instanceof THREE.Mesh) || !object.userData.draggable) return
    const elementId = object.userData.elementId
    if (typeof elementId === 'string' && renderedIds.has(elementId)) targets.push(object)
  })
  if (targets.length === 0) return

  const bounds = collectElementBounds(renderedIds)
  if (bounds.isEmpty()) return
  dragAnchor = new THREE.Object3D()
  dragAnchor.name = `DragAnchor:${componentId}`
  bounds.getCenter(dragAnchor.position)
  scene.add(dragAnchor)
  transformControls.attach(dragAnchor)
  markNeedsRender()
}

function clearComponentTransformControl() {
  transformControls?.detach()
  if (dragAnchor?.parent) dragAnchor.parent.remove(dragAnchor)
  dragAnchor = null
  dragStartPosition = null
  dragComponentId = null
  dragTargetPositions.clear()
}

function handleTransformMouseDown() {
  if (!dragAnchor || selectionStore.selectedIds.length !== 1 || !sceneGroup) return
  suppressSelectionClick = true
  dragStartPosition = dragAnchor.position.clone()
  dragComponentId = selectionStore.selectedIds[0]
  dragTargetPositions.clear()
  const mapping = sceneStore.reconstructed?.componentMapping
  if (!mapping) return
  const renderedIds = new Set(getRenderedElementIds(dragComponentId, mapping))
  sceneGroup.traverse(object => {
    if (!(object instanceof THREE.Mesh) || !object.userData.draggable) return
    const elementId = object.userData.elementId
    if (typeof elementId === 'string' && renderedIds.has(elementId)) {
      dragTargetPositions.set(object, object.position.clone())
    }
  })
}

/**
 * 拖动过程中阴影重渲被节流到 120ms，若松手时刚好落在节流窗口内，
 * 阴影会停留在中间位置直到下一次失效（表现为"投影没跟上物体"）。
 * 这里补一个尾沿定时器：每次拖动都重置，停止后 120ms 保证落地最终状态。
 */
function scheduleTrailingShadowRefresh(): void {
  if (trailingShadowDirtyTimer !== null) clearTimeout(trailingShadowDirtyTimer)
  trailingShadowDirtyTimer = setTimeout(() => {
    trailingShadowDirtyTimer = null
    markShadowsDirty()
  }, SHADOW_DIRTY_THROTTLE_MS)
}

function handleTransformObjectChange() {
  if (!dragAnchor || !dragStartPosition) return
  const delta = dragAnchor.position.clone().sub(dragStartPosition)
  for (const [object, start] of dragTargetPositions) object.position.copy(start).add(delta)
  syncSelectionHighlights()
  markNeedsRender()
  // 拖动时阴影重渲节流：避免每帧重渲整张阴影图，拖动手感更跟手。
  const now = performance.now()
  if (now - lastShadowDirtyTime >= SHADOW_DIRTY_THROTTLE_MS) {
    lastShadowDirtyTime = now
    markShadowsDirty()
  }
  scheduleTrailingShadowRefresh()
}

function handleTransformDraggingChanged(event: { value?: unknown }) {
  if (controls) controls.enabled = event.value !== true
}

function handleTransformMouseUp() {
  if (!dragAnchor || !dragStartPosition || !dragComponentId || !sceneStore.document) return
  const delta = dragAnchor.position.clone().sub(dragStartPosition)
  if (delta.lengthSq() < 1e-10) {
    // 零净位移（拖出去又拖回原位）：不会产生 patch，也就不会走 updateScene → markShadowsDirty，
    // 而中间过程的阴影可能已经按中间位置渲染过，所以这里必须补一次刷新。
    markShadowsDirty()
    return
  }
  const component = sceneStore.document.blueprint.geometry.components
    ?.find(item => item.id === dragComponentId)
  if (!component) return
  const changes = createComponentTranslationChanges(
    component,
    [delta.x, delta.y, delta.z],
    sceneStore.document.blueprint.geometry.elements,
  )
  const patch = createPatch(
    sceneStore.document.revision,
    [{ op: 'update_component', id: component.id, changes }],
    'user',
    false,
    `拖动${component.id}`,
  )
  transformControls?.detach()
  void sceneStore.applyPatch(patch).then(applied => {
    if (!applied) updateScene()
  })
}

function cycleEnvironmentPreset() {
  const nextIndex = (ENVIRONMENT_ORDER.indexOf(environmentPresetId.value) + 1) % ENVIRONMENT_ORDER.length
  environmentPresetId.value = ENVIRONMENT_ORDER[nextIndex]
  rebuildBuiltInEnvironment()
  // 环境档切换是离散动作：地面色/雾色/太阳方位角都变了，必须立即重建环境贴图。
  applyTimePreset(true)
}

function environmentColor(kind: 'groundColor' | 'fogColor') {
  const environmentColorValue = ENVIRONMENT_PRESETS[environmentPresetId.value][kind]
  const timeColorValue = TIME_PRESETS[timeOfDay.value][kind]
  const timeBlend = timeOfDay.value === 'night' ? 0.76 : timeOfDay.value === 'sunset' ? 0.42 : 0.08
  const atmosphere = deriveWorldAtmosphere(
    getWorldEnvironmentState(),
    getWorldRenderingState().weatherEnabled,
  )
  const weatherColor = kind === 'groundColor' ? atmosphere.groundTint : atmosphere.fogColor
  return new THREE.Color(environmentColorValue)
    .lerp(new THREE.Color(timeColorValue), timeBlend)
    .lerp(new THREE.Color(weatherColor), atmosphere.tintStrength)
}

function applyEnvironmentAppearance() {
  if (presentationGround) {
    presentationGround.material.color.copy(environmentColor('groundColor'))
    presentationGround.material.needsUpdate = true
  }
  if (scene?.fog) {
    scene.fog.color.copy(environmentColor('fogColor'))
  }
}

function clearBuiltInEnvironment() {
  if (!builtInEnvironment) return
  const geometries = new Set<THREE.BufferGeometry>()
  const materials = new Set<THREE.Material>()
  builtInEnvironment.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return
    geometries.add(object.geometry)
    const objectMaterials = Array.isArray(object.material) ? object.material : [object.material]
    objectMaterials.forEach(material => materials.add(material))
  })
  builtInEnvironment.clear()
  geometries.forEach(geometry => geometry.dispose())
  materials.forEach(material => material.dispose())
}

function addDistantHills(group: THREE.Group, radius: number, colors: number[], count = 3) {
  const geometry = new THREE.SphereGeometry(1, 24, 12)
  const materials = colors.map(color => new THREE.MeshStandardMaterial({
    color,
    roughness: 1,
    metalness: 0,
  }))
  for (let index = 0; index < count; index += 1) {
    const angle = index / count * Math.PI * 2 + 0.35
    const distance = radius * (1.04 + (index % 2) * 0.08)
    const width = radius * (0.36 + (index % 2) * 0.07)
    const height = radius * (0.065 + (index % 3) * 0.012)
    const hill = new THREE.Mesh(geometry, materials[index % materials.length])
    hill.position.set(Math.cos(angle) * distance, -height * 0.72, Math.sin(angle) * distance)
    hill.scale.set(width, height, width * (0.72 + (index % 2) * 0.08))
    hill.rotation.y = angle * 0.7
    group.add(hill)
  }
}

function addSparseTrees(group: THREE.Group, radius: number, colors: number[], count: number) {
  const treeScale = Math.max(0.75, Math.min(2.2, lightingExtent / 7))
  const trunkGeometry = new THREE.CylinderGeometry(0.13, 0.18, 1.6, 7)
  const crownGeometry = new THREE.ConeGeometry(0.82, 2.25, 9)
  const trunks = new THREE.InstancedMesh(
    trunkGeometry,
    new THREE.MeshStandardMaterial({ color: 0x6b4930, roughness: 1 }),
    count,
  )
  const crowns = new THREE.InstancedMesh(
    crownGeometry,
    new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.96 }),
    count,
  )
  const transform = new THREE.Object3D()
  for (let index = 0; index < count; index += 1) {
    const angle = index / count * Math.PI * 2 + 0.5 + Math.sin(index * 2.7) * 0.12
    const distance = radius * (0.88 + (index % 3) * 0.08)
    const scale = treeScale * (0.82 + (index % 3) * 0.09)
    const x = Math.cos(angle) * distance
    const z = Math.sin(angle) * distance

    transform.position.set(x, 0.8 * scale, z)
    transform.scale.setScalar(scale)
    transform.updateMatrix()
    trunks.setMatrixAt(index, transform.matrix)

    transform.position.set(x, 2.58 * scale, z)
    transform.rotation.y = angle
    transform.updateMatrix()
    crowns.setMatrixAt(index, transform.matrix)
    crowns.setColorAt(index, new THREE.Color(colors[index % colors.length]))
  }
  trunks.instanceMatrix.needsUpdate = true
  crowns.instanceMatrix.needsUpdate = true
  if (crowns.instanceColor) crowns.instanceColor.needsUpdate = true
  group.add(trunks, crowns)
}

function addAlpineMountains(group: THREE.Group, radius: number) {
  const mountainGeometry = new THREE.ConeGeometry(1, 1, 7)
  const snowGeometry = new THREE.ConeGeometry(1, 1, 7)
  const rockMaterials = [0x66727a, 0x77838a, 0x58656d].map(color => (
    new THREE.MeshStandardMaterial({ color, roughness: 0.98 })
  ))
  const snowMaterial = new THREE.MeshStandardMaterial({ color: 0xf2f6f8, roughness: 0.82 })
  const count = 5
  for (let index = 0; index < count; index += 1) {
    const angle = index / count * Math.PI * 2 + 0.28
    const distance = radius * (1.02 + (index % 2) * 0.1)
    const base = radius * (0.18 + (index % 3) * 0.03)
    const height = radius * (0.38 + (index % 3) * 0.06)
    const mountain = new THREE.Mesh(mountainGeometry, rockMaterials[index % rockMaterials.length])
    mountain.position.set(Math.cos(angle) * distance, height / 2, Math.sin(angle) * distance)
    mountain.scale.set(base, height, base)
    mountain.rotation.y = angle
    group.add(mountain)

    const capHeight = height * 0.38
    const snowCap = new THREE.Mesh(snowGeometry, snowMaterial)
    snowCap.position.set(mountain.position.x, height - capHeight / 2, mountain.position.z)
    snowCap.scale.set(base * 0.42, capHeight, base * 0.42)
    snowCap.rotation.y = angle
    group.add(snowCap)
  }
}

function addDesertRocks(group: THREE.Group, radius: number) {
  const geometry = new THREE.DodecahedronGeometry(1, 0)
  const materials = [0x8f5f3d, 0xa8744c, 0x74503b].map(color => (
    new THREE.MeshStandardMaterial({ color, roughness: 1 })
  ))
  for (let index = 0; index < 3; index += 1) {
    const angle = index / 3 * Math.PI * 2 + 0.65
    const distance = radius * (0.78 + (index % 2) * 0.1)
    const size = Math.max(0.45, Math.min(2.3, lightingExtent / 8)) * (0.7 + (index % 3) * 0.28)
    const rock = new THREE.Mesh(geometry, materials[index % materials.length])
    rock.position.set(Math.cos(angle) * distance, size * 0.55, Math.sin(angle) * distance)
    rock.scale.set(size * 1.25, size, size * 0.85)
    rock.rotation.set(index * 0.17, angle, index * 0.11)
    group.add(rock)
  }
}

function rebuildBuiltInEnvironment() {
  if (!builtInEnvironment) return
  clearBuiltInEnvironment()
  builtInEnvironment.position.set(sceneBoundsCenter.x, environmentGroundY, sceneBoundsCenter.z)
  const presetId = environmentPresetId.value
  builtInEnvironment.visible = presetId !== 'minimal'
  if (presetId === 'minimal') {
    markNeedsRender()
    return
  }

  // 环境只提供远处轮廓，主体观感由天空、主光与软阴影承担。
  const radius = Math.max(30, lightingExtent * 3.6)
  if (presetId === 'meadow') {
    addDistantHills(builtInEnvironment, radius, [0x45613d, 0x56734a, 0x678058], 3)
    addSparseTrees(builtInEnvironment, radius, [0x315d32, 0x426d39, 0x537b43], 4)
  } else if (presetId === 'alpine') {
    addAlpineMountains(builtInEnvironment, radius)
  } else if (presetId === 'desert') {
    addDistantHills(builtInEnvironment, radius, [0xa76c3d, 0xbc8047, 0xc99458], 4)
    addDesertRocks(builtInEnvironment, radius)
  } else {
    addDistantHills(builtInEnvironment, radius, [0x595534, 0x6a5d35, 0x766440], 3)
    addSparseTrees(builtInEnvironment, radius, [0x8b3c20, 0xaa5524, 0xc4772d, 0x71321f], 5)
  }
  markNeedsRender()
}

function cycleTimeOfDay() {
  const nextIndex = (TIME_ORDER.indexOf(timeOfDay.value) + 1) % TIME_ORDER.length
  const next = TIME_ORDER[nextIndex]
  // 只写世界环境状态：订阅回调里的 syncTimePresetFromWorldEnvironment() 会检测到时段变化，
  // 并把这次变更当作【离散切换】处理（force = true），环境贴图随即立即重建。
  // 这里不要抢先改 timeOfDay.value —— 否则 sync 会认为"没变化"，退化成 120ms 的节流路径。
  updateWorldEnvironmentState({
    timeOfDay: next === 'day' ? 12 : next === 'sunset' ? 18 : 0,
  })
}

/** 依据世界环境的 timeOfDay 同步时段预设；返回是否发生了时段切换（离散切换需强制重建环境贴图）。 */
function syncTimePresetFromWorldEnvironment(): boolean {
  const hour = getWorldEnvironmentState().timeOfDay
  const next: TimeOfDay = hour < 6 || hour >= 21
    ? 'night'
    : hour >= 16
      ? 'sunset'
      : 'day'
  if (timeOfDay.value === next) return false
  timeOfDay.value = next
  return true
}

function applyTimePreset(forceEnvironment = false) {
  if (!renderer || !scene || !sky || !hemisphereLight || !directionalLight) return
  const preset = TIME_PRESETS[timeOfDay.value]
  const environmentPreset = ENVIRONMENT_PRESETS[environmentPresetId.value]
  const worldLook = worldLookRuntime.getActiveProfile().appearance
  const directLightScale = worldLook?.directLightScale ?? 1
  const ambientLightScale = worldLook?.ambientLightScale ?? 1
  const exposureScale = worldLook?.exposureScale ?? 1
  const shadowOpacityScale = worldLook?.shadowOpacity ?? 1
  const worldEnvironment = getWorldEnvironmentState()
  const weatherEnabled = getWorldRenderingState().weatherEnabled
  const atmosphere = deriveWorldAtmosphere(worldEnvironment, weatherEnabled)

  sunDirection.setFromSphericalCoords(
    1,
    THREE.MathUtils.degToRad(preset.sunPhi),
    THREE.MathUtils.degToRad(preset.sunTheta + environmentPreset.sunAzimuthOffset),
  )
  // 主光方向：夜晚 sunPhi = 108° 使太阳落到地平线之下，此时主光取月亮方向（= −sunDirection），
  // 与 moonBody 一致；否则主光会被放到地面之下面朝上打光，整晚没有有效方向光。
  // 天空 uniform、太阳/月亮实体、环境贴图太阳亮点继续用 sunDirection，不受影响。
  keyLightDirection.copy(sunDirection)
  if (timeOfDay.value === 'night') keyLightDirection.negate()

  sky.visible = preset.skyVisible
  syncSkyPreset(sky, preset, atmosphere, sunDirection)

  scene.background = new THREE.Color(preset.background)
    .lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength)
  // 环境贴图（PMREM）重建很贵：一遍立方图 6 面渲染 + 卷积 + 纹理创建/销毁。
  // 天气滑杆是连续 @input，一个拖动动作会打出上百个事件 ⇒ 必须去重 + 节流。
  scheduleEnvironmentRebuild(preset, atmosphere, forceEnvironment)
  renderer.toneMappingExposure = preset.exposure
    * environmentPreset.exposureScale
    * exposureScale
    * atmosphere.exposureScale

  hemisphereLight.color.setHex(preset.hemisphereSkyColor)
    .lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength * 0.38)
  hemisphereLight.groundColor.setHex(preset.hemisphereGroundColor)
    .lerp(new THREE.Color(atmosphere.groundTint), atmosphere.tintStrength * 0.38)
  hemisphereLight.intensity = preset.hemisphereIntensity
    * environmentPreset.ambientLightScale
    * ambientLightScale
    * atmosphere.ambientLightScale
  directionalLight.color.setHex(preset.directionalColor)
    .lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength * 0.22)
  directionalLight.intensity = preset.directionalIntensity
    * environmentPreset.directLightScale
    * directLightScale
    * atmosphere.directLightScale
  weatherVisuals?.setEnvironment(worldEnvironment, weatherEnabled)
  applyEnvironmentAppearance()
  if (bloomPass) {
    bloomPass.enabled = QUALITY_PRESETS[qualityLevel.value].bloom && timeOfDay.value === 'night'
  }
  if (shadowGround) {
    const timeShadowScale = timeOfDay.value === 'night' ? 0.36 : timeOfDay.value === 'sunset' ? 0.88 : 1
    // 贴花是半透明暗色覆盖层，颜色也要对齐当前环境的地面色相，
    // 否则沙漠（色相偏差 118°）、秋林（103°）这种暖色地面上会出现"冷绿黑"的投影。
    // 系数取线性空间等亮度比：原先 0x26352d 在极简地面 0x747b73 上的亮度比 ≈ 0.162，
    // 换成"地面色 × 0.162"后极简档观感不变，其余环境自动跟随地面色相。
    shadowGround.material.color
      .setHex(environmentPreset.groundColor)
      .multiplyScalar(SHADOW_DECAL_LUMA_RATIO)
      .lerp(
        new THREE.Color(atmosphere.groundTint).multiplyScalar(SHADOW_DECAL_LUMA_RATIO),
        atmosphere.tintStrength * 0.5,
      )
    shadowGround.material.opacity = environmentPreset.shadowOpacity
      * timeShadowScale
      * shadowOpacityScale
    shadowGround.material.needsUpdate = true
  }

  updateLightingToBounds(lightingCenter, sceneBoundsSize)
  applyViewMode()
  markNeedsRender()
}

/**
 * 环境贴图重建的调度入口。
 *
 * 机制（PMREM 生产、签名去重、前后沿节流、旧纹理释放）全部在引擎侧的
 * `WorldEnvironmentMapRuntime` 里；这里只负责把**当前策略**喂进去：
 * 用哪个时段预设、当前大气参数、太阳方向、是不是夜晚。
 *
 * 离散切换（时段/环境档/画质档/WILD profile）传 force = true 绕过去重与节流，
 * 避免"点了一下但画面没跟着变"。
 */
function scheduleEnvironmentRebuild(
  preset: TimePreset,
  atmosphere: WorldAtmosphereAppearance,
  force: boolean,
): void {
  environmentRuntime?.schedule(preset, atmosphere, sunDirection, timeOfDay.value === 'night', force)
}

function createGroundTexture(): THREE.CanvasTexture {
  // 程序化地面纹理：低分辨率噪点色块，让纯色地面有轻微质感（草/土/石混合），
  // 128x128 + RepeatWrapping，放大后不显著，成本可忽略。
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')
  if (context) {
    const base = [0x74, 0x7b, 0x73]
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        // 确定性 hash 噪点，避免每个像素随机数开销。
        const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
        const frac = n - Math.floor(n)
        const jitter = (frac - 0.5) * 22
        const r = Math.max(0, Math.min(255, base[0] + jitter))
        const g = Math.max(0, Math.min(255, base[1] + jitter * 0.9))
        const b = Math.max(0, Math.min(255, base[2] + jitter * 0.7))
        context.fillStyle = `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`
        context.fillRect(x, y, 1, 1)
      }
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(24, 24)
  return texture
}

function updateCelestialBodies(center = lightingCenter, extent = lightingExtent): void {
  if (!sunBody || !moonBody) return
  const atmosphere = deriveWorldAtmosphere(
    getWorldEnvironmentState(),
    getWorldRenderingState().weatherEnabled,
  )
  const radius = Math.max(72, extent * 5.5)
  const size = Math.max(4.2, radius * 0.055)
  sunBody.position.copy(center).addScaledVector(sunDirection, radius)
  moonBody.position.copy(center).addScaledVector(sunDirection, -radius)
  sunBody.scale.set(size * 1.62, size * 1.62, 1)
  moonBody.scale.set(size, size, 1)
  sunBody.visible = timeOfDay.value !== 'night'
  moonBody.visible = timeOfDay.value === 'night'
  ;(sunBody.material as THREE.SpriteMaterial).opacity = Math.max(
    0.12,
    1 - atmosphere.cloud * 0.76 - atmosphere.rain * 0.18 - atmosphere.fog * 0.32,
  )
  ;(moonBody.material as THREE.SpriteMaterial).opacity = Math.max(
    0.2,
    0.92 - atmosphere.cloud * 0.58 - atmosphere.fog * 0.28,
  )
}

function toggleViewMode() {
  viewMode.value = viewMode.value === 'editor' ? 'presentation' : 'editor'
  applyViewMode()
}

function applyGroundVisibility() {
  if (!presentationGround) return
  const presenting = viewMode.value === 'presentation'
  const scenic = environmentPresetId.value !== 'minimal'
  const effects = getWorldEffectState()
  presentationGround.visible = presenting || scenic
    || effects.puddles || effects.ripples || effects.reflections
}

function configureSceneFog() {
  if (!scene) return
  const atmosphere = deriveWorldAtmosphere(
    getWorldEnvironmentState(),
    getWorldRenderingState().weatherEnabled,
  )
  const presenting = viewMode.value === 'presentation'
  if (presenting || atmosphere.fog > 0.025) {
    const baseFogNear = Math.max(60, lightingExtent * 5)
    const fogNear = baseFogNear * (1 - atmosphere.fog * 0.82)
    const fogScale = worldLookRuntime.getActiveProfile().appearance?.fogScale ?? 1
    const fogFar = fogNear + Math.max(180, lightingExtent * 16)
      * fogScale
      * Math.max(0.1, 1 - atmosphere.fog * 0.84)
    const fogColor = environmentColor('fogColor')
    if (getWorldEffectUniforms().volumetricFog.value > 0.5) {
      scene.fog = new THREE.FogExp2(fogColor, Math.max(0.0008, 2.4 / Math.max(1, fogFar - fogNear)))
    } else {
      scene.fog = new THREE.Fog(fogColor, fogNear, fogFar)
    }
  } else {
    scene.fog = null
  }
}

function applyViewMode() {
  if (!scene) return
  const presenting = viewMode.value === 'presentation'
  const scenic = environmentPresetId.value !== 'minimal'
  if (gridHelper) gridHelper.visible = !presenting
  if (shadowGround) shadowGround.visible = true
  applyGroundVisibility()
  if (builtInEnvironment) builtInEnvironment.visible = scenic
  if (transformControls) transformControls.visible = !presenting
  if (presenting) {
    clearSelectionHelpers()
    clearComponentTransformControl()
  } else {
    syncSelectionHighlights()
    syncComponentTransformControl()
  }
  configureSceneFog()
  markNeedsRender()
}

function cycleQuality() {
  const nextIndex = (QUALITY_ORDER.indexOf(qualityLevel.value) + 1) % QUALITY_ORDER.length
  qualityLevel.value = QUALITY_ORDER[nextIndex]
  applyQualityPreset()
}

function applyQualityPreset() {
  if (!renderer) return
  // 手动切档会重置自适应降级标记，允许回到更高质量档。
  adaptiveQualityApplied = false
  const preset = QUALITY_PRESETS[qualityLevel.value]
  updateWorldRenderingState({
    surfaceQuality: qualityLevel.value,
    weatherQuality: worldLookRuntime.getActiveProfile().quality?.weatherTier || qualityLevel.value,
  })
  const pixelRatio = Math.min(window.devicePixelRatio || 1, preset.pixelRatio)
  renderer.setPixelRatio(pixelRatio)
  postProcessing?.setPixelRatio(pixelRatio)
  if (lightingRig) {
    lightingRig.setShadowMapSize(preset.shadowMapSize, renderer.capabilities.maxTextureSize)
    markShadowsDirty()
  }
  if (ssaoPass) ssaoPass.enabled = preset.ssao
  if (bloomPass) bloomPass.enabled = preset.bloom && timeOfDay.value === 'night'
  configureMaterialRendering(renderer.capabilities.getMaxAnisotropy(), markNeedsRender)
  handleResize()
}

function cycleCameraPreset() {
  const nextIndex = (CAMERA_ORDER.indexOf(cameraPresetId.value) + 1) % CAMERA_ORDER.length
  cameraPresetId.value = CAMERA_ORDER[nextIndex]
  if (hasSceneBounds) frameCameraToBounds(sceneBoundsCenter, sceneBoundsSize)
}

function updateLightingToBounds(center: THREE.Vector3, size: THREE.Vector3) {
  if (!lightingRig) return
  lightingCenter.copy(center)
  const maxDim = Math.max(size.x, size.y, size.z)
  // 场景尺度参照（内置环境 / 日月 / 天气层 / 雾）仍按模型尺寸，不随太阳角度变化。
  lightingExtent = Math.max(maxDim * 0.68, 4)

  // 阴影正交框 / 光位 / bias 的推导是纯机制，全部在引擎侧 WorldLightingRig.fitToBounds()：
  // 那一套参数互相耦合，任何别的渲染方都要拿到同一份推导，否则"同一蓝图两套光影"。
  const fit = lightingRig.fitToBounds(center, size, keyLightDirection, {
    onShadowsDirty: markShadowsDirty,
  })
  shadowExtent = fit.extent
  updateCelestialBodies(center, lightingExtent)
  weatherVisuals?.setBounds(center, lightingExtent, environmentGroundY)
  configureSceneFog()
}

function frameCameraToBounds(center: THREE.Vector3, size: THREE.Vector3) {
  if (!camera || !controls) return
  const verticalFov = THREE.MathUtils.degToRad(camera.fov)
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect)
  const verticalDistance = size.y / Math.max(2 * Math.tan(verticalFov / 2), 0.01)
  const horizontalDistance = Math.max(size.x, size.z) / Math.max(2 * Math.tan(horizontalFov / 2), 0.01)
  const distance = Math.max(verticalDistance, horizontalDistance, 2) * 1.50  // 从 1.55 降低到 1.50，更接近建筑
  const preset = CAMERA_PRESETS[cameraPresetId.value]
  const viewDirection = new THREE.Vector3(...preset.direction).normalize()
  const target = center.clone()
  if (cameraPresetId.value === 'human') {
    target.y = center.y - size.y / 2 + Math.min(1.7, Math.max(0.8, size.y * 0.25))
  }
  controls.target.copy(target)
  controls.minDistance = Math.max(0.2, distance * 0.08)
  controls.maxDistance = Math.max(50, distance * 8)
  camera.position.copy(target).addScaledVector(viewDirection, distance)
  camera.near = Math.max(0.03, distance / 500)
  camera.far = Math.max(500, distance * 20)
  camera.updateProjectionMatrix()
  controls.update()
}

function markNeedsRender() {
  needsRender = true
  scheduleRenderFrame()
}

function markShadowsDirty() {
  if (!renderer || !directionalLight) return
  renderer.shadowMap.needsUpdate = true
  directionalLight.shadow.needsUpdate = true
  // shadowMap.needsUpdate 只在【下一次 renderer.render()】里被消费并清零（autoUpdate=false）。
  // 只置位不请求渲染会有两种失效：
  //   1) 此刻队列里没有任何待渲染帧（相机静止、无动画）→ 标记永远悬空，阴影不刷新；
  //   2) 已有帧在排队 → 该帧可能在本 tick 的几何/变换写入落地之前就被执行并清零标记，
  //      于是阴影按旧姿态烘焙，之后也不再补算。
  // 这里显式请求一次渲染：requestAnimationFrame 回调在所有同步写与微任务（Vue watcher）之后执行，
  // 保证重算阴影时场景图已是最终状态。
  markNeedsRender()
}

function cleanup() {
  renderLoopActive = false
  if (animationFrameId !== null) cancelAnimationFrame(animationFrameId)
  animationFrameId = null
  if (trailingShadowDirtyTimer !== null) {
    clearTimeout(trailingShadowDirtyTimer)
    trailingShadowDirtyTimer = null
  }
  resizeObserver?.disconnect()
  resizeObserver = null
  window.removeEventListener('resize', handleResize)
  renderer?.domElement.removeEventListener('pointerdown', handlePointerDown)
  renderer?.domElement.removeEventListener('pointerup', handlePointerUp)
  renderer?.domElement.removeEventListener('contextmenu', handleContextMenu)
  clearSelectionHelpers()
  clearComponentTransformControl()
  if (worldRuntime) worldRuntime.dispose()
  else if (materialCache) materialCache.clear()
  if (controls) controls.removeEventListener('change', markNeedsRender)
  weatherVisuals?.dispose()
  weatherVisuals = null
  cloudLayer?.dispose()
  cloudLayer = null
  for (const body of [sunBody, moonBody]) {
    if (!body) continue
    body.removeFromParent()
    const material = body.material as THREE.SpriteMaterial
    material.map?.dispose()
    material.dispose()
  }
  sunBody = null
  moonBody = null
  sky?.geometry.dispose()
  sky?.material.dispose()
  // 环境贴图（PMREM target + 离屏环境场景 + 太阳精灵）的释放统一交给运行时。
  environmentRuntime?.dispose()
  environmentRuntime = null
  lightingRig?.dispose()
  lightingRig = null
  clearBuiltInEnvironment()
  shadowGround?.geometry.dispose()
  shadowGround?.material.dispose()
  presentationGround?.geometry.dispose()
  const groundMaterial = presentationGround?.material
  if (groundMaterial && 'map' in groundMaterial) {
    ;(groundMaterial as THREE.MeshStandardMaterial).map?.dispose()
  }
  groundMaterial?.dispose()
  // 后期合成链路（含 SSAO / Bloom / FXAA 三张 pass 与合成 RT）统一由运行时释放。
  postProcessing?.dispose()
  postProcessing = null
  configureMaterialRendering(1)
  disposeKtx2Rendering()
  worldLookRuntime.setActivationContext(undefined)
  if (renderer) renderer.dispose()
  if (controls) controls.dispose()
  if (transformControls) {
    scene?.remove(transformControls)
    transformControls.dispose()
  }
}
</script>

<style scoped>
.canvas-viewport {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
}

canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.viewport-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
}

.stats {
  position: absolute;
  top: 12px;
  left: 12px;
  background: rgba(0, 0, 0, 0.6);
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #cccccc;
  font-family: monospace;
}

.stats>div {
  margin: 2px 0;
}

.viewport-toolbar {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  pointer-events: auto;
}

.viewport-action {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 76px;
  padding: 8px 12px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(18, 23, 33, 0.78);
  color: #f4f7fb;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}

.viewport-action:hover,
.viewport-action.active {
  background: rgba(28, 36, 50, 0.92);
  border-color: rgba(255, 255, 255, 0.36);
}

.viewport-action:active {
  transform: translateY(1px);
}

.fps-meter {
  position: absolute;
  right: 12px;
  bottom: 12px;
  padding: 5px 10px;
  border-radius: 6px;
  background: rgba(18, 23, 33, 0.72);
  color: #8bd450;
  font-family: monospace;
  font-size: 12px;
  line-height: 1;
  backdrop-filter: blur(8px);
}

.fps-meter.ok {
  color: #e6c34a;
}

.fps-meter.bad {
  color: #e06a5a;
}

.viewport-action:focus-visible {
  outline: 2px solid #8fc7ff;
  outline-offset: 2px;
}

@media (max-width: 760px) {
  .viewport-toolbar {
    align-items: flex-end;
    flex-direction: column;
  }

  .viewport-action {
    min-width: 70px;
    padding: 7px 9px;
    font-size: 12px;
  }
}

.diagnostics {
  color: #ffd27a;
}
</style>
