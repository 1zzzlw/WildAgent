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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { useUIStore } from '../../stores/uiStore'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { Sky } from 'three/examples/jsm/objects/Sky.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { FXAAShader } from 'three/examples/jsm/shaders/FXAAShader.js'
import { configureMaterialRendering, MaterialCache } from '../../renderer/materialAdapter'
import { toggleRuntimeInteraction, updateSceneGroup } from '../../renderer/renderEntity'
import { getRenderedElementIds, resolveSelectableId } from '../../wild/componentSelection'
import { createComponentTranslationChanges } from '../../wild/componentDrag'
import { createPatch } from '../../wild/scenePatch'

const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const uiStore = useUIStore()

type TimeOfDay = 'day' | 'sunset' | 'night'
type ViewMode = 'editor' | 'presentation'
type QualityLevel = 'low' | 'medium' | 'high'
type CameraPresetId = 'corner' | 'human' | 'bird' | 'front'
type EnvironmentPresetId = 'minimal' | 'meadow' | 'alpine' | 'desert' | 'autumn'

interface TimePreset {
  label: string
  icon: string
  background: number
  exposure: number
  skyVisible: boolean
  turbidity: number
  rayleigh: number
  mieCoefficient: number
  mieDirectionalG: number
  sunPhi: number
  sunTheta: number
  directionalColor: number
  directionalIntensity: number
  hemisphereSkyColor: number
  hemisphereGroundColor: number
  hemisphereIntensity: number
  groundColor: number
  fogColor: number
}

interface QualityPreset {
  label: string
  pixelRatio: number
  shadowMapSize: number
  ssao: boolean
  bloom: boolean
}

interface CameraPreset {
  label: string
  direction: [number, number, number]
}

interface EnvironmentPreset {
  label: string
  icon: string
  groundColor: number
  fogColor: number
  sunAzimuthOffset: number
  directLightScale: number
  ambientLightScale: number
  exposureScale: number
  shadowOpacity: number
}

const TIME_ORDER: TimeOfDay[] = ['day', 'sunset', 'night']
const TIME_PRESETS: Record<TimeOfDay, TimePreset> = {
  day: {
    label: '白天',
    icon: '☀️',
    background: 0xb9c9d8,
    exposure: 1.05,
    skyVisible: true,
    turbidity: 4,
    rayleigh: 1.5,
    mieCoefficient: 0.006,
    mieDirectionalG: 0.82,
    sunPhi: 52,
    sunTheta: 135,
    directionalColor: 0xfff4df,
    directionalIntensity: 2.4,
    hemisphereSkyColor: 0xddeeff,
    hemisphereGroundColor: 0x665544,
    hemisphereIntensity: 0.75,
    groundColor: 0x7c8378,
    fogColor: 0xb9c9d8,
  },
  sunset: {
    label: '黄昏',
    icon: '🌇',
    background: 0x6f4054,
    exposure: 0.9,
    skyVisible: true,
    turbidity: 10,
    rayleigh: 2.8,
    mieCoefficient: 0.02,
    mieDirectionalG: 0.9,
    sunPhi: 84,
    sunTheta: 245,
    directionalColor: 0xff8a4c,
    directionalIntensity: 1.65,
    hemisphereSkyColor: 0xffa27d,
    hemisphereGroundColor: 0x34283f,
    hemisphereIntensity: 0.45,
    groundColor: 0x5b4b48,
    fogColor: 0x6f4054,
  },
  night: {
    label: '夜晚',
    icon: '🌙',
    background: 0x050914,
    exposure: 0.68,
    skyVisible: false,
    turbidity: 2,
    rayleigh: 0.2,
    mieCoefficient: 0.001,
    mieDirectionalG: 0.7,
    sunPhi: 108,
    sunTheta: 220,
    directionalColor: 0x9dbbff,
    directionalIntensity: 0.32,
    hemisphereSkyColor: 0x182442,
    hemisphereGroundColor: 0x08070d,
    hemisphereIntensity: 0.2,
    groundColor: 0x111722,
    fogColor: 0x050914,
  },
}

