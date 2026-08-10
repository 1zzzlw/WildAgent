<template>
  <div class="canvas-viewport" ref="containerRef">
    <!-- 展示3D视图的区域 -->
    <canvas ref="canvasRef"></canvas>
    <div class="viewport-overlay">
      <div class="stats">
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
import { useUIStore } from '../../stores/uiStore'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { Sky } from 'three/examples/jsm/objects/Sky.js'
import { configureMaterialRendering, MaterialCache } from '../../renderer/materialAdapter'
import { toggleRuntimeInteraction, updateSceneGroup } from '../../renderer/renderEntity'
import { createTestScene, clearTestScene } from '../../utils/simpleSceneTest'
import { getRenderedElementIds, resolveSelectableId } from '../../wild/componentSelection'
import { createComponentTranslationChanges } from '../../wild/componentDrag'
import { createPatch } from '../../wild/scenePatch'

const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const uiStore = useUIStore()

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
let transformControls: TransformControls | null = null
let animationFrameId: number | null = null
let sceneGroup: THREE.Group | null = null
let materialCache: MaterialCache | null = null
let gridHelper: THREE.GridHelper | null = null
let environmentTarget: THREE.WebGLRenderTarget | null = null
let sky: Sky | null = null
let hemisphereLight: THREE.HemisphereLight | null = null
let directionalLight: THREE.DirectionalLight | null = null
let shadowGround: THREE.Mesh<THREE.PlaneGeometry, THREE.ShadowMaterial> | null = null
const sunDirection = new THREE.Vector3()
const lightingCenter = new THREE.Vector3()
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
const instanceMatrix = new THREE.Matrix4()
const instanceWorldMatrix = new THREE.Matrix4()
let lightingExtent = 8
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
    antialias: true,
    logarithmicDepthBuffer: true,
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05
  configureMaterialRendering(renderer.capabilities.getMaxAnisotropy())

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
    new THREE.ShadowMaterial({ color: 0x26352d, opacity: 0.2 }),
  )
  shadowGround.name = 'ShadowGround'
  shadowGround.rotation.x = -Math.PI / 2
  shadowGround.position.y = -0.002
  shadowGround.receiveShadow = true
  scene.add(shadowGround)
  
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

    updateLightingToBounds(center, maxDim)
    if (shadowGround) shadowGround.position.y = bbox.min[1] - 0.002
    if (gridHelper) gridHelper.position.y = bbox.min[1]

    if (!hasFramedScene && controls && camera) {
      frameCameraToBounds(center, size)
      hasFramedScene = true
    }
  }
  
  ensureGridVisible()
  syncSelectionHighlights()
  syncComponentTransformControl()
  markNeedsRender()
}

function handlePointerDown(event: PointerEvent) {
  // 选择只响应主按键。右键由 contextmenu 独占，不能先改变选中高亮。
  if (event.button !== 0) {
    pointerDownPosition = null
    return
  }
  pointerDownPosition = { x: event.clientX, y: event.clientY }
}

function handlePointerUp(event: PointerEvent) {
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
  if (!scene || !sceneGroup || !sceneStore.reconstructed) {
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
  if (shadowGround) {
    shadowGround.material.opacity = timeOfDay.value === 'night' ? 0.1 : timeOfDay.value === 'sunset' ? 0.24 : 0.2
    shadowGround.material.needsUpdate = true
  }

  updateLightingToBounds(lightingCenter, lightingExtent)
  markNeedsRender()
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
}

function frameCameraToBounds(center: THREE.Vector3, size: THREE.Vector3) {
  if (!camera || !controls) return
  const verticalFov = THREE.MathUtils.degToRad(camera.fov)
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect)
  const verticalDistance = size.y / Math.max(2 * Math.tan(verticalFov / 2), 0.01)
  const horizontalDistance = Math.max(size.x, size.z) / Math.max(2 * Math.tan(horizontalFov / 2), 0.01)
  const distance = Math.max(verticalDistance, horizontalDistance, 2) * 1.55
  const viewDirection = new THREE.Vector3(1, 0.72, 1).normalize()
  controls.target.copy(center)
  controls.minDistance = Math.max(0.2, distance * 0.08)
  controls.maxDistance = Math.max(50, distance * 8)
  camera.position.copy(center).addScaledVector(viewDirection, distance)
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
  shadowGround?.geometry.dispose()
  shadowGround?.material.dispose()
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
