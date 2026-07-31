<template>
  <div class="canvas-viewport" ref="containerRef">
    <!-- 展示3D视图的区域 -->
    <canvas ref="canvasRef"></canvas>
    <div class="viewport-overlay">
      <div class="stats">
        <div v-if="sceneStore.document">
          元素: {{ sceneStore.document.blueprint.geometry.elements?.length || 0 }}
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
      <button
        type="button"
        class="time-toggle"
        :title="`切换到${nextTimePreset.label}`"
        :aria-label="`当前${activeTimePreset.label}，切换到${nextTimePreset.label}`"
        @click="cycleTimeOfDay"
      >
        <span aria-hidden="true">{{ activeTimePreset.icon }}</span>
        <span>{{ activeTimePreset.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { Sky } from 'three/examples/jsm/objects/Sky.js'
import { MaterialCache } from '../../renderer/materialAdapter'
import { updateSceneGroup } from '../../renderer/renderEntity'
import { createTestScene, clearTestScene } from '../../utils/simpleSceneTest'

const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()

type TimeOfDay = 'day' | 'sunset' | 'night'

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
  useEnvironment: boolean
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
    useEnvironment: true,
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
    useEnvironment: true,
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
    sunPhi: 55,
    sunTheta: 220,
    directionalColor: 0x9dbbff,
    directionalIntensity: 0.32,
    hemisphereSkyColor: 0x182442,
    hemisphereGroundColor: 0x08070d,
    hemisphereIntensity: 0.2,
    useEnvironment: false,
  },
}

const timeOfDay = ref<TimeOfDay>('day')
const activeTimePreset = computed(() => TIME_PRESETS[timeOfDay.value])
const nextTimePreset = computed(() => {
  const nextIndex = (TIME_ORDER.indexOf(timeOfDay.value) + 1) % TIME_ORDER.length
  return TIME_PRESETS[TIME_ORDER[nextIndex]]
})

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let animationFrameId: number | null = null
let sceneGroup: THREE.Group | null = null
let materialCache: MaterialCache | null = null
let gridHelper: THREE.GridHelper | null = null
let environmentTarget: THREE.WebGLRenderTarget | null = null
let sky: Sky | null = null
let hemisphereLight: THREE.HemisphereLight | null = null
let directionalLight: THREE.DirectionalLight | null = null
const sunDirection = new THREE.Vector3()
const lightingCenter = new THREE.Vector3()
let lightingExtent = 8
let hasFramedScene = false
let needsRender = true

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

function initThreeJS() {
  if (!canvasRef.value || !containerRef.value) return

  renderer = new THREE.WebGLRenderer({
    canvas: canvasRef.value,
    antialias: true,
    logarithmicDepthBuffer: true,
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0xb9c9d8)

  const aspect = containerRef.value.clientWidth / containerRef.value.clientHeight
  camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 2000)
  camera.position.set(12, 10, 12)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0, 1.5, 0)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.addEventListener('change', markNeedsRender)
  controls.update()

  // 测试：检查GridHelper是否正确添加
  console.log('Scene children after init:', scene.children.map(c => ({ type: c.type, name: c.name })));

  // 暴露到window用于调试
  (window as any).debugScene = {
    scene,
    camera,
    renderer,
    controls,
    testScene: () => createTestScene(scene),
    clearTest: () => clearTestScene(scene)
  };
  console.log('💡 调试工具已挂载到 window.debugScene');
  console.log('  - debugScene.testScene() : 创建测试场景');
  console.log('  - debugScene.clearTest() : 清除测试场景');

  const pmremGenerator = new THREE.PMREMGenerator(renderer)
  environmentTarget = pmremGenerator.fromScene(new RoomEnvironment(renderer), 0.04)
  scene.environment = environmentTarget.texture
  pmremGenerator.dispose()

  sky = new Sky()
  sky.scale.setScalar(450)
  scene.add(sky)

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
  directionalLight.shadow.camera.left = -20
  directionalLight.shadow.camera.right = 20
  directionalLight.shadow.camera.top = 20
  directionalLight.shadow.camera.bottom = -20
  scene.add(directionalLight)
  scene.add(directionalLight.target)
  applyTimePreset()

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(400, 400),
    new THREE.ShadowMaterial({ color: 0x26352d, opacity: 0.2 }),
  )
  ground.name = 'ShadowGround'
  ground.rotation.x = -Math.PI / 2
  ground.position.y = -0.002
  ground.receiveShadow = true
  scene.add(ground)
  
  // 创建GridHelper并保持引用，确保不会被误删除
  // 添加到场景根层级，不是sceneGroup
  gridHelper = new THREE.GridHelper(20, 20, 0x444444, 0x333333)
  gridHelper.name = 'GridHelper'
  gridHelper.position.y = 0  // 确保在地面
  scene.add(gridHelper)
  console.log('GridHelper added to scene at root level');

  materialCache = new MaterialCache()
  // 创建名为 WildScene 的空分组容器，加入场景统一管理多个模型物体。
  sceneGroup = new THREE.Group()
  sceneGroup.name = 'WildScene'
  scene.add(sceneGroup)
  
  console.log('Scene structure:', {
    children: scene.children.length,
    hasGrid: scene.children.some(c => c.name === 'GridHelper'),
    hasWildScene: scene.children.some(c => c.name === 'WildScene')
  });

  window.addEventListener('resize', handleResize)
  handleResize()
}