const QUALITY_ORDER: QualityLevel[] = ['low', 'medium', 'high']
const QUALITY_PRESETS: Record<QualityLevel, QualityPreset> = {
  low: { label: '流畅', pixelRatio: 1, shadowMapSize: 1024, ssao: false, bloom: false },
  medium: { label: '均衡', pixelRatio: 1.5, shadowMapSize: 2048, ssao: true, bloom: false },
  high: { label: '精细', pixelRatio: 2, shadowMapSize: 4096, ssao: true, bloom: true },
}
const CAMERA_ORDER: CameraPresetId[] = ['corner', 'human', 'bird', 'front']
const CAMERA_PRESETS: Record<CameraPresetId, CameraPreset> = {
  corner: { label: '街角', direction: [1, 0.62, 1] },
  human: { label: '人视', direction: [1, 0.18, 1] },
  bird: { label: '鸟瞰', direction: [0.8, 1.25, 0.8] },
  front: { label: '正立面', direction: [0, 0.12, 1] },
}
const ENVIRONMENT_ORDER: EnvironmentPresetId[] = ['minimal', 'meadow', 'alpine', 'desert', 'autumn']
const ENVIRONMENT_PRESETS: Record<EnvironmentPresetId, EnvironmentPreset> = {
  minimal: {
    label: '极简', icon: '◻️', groundColor: 0x747b73, fogColor: 0xb9c9d8,
    sunAzimuthOffset: 0, directLightScale: 1, ambientLightScale: 0.9, exposureScale: 1,
    shadowOpacity: 0.22,
  },
  meadow: {
    label: '草地', icon: '🌿', groundColor: 0x526d42, fogColor: 0xadc2ae,
    sunAzimuthOffset: -18, directLightScale: 1.16, ambientLightScale: 0.72, exposureScale: 0.96,
    shadowOpacity: 0.28,
  },
  alpine: {
    label: '雪山', icon: '🏔️', groundColor: 0xc9d1d5, fogColor: 0xc6d2da,
    sunAzimuthOffset: 16, directLightScale: 1.22, ambientLightScale: 0.82, exposureScale: 0.92,
    shadowOpacity: 0.3,
  },
  desert: {
    label: '沙漠', icon: '🏜️', groundColor: 0xb9844f, fogColor: 0xd2ad7f,
    sunAzimuthOffset: 30, directLightScale: 1.3, ambientLightScale: 0.66, exposureScale: 0.92,
    shadowOpacity: 0.34,
  },
  autumn: {
    label: '秋林', icon: '🍂', groundColor: 0x665c3d, fogColor: 0xb39a78,
    sunAzimuthOffset: -32, directLightScale: 1.18, ambientLightScale: 0.68, exposureScale: 0.92,
    shadowOpacity: 0.32,
  },
}

const timeOfDay = ref<TimeOfDay>('day')
const viewMode = ref<ViewMode>('editor')
const qualityLevel = ref<QualityLevel>('medium')
const cameraPresetId = ref<CameraPresetId>('corner')
const environmentPresetId = ref<EnvironmentPresetId>('minimal')
const activeTimePreset = computed(() => TIME_PRESETS[timeOfDay.value])
const activeQualityPreset = computed(() => QUALITY_PRESETS[qualityLevel.value])
const activeCameraPreset = computed(() => CAMERA_PRESETS[cameraPresetId.value])
const activeEnvironmentPreset = computed(() => ENVIRONMENT_PRESETS[environmentPresetId.value])
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
let sceneGroup: THREE.Group | null = null
let materialCache: MaterialCache | null = null
let gridHelper: THREE.GridHelper | null = null
let environmentTarget: THREE.WebGLRenderTarget | null = null
let pmremGenerator: THREE.PMREMGenerator | null = null
let environmentScene: THREE.Scene | null = null
let environmentSky: Sky | null = null
let sky: Sky | null = null
let hemisphereLight: THREE.HemisphereLight | null = null
let directionalLight: THREE.DirectionalLight | null = null
let shadowGround: THREE.Mesh<THREE.PlaneGeometry, THREE.ShadowMaterial> | null = null
let presentationGround: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial> | null = null
let builtInEnvironment: THREE.Group | null = null
let composer: EffectComposer | null = null
let ssaoPass: SSAOPass | null = null
let bloomPass: UnrealBloomPass | null = null
let fxaaPass: ShaderPass | null = null
const sunDirection = new THREE.Vector3()
const lightingCenter = new THREE.Vector3()
const sceneBoundsCenter = new THREE.Vector3()
const sceneBoundsSize = new THREE.Vector3(8, 4, 8)
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
const instanceMatrix = new THREE.Matrix4()
const instanceWorldMatrix = new THREE.Matrix4()
let lightingExtent = 8
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

