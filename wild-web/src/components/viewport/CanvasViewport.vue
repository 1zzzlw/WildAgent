<template>
  <div class="canvas-viewport" ref="containerRef">
    <canvas ref="canvasRef"></canvas>
    <div class="viewport-overlay">
      <div class="stats">
        <div v-if="sceneStore.document">
          元素: {{ sceneStore.document.blueprint.geometry.elements?.length || 0 }}
        </div>
        <div v-if="sceneStore.reconstructed">
          网格: {{ sceneStore.reconstructed.meshes.length }}
        </div>
        <div v-if="sceneStore.isReconstructing">
          重建中...
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { MaterialCache } from '../../renderer/materialAdapter'
import { updateSceneGroup } from '../../renderer/renderEntity'

const containerRef = ref<HTMLDivElement>()
const canvasRef = ref<HTMLCanvasElement>()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let animationFrameId: number | null = null
let sceneGroup: THREE.Group | null = null
let materialCache: MaterialCache | null = null

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

function initThreeJS() {
  if (!canvasRef.value || !containerRef.value) return

  renderer = new THREE.WebGLRenderer({ canvas: canvasRef.value, antialias: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x1a1a1a)

  const aspect = containerRef.value.clientWidth / containerRef.value.clientHeight
  camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 1000)
  camera.position.set(12, 10, 12)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0, 1.5, 0)
  controls.update()

  const ambientLight = new THREE.AmbientLight(0xffffff, 0.4)
  scene.add(ambientLight)

  const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
  directionalLight.position.set(10, 20, 10)
  directionalLight.castShadow = true
  directionalLight.shadow.mapSize.width = 2048
  directionalLight.shadow.mapSize.height = 2048
  directionalLight.shadow.camera.left = -20
  directionalLight.shadow.camera.right = 20
  directionalLight.shadow.camera.top = 20
  directionalLight.shadow.camera.bottom = -20
  scene.add(directionalLight)

  const gridHelper = new THREE.GridHelper(20, 20, 0x444444, 0x333333)
  scene.add(gridHelper)

  materialCache = new MaterialCache()

  sceneGroup = new THREE.Group()
  sceneGroup.name = 'WildScene'
  scene.add(sceneGroup)

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
}

function startRenderLoop() {
  function animate() {
    animationFrameId = requestAnimationFrame(animate)
    if (controls) controls.update()
    if (renderer && scene && camera) renderer.render(scene, camera)
  }
  animate()
}

function updateScene() {
  if (!scene || !sceneGroup || !materialCache) return

  const entity = sceneStore.reconstructed
  if (!entity) {
    while (sceneGroup.children.length > 0) {
      const child = sceneGroup.children[0]
      sceneGroup.remove(child)
      if (child instanceof THREE.Mesh) child.geometry.dispose()
    }
    return
  }

  updateSceneGroup(sceneGroup, entity, materialCache)

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

    if (controls && camera) {
      controls.target.copy(center)
      camera.position.set(
        center.x + distance,
        center.y + distance * 0.7,
        center.z + distance
      )
      controls.update()
    }
  }
}

function cleanup() {
  if (animationFrameId !== null) cancelAnimationFrame(animationFrameId)
  window.removeEventListener('resize', handleResize)
  if (materialCache) materialCache.clear()
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

.stats > div {
  margin: 2px 0;
}
</style>
