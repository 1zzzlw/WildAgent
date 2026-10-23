import * as THREE from 'three'
import { Reflector } from 'three/examples/jsm/objects/Reflector.js'
import { getWaterReflectionUniforms } from './waterSurfaceMaterial'

/** 一次捕获主水位的真实场景反射；PBR 仍负责透射/吸收，其他水位保留 IBL。 */
export class WaterReflectionRuntime {
  private reflector: Reflector | null = null
  private surfaces: THREE.Mesh[] = []
  private materials = new Set<THREE.Material>()
  private worldBox = new THREE.Box3()
  private inverse = new THREE.Matrix4()
  private frameSize = new THREE.Vector2()
  enabled = false
  active = false
  private renderer: THREE.WebGLRenderer
  private scene: THREE.Scene

  constructor(renderer: THREE.WebGLRenderer, scene: THREE.Scene) { this.renderer = renderer; this.scene = scene }

  setRoot(root: THREE.Object3D | null): void {
    for (const material of this.materials) {
      const uniforms = getWaterReflectionUniforms(material)
      uniforms.strength.value = 0
      uniforms.map.value = null
    }
    this.materials.clear()
    this.surfaces = []
    root?.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return
      const materials = Array.isArray(object.material) ? object.material : [object.material]
      if (materials.some(material => material.userData.wildWaterSurface)) {
        this.surfaces.push(object)
        materials.filter(material => material.userData.wildWaterSurface).forEach(material => this.materials.add(material))
      }
    })
    if (!this.surfaces.length) this.releaseTarget()
  }

  update(camera: THREE.Camera): void {
    this.active = false
    for (const material of this.materials) getWaterReflectionUniforms(material).strength.value = 0
    if (!this.enabled || !this.surfaces.length) return
    this.scene.updateMatrixWorld(true)
    let largestArea = 0, height = 0
    for (const mesh of this.surfaces) {
      if (!mesh.visible || !mesh.parent?.visible) continue
      const up = new THREE.Vector3(0, 1, 0).transformDirection(mesh.matrixWorld)
      if (up.y < 0.999) continue
      this.worldBox.setFromObject(mesh)
      const area = (this.worldBox.max.x - this.worldBox.min.x) * (this.worldBox.max.z - this.worldBox.min.z)
      if (area > largestArea) { largestArea = area; height = this.worldBox.max.y }
    }
    if (!largestArea || camera.getWorldPosition(new THREE.Vector3()).y <= height) return
    this.renderer.getDrawingBufferSize(this.frameSize)
    const scale = Math.min(0.5, 1024 / Math.max(this.frameSize.x, this.frameSize.y))
    const width = Math.max(1, Math.round(this.frameSize.x * scale)), heightPx = Math.max(1, Math.round(this.frameSize.y * scale))
    if (!this.reflector) this.reflector = new Reflector(new THREE.PlaneGeometry(1, 1), { textureWidth: width, textureHeight: heightPx, clipBias: 0.003, multisample: 0 })
    const reflector = this.reflector
    if (reflector.getRenderTarget().width !== width || reflector.getRenderTarget().height !== heightPx) reflector.getRenderTarget().setSize(width, heightPx)
    reflector.position.set(0, height, 0)
    reflector.rotation.x = -Math.PI / 2
    reflector.updateMatrixWorld(true)
    // 捕获时排除所有水面，避免递归/采样正在写入的纹理，也排除编辑辅助物。
    const hidden: Array<[THREE.Object3D, boolean]> = [...this.surfaces, ...this.scene.children.filter(object => object instanceof THREE.Line || object.type === 'TransformControls' || object.name === 'SelectionEdges')]
      .map(object => [object, object.visible])
    try {
      hidden.forEach(([object]) => { object.visible = false })
      reflector.onBeforeRender(this.renderer, this.scene, camera, reflector.geometry, reflector.material as THREE.ShaderMaterial, null as unknown as THREE.Group)
    } finally {
      hidden.forEach(([object, visible]) => { object.visible = visible })
    }
    const matrix = (reflector.material as THREE.ShaderMaterial).uniforms.textureMatrix!.value as THREE.Matrix4
    this.inverse.copy(reflector.matrixWorld).invert()
    for (const material of this.materials) {
      const uniforms = getWaterReflectionUniforms(material)
      uniforms.map.value = reflector.getRenderTarget().texture
      uniforms.matrix.value.copy(matrix).multiply(this.inverse)
      uniforms.height.value = height
      uniforms.texel.value.set(1 / width, 1 / heightPx)
      uniforms.strength.value = 0.85
    }
    this.active = true
  }

  private releaseTarget(): void {
    if (!this.reflector) return
    for (const material of this.materials) getWaterReflectionUniforms(material).map.value = null
    this.reflector.geometry.dispose()
    this.reflector.dispose()
    this.reflector = null
  }

  dispose(): void { this.setRoot(null); this.releaseTarget() }
}