onMounted(() => {
  initThreeJS()
  startRenderLoop()
})

onUnmounted(() => {
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

function initThreeJS() {
  if (!canvasRef.value || !containerRef.value) return

  renderer = new THREE.WebGLRenderer({
    canvas: canvasRef.value,
    antialias: false,
    powerPreference: 'high-performance',
  })
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05
  configureMaterialRendering(renderer.capabilities.getMaxAnisotropy(), markNeedsRender)

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0xb9c9d8)

  const aspect = containerRef.value.clientWidth / containerRef.value.clientHeight
  camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 2000)
  camera.position.set(12, 10, 12)

  composer = new EffectComposer(renderer)
  composer.addPass(new RenderPass(scene, camera))
  ssaoPass = new SSAOPass(scene, camera, 1, 1)
  ssaoPass.kernelRadius = 10
  ssaoPass.minDistance = 0.002
  ssaoPass.maxDistance = 0.14
  composer.addPass(ssaoPass)
  bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.2, 0.35, 1.05)
  composer.addPass(bloomPass)
  composer.addPass(new OutputPass())
  fxaaPass = new ShaderPass(FXAAShader)
  composer.addPass(fxaaPass)

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

  pmremGenerator = new THREE.PMREMGenerator(renderer)
  pmremGenerator.compileCubemapShader()
  environmentScene = new THREE.Scene()
  environmentSky = new Sky()
  environmentSky.scale.setScalar(450)
  environmentScene.add(environmentSky)

  hemisphereLight = new THREE.HemisphereLight(0xddeeff, 0x665544, 0.75)
  scene.add(hemisphereLight)
  // 平行光
  directionalLight = new THREE.DirectionalLight(0xfff4df, 2.4)
  directionalLight.position.set(10, 20, 10)
  directionalLight.castShadow = true
  directionalLight.shadow.mapSize.width = 2048
  directionalLight.shadow.mapSize.height = 2048
  directionalLight.shadow.bias = -0.0002
  directionalLight.shadow.normalBias = 0.025
  directionalLight.shadow.radius = 2
  directionalLight.shadow.camera.left = -20
  directionalLight.shadow.camera.right = 20
  directionalLight.shadow.camera.top = 20
  directionalLight.shadow.camera.bottom = -20
  scene.add(directionalLight)
  scene.add(directionalLight.target)
  applyTimePreset()

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

  presentationGround = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshStandardMaterial({
      color: TIME_PRESETS.day.groundColor,
      roughness: 0.92,
      metalness: 0,
    }),
  )
  presentationGround.name = 'PresentationGround'
  presentationGround.rotation.x = -Math.PI / 2
  presentationGround.position.y = -0.004
  presentationGround.scale.set(200, 200, 1)
  // 地面本体负责受光，透明 ShadowMaterial 单独叠加可控的建筑投影，避免阴影重复变黑。
  presentationGround.receiveShadow = false
  presentationGround.visible = false
  scene.add(presentationGround)

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
  materialCache = new MaterialCache()
  // 创建名为 WildScene 的空分组容器，加入场景统一管理多个模型物体。
  sceneGroup = new THREE.Group()
  sceneGroup.name = 'WildScene'
  scene.add(sceneGroup)
  
  window.addEventListener('resize', handleResize)
  applyQualityPreset()
  applyViewMode()
  handleResize()
}

