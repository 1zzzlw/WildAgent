import * as THREE from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { reconstructWildEntity } from './wildCoreAdapter'
import { SURFACE_MATERIAL_PRESETS } from '../wild/surfaceMaterialPresets'
import { clearSceneObjectResources, createSceneGroupFromEntity } from './renderEntity'

let thumbnails: Promise<Record<string, string>> | undefined

/** 用正式 Core/材质管线生成一次缩略图，完成即释放 GPU 资源。 */
export function getMaterialThumbnails(): Promise<Record<string, string>> {
  return thumbnails ??= renderThumbnails()
}

async function renderThumbnails(): Promise<Record<string, string>> {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, alpha: true })
  renderer.setSize(192, 128)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  const pmrem = new THREE.PMREMGenerator(renderer), room = new RoomEnvironment()
  const environment = pmrem.fromScene(room, 0.04)
  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#303944')
  scene.environment = environment.texture
  const camera = new THREE.PerspectiveCamera(36, 1.5, 0.01, 10)
  camera.position.set(0.65, 0.45, 1.15); camera.lookAt(0, 0, 0)
  const light = new THREE.DirectionalLight(0xffffff, 3)
  light.position.set(-1, 2, 3); scene.add(light)
  const result: Record<string, string> = {}
  try {
    for (const preset of SURFACE_MATERIAL_PRESETS) {
      const rounded = ['metal', 'glass'].includes(preset.material.surfaceFamily ?? '') || preset.material.materialClass === 'fabric'
      const entity = await reconstructWildEntity({ meta: { version: '1.1', type: 'asset', name: preset.name },
        geometry: { elements: [{ type: 'primitive', id: 'sample', shape: rounded ? 'sphere' : 'box', radius: 0.32, dimensions: [0.65, 0.65, 0.08], material: preset.id }] },
        materials: { [preset.id]: preset.material } })
      const group = createSceneGroupFromEntity(entity)
      scene.add(group); renderer.render(scene, camera)
      result[preset.id] = renderer.domElement.toDataURL('image/png')
      scene.remove(group); clearSceneObjectResources(group)
      await new Promise(resolve => setTimeout(resolve, 0))
    }
    return result
  } finally {
    environment.dispose(); room.dispose(); pmrem.dispose(); renderer.dispose(); renderer.forceContextLoss()
  }
}