function handleResize() {
  if (!containerRef.value || !renderer || !camera) return
  const width = containerRef.value.clientWidth
  const height = containerRef.value.clientHeight
  camera.aspect = width / height
  camera.updateProjectionMatrix()
  renderer.setSize(width, height)
  markNeedsRender()
}

function startRenderLoop() {
  function animate() {
    animationFrameId = requestAnimationFrame(animate)
    if (controls) controls.update()
    if (needsRender && renderer && scene && camera) {
      renderer.render(scene, camera)
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
	  gridHelper.visible = true
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
    console.log('Scene cleared, GridHelper should remain visible');
    
    // 重置相机到初始位置，确保GridHelper可见
    if (controls && camera) {
      controls.target.set(0, 0, 0)
      camera.position.set(12, 10, 12)
      controls.update()
    }
    hasFramedScene = false
    ensureGridVisible()
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
    ensureGridVisible()
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
    const distance = maxDim * 1.5

    updateLightingToBounds(center, maxDim)

    if (!hasFramedScene && controls && camera) {
      controls.target.copy(center)
      camera.position.set(
        center.x + distance,
        center.y + distance * 0.7,
        center.z + distance
      )
      controls.update()
      hasFramedScene = true
    }
  }
  
  ensureGridVisible()
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
  const skyUniforms = sky.material.uniforms

  sunDirection.setFromSphericalCoords(
    1,
    THREE.MathUtils.degToRad(preset.sunPhi),
    THREE.MathUtils.degToRad(preset.sunTheta),
  )
  sky.visible = preset.skyVisible
  skyUniforms.turbidity.value = preset.turbidity
  skyUniforms.rayleigh.value = preset.rayleigh
  skyUniforms.mieCoefficient.value = preset.mieCoefficient
  skyUniforms.mieDirectionalG.value = preset.mieDirectionalG
  skyUniforms.sunPosition.value.copy(sunDirection)

  scene.background = new THREE.Color(preset.background)
  scene.environment = preset.useEnvironment && environmentTarget
    ? environmentTarget.texture
    : null
  renderer.toneMappingExposure = preset.exposure

  hemisphereLight.color.setHex(preset.hemisphereSkyColor)
  hemisphereLight.groundColor.setHex(preset.hemisphereGroundColor)
  hemisphereLight.intensity = preset.hemisphereIntensity
  directionalLight.color.setHex(preset.directionalColor)
  directionalLight.intensity = preset.directionalIntensity

  updateLightingToBounds(lightingCenter, lightingExtent)
  markNeedsRender()
}

function updateLightingToBounds(center: THREE.Vector3, maxDim: number) {
  if (!directionalLight) return
  lightingCenter.copy(center)
  lightingExtent = Math.max(maxDim, 8)
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
}

function markNeedsRender() {
  needsRender = true
}

function cleanup() {
  if (animationFrameId !== null) cancelAnimationFrame(animationFrameId)
  window.removeEventListener('resize', handleResize)
  if (materialCache) materialCache.clear()
  if (controls) controls.removeEventListener('change', markNeedsRender)
  environmentTarget?.dispose()
  if (renderer) renderer.dispose()
  if (controls) controls.dispose()
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

.time-toggle {
  position: absolute;
  top: 12px;
  right: 12px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 92px;
  padding: 8px 12px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(18, 23, 33, 0.78);
  color: #f4f7fb;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  pointer-events: auto;
  backdrop-filter: blur(8px);
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}

.time-toggle:hover {
  background: rgba(28, 36, 50, 0.92);
  border-color: rgba(255, 255, 255, 0.36);
}

.time-toggle:active {
  transform: translateY(1px);
}

.time-toggle:focus-visible {
  outline: 2px solid #8fc7ff;
  outline-offset: 2px;
}

.diagnostics {
  color: #ffd27a;
}
</style>