function handleResize() {
  if (!containerRef.value || !renderer || !camera) return
  const width = containerRef.value.clientWidth
  const height = containerRef.value.clientHeight
  camera.aspect = width / height
  camera.updateProjectionMatrix()
  renderer.setSize(width, height)
  composer?.setSize(width, height)
  if (fxaaPass) {
    const pixelRatio = renderer.getPixelRatio()
    fxaaPass.material.uniforms.resolution.value.set(
      1 / Math.max(width * pixelRatio, 1),
      1 / Math.max(height * pixelRatio, 1),
    )
  }
  markNeedsRender()
}

function startRenderLoop() {
  function animate() {
    animationFrameId = requestAnimationFrame(animate)
    if (controls) controls.update()
    if (needsRender && renderer && scene && camera) {
      if (composer) composer.render()
      else renderer.render(scene, camera)
      needsRender = false
    }
  }
  animate()
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
  environmentGroundY = 0
  sceneBoundsCenter.set(0, 0, 0)
  sceneBoundsSize.set(8, 4, 8)
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
    // 清空sceneGroup，但保留scene中的其他对象（灯光、GridHelper等）
    while (sceneGroup.children.length > 0) {
      const child = sceneGroup.children[0]
      sceneGroup.remove(child)
      if (child instanceof THREE.Mesh) child.geometry.dispose()
    }
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

  updateSceneGroup(sceneGroup, entity, materialCache)

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

    sceneBoundsCenter.copy(center)
    sceneBoundsSize.copy(size)
    hasSceneBounds = true
    environmentGroundY = bbox.min[1]

    updateLightingToBounds(center, maxDim)
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
    if (!event.shiftKey) selectionStore.clearSelection()
    return
  }

  const mapping = sceneStore.reconstructed?.componentMapping
  const selectableId = mapping ? resolveSelectableId(elementId, mapping) : elementId
  selectionStore.select(selectableId, event.shiftKey)
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
  if (viewMode.value === 'presentation' || !scene || !sceneGroup || !sceneStore.reconstructed) {
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
    ||
    !scene
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

function handleTransformObjectChange() {
  if (!dragAnchor || !dragStartPosition) return
  const delta = dragAnchor.position.clone().sub(dragStartPosition)
  for (const [object, start] of dragTargetPositions) object.position.copy(start).add(delta)
  syncSelectionHighlights()
  markNeedsRender()
}

function handleTransformDraggingChanged(event: { value?: unknown }) {
  if (controls) controls.enabled = event.value !== true
}

function handleTransformMouseUp() {
  if (!dragAnchor || !dragStartPosition || !dragComponentId || !sceneStore.document) return
  const delta = dragAnchor.position.clone().sub(dragStartPosition)
  if (delta.lengthSq() < 1e-10) return
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
  applyTimePreset()
}

function environmentColor(kind: 'groundColor' | 'fogColor') {
  const environmentColorValue = ENVIRONMENT_PRESETS[environmentPresetId.value][kind]
  const timeColorValue = TIME_PRESETS[timeOfDay.value][kind]
  const timeBlend = timeOfDay.value === 'night' ? 0.76 : timeOfDay.value === 'sunset' ? 0.42 : 0.08
  return new THREE.Color(environmentColorValue).lerp(new THREE.Color(timeColorValue), timeBlend)
}

function applyEnvironmentAppearance() {
  if (presentationGround) {
    presentationGround.material.color.copy(environmentColor('groundColor'))
    presentationGround.material.needsUpdate = true
  }
  if (scene?.fog instanceof THREE.Fog) {
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
  timeOfDay.value = TIME_ORDER[nextIndex]
  applyTimePreset()
}

function applyTimePreset() {
  if (!renderer || !scene || !sky || !hemisphereLight || !directionalLight) return
  const preset = TIME_PRESETS[timeOfDay.value]
  const environmentPreset = ENVIRONMENT_PRESETS[environmentPresetId.value]

  sunDirection.setFromSphericalCoords(
    1,
    THREE.MathUtils.degToRad(preset.sunPhi),
    THREE.MathUtils.degToRad(preset.sunTheta + environmentPreset.sunAzimuthOffset),
  )
  sky.visible = preset.skyVisible
  syncSkyPreset(sky, preset)

  scene.background = new THREE.Color(preset.background)
  rebuildEnvironment(preset)
  renderer.toneMappingExposure = preset.exposure * environmentPreset.exposureScale

  hemisphereLight.color.setHex(preset.hemisphereSkyColor)
  hemisphereLight.groundColor.setHex(preset.hemisphereGroundColor)
  hemisphereLight.intensity = preset.hemisphereIntensity * environmentPreset.ambientLightScale
  directionalLight.color.setHex(preset.directionalColor)
  directionalLight.intensity = preset.directionalIntensity * environmentPreset.directLightScale
  applyEnvironmentAppearance()
  if (bloomPass) {
    bloomPass.enabled = QUALITY_PRESETS[qualityLevel.value].bloom && timeOfDay.value === 'night'
  }
  if (shadowGround) {
    const timeShadowScale = timeOfDay.value === 'night' ? 0.36 : timeOfDay.value === 'sunset' ? 0.88 : 1
    shadowGround.material.opacity = environmentPreset.shadowOpacity * timeShadowScale
    shadowGround.material.needsUpdate = true
  }

  updateLightingToBounds(lightingCenter, Math.max(sceneBoundsSize.x, sceneBoundsSize.y, sceneBoundsSize.z))
  applyViewMode()
  markNeedsRender()
}

function syncSkyPreset(target: Sky, preset: TimePreset) {
  const uniforms = target.material.uniforms
  uniforms.turbidity.value = preset.turbidity
  uniforms.rayleigh.value = preset.rayleigh
  uniforms.mieCoefficient.value = preset.mieCoefficient
  uniforms.mieDirectionalG.value = preset.mieDirectionalG
  uniforms.sunPosition.value.copy(sunDirection)
}

function rebuildEnvironment(preset: TimePreset) {
  if (!scene || !pmremGenerator || !environmentScene || !environmentSky) return
  syncSkyPreset(environmentSky, preset)
  environmentScene.background = new THREE.Color(preset.background)
  const nextTarget = pmremGenerator.fromScene(
    environmentScene,
    timeOfDay.value === 'night' ? 0.16 : 0.045,
    0.1,
    1000,
  )
  const previousTarget = environmentTarget
  environmentTarget = nextTarget
  scene.environment = nextTarget.texture
  previousTarget?.dispose()
}

function toggleViewMode() {
  viewMode.value = viewMode.value === 'editor' ? 'presentation' : 'editor'
  applyViewMode()
}

function applyViewMode() {
  if (!scene) return
  const presenting = viewMode.value === 'presentation'
  const scenic = environmentPresetId.value !== 'minimal'
  if (gridHelper) gridHelper.visible = !presenting
  if (shadowGround) shadowGround.visible = true
  if (presentationGround) presentationGround.visible = presenting || scenic
  if (builtInEnvironment) builtInEnvironment.visible = scenic
  if (transformControls) transformControls.visible = !presenting
  if (presenting) {
    clearSelectionHelpers()
    clearComponentTransformControl()
  } else {
    syncSelectionHighlights()
    syncComponentTransformControl()
  }
  if (presenting) {
    const fogNear = Math.max(60, lightingExtent * 5)
    scene.fog = new THREE.Fog(
      environmentColor('fogColor'),
      fogNear,
      fogNear + Math.max(180, lightingExtent * 16),
    )
  } else {
    scene.fog = null
  }
  markNeedsRender()
}

function cycleQuality() {
  const nextIndex = (QUALITY_ORDER.indexOf(qualityLevel.value) + 1) % QUALITY_ORDER.length
  qualityLevel.value = QUALITY_ORDER[nextIndex]
  applyQualityPreset()
}

function applyQualityPreset() {
  if (!renderer) return
  const preset = QUALITY_PRESETS[qualityLevel.value]
  const pixelRatio = Math.min(window.devicePixelRatio || 1, preset.pixelRatio)
  renderer.setPixelRatio(pixelRatio)
  composer?.setPixelRatio(pixelRatio)
  if (directionalLight) {
    const shadowSize = Math.min(preset.shadowMapSize, renderer.capabilities.maxTextureSize)
    if (directionalLight.shadow.mapSize.width !== shadowSize) {
      directionalLight.shadow.map?.dispose()
      directionalLight.shadow.map = null
      directionalLight.shadow.mapSize.set(shadowSize, shadowSize)
    }
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

function updateLightingToBounds(center: THREE.Vector3, maxDim: number) {
  if (!directionalLight) return
  lightingCenter.copy(center)
  // 阴影相机只覆盖模型附近，提升同一张 2048 阴影图的有效像素密度。
  lightingExtent = Math.max(maxDim * 0.68, 4)
  const lightDistance = lightingExtent * 2.5

  directionalLight.position.copy(center).addScaledVector(sunDirection, lightDistance)
  directionalLight.target.position.copy(center)
  directionalLight.target.updateMatrixWorld()
  const shadowCamera = directionalLight.shadow.camera
  shadowCamera.left = -lightingExtent
  shadowCamera.right = lightingExtent
  shadowCamera.top = lightingExtent
  shadowCamera.bottom = -lightingExtent
  shadowCamera.near = 0.1
  shadowCamera.far = lightDistance + lightingExtent * 2
  shadowCamera.updateProjectionMatrix()
  directionalLight.shadow.normalBias = Math.max(0.008, lightingExtent * 0.0015)
  directionalLight.shadow.needsUpdate = true
  if (scene?.fog instanceof THREE.Fog) {
    const fogNear = Math.max(60, lightingExtent * 5)
    scene.fog.near = fogNear
    scene.fog.far = fogNear + Math.max(180, lightingExtent * 16)
  }
}

function frameCameraToBounds(center: THREE.Vector3, size: THREE.Vector3) {
  if (!camera || !controls) return
  const verticalFov = THREE.MathUtils.degToRad(camera.fov)
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect)
  const verticalDistance = size.y / Math.max(2 * Math.tan(verticalFov / 2), 0.01)
  const horizontalDistance = Math.max(size.x, size.z) / Math.max(2 * Math.tan(horizontalFov / 2), 0.01)
  const distance = Math.max(verticalDistance, horizontalDistance, 2) * 1.55
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
}

function cleanup() {
  if (animationFrameId !== null) cancelAnimationFrame(animationFrameId)
  window.removeEventListener('resize', handleResize)
  renderer?.domElement.removeEventListener('pointerdown', handlePointerDown)
  renderer?.domElement.removeEventListener('pointerup', handlePointerUp)
  renderer?.domElement.removeEventListener('contextmenu', handleContextMenu)
  clearSelectionHelpers()
  clearComponentTransformControl()
  if (materialCache) materialCache.clear()
  if (controls) controls.removeEventListener('change', markNeedsRender)
  environmentTarget?.dispose()
  pmremGenerator?.dispose()
  sky?.geometry.dispose()
  sky?.material.dispose()
  environmentSky?.geometry.dispose()
  environmentSky?.material.dispose()
  clearBuiltInEnvironment()
  shadowGround?.geometry.dispose()
  shadowGround?.material.dispose()
  presentationGround?.geometry.dispose()
  presentationGround?.material.dispose()
  ssaoPass?.dispose()
  bloomPass?.dispose()
  fxaaPass?.material.dispose()
  composer?.dispose()
  configureMaterialRendering(1)
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
