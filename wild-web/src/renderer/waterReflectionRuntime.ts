import * as THREE from 'three'
import { Reflector } from 'three/examples/jsm/objects/Reflector.js'
import { getWaterReflectionUniforms } from './waterSurfaceMaterial'

/** 一次捕获主水位的真实场景反射；PBR 仍负责透射/吸收，其他水位保留 IBL。 */
export class WaterReflectionRuntime {
  private reflector: Reflector | null = null
  private surfaces: THREE.Mesh[] = []
  private materials = new Set<THREE.Material>()
  private worldBox = new THREE.Box3()
  private instanceWorld = new THREE.Matrix4()
  private inverse = new THREE.Matrix4()
  private reflectionMatrix = new THREE.Matrix4()
  private frameSize = new THREE.Vector2()
  private projection = new THREE.Matrix4()
  private frustum = new THREE.Frustum()
  private cameraMatrix = new THREE.Matrix4()
  private cameraProjection = new THREE.Matrix4()
  private up = new THREE.Vector3()
  private cameraPosition = new THREE.Vector3()
  private dirty = true
  private lastCapture = -Infinity
  private capturedHeight = NaN
  captureCount = 0
  enabled = false
  active = false
  private renderer: THREE.WebGLRenderer
  private scene: THREE.Scene

  constructor(renderer: THREE.WebGLRenderer, scene: THREE.Scene) { this.renderer = renderer; this.scene = scene }

  setRoot(root: THREE.Object3D | null): void {
    this.invalidate()
    this.lastCapture = -Infinity
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

  invalidate(): void { this.dirty = true }

  hasVisibleSurface(camera: THREE.Camera): boolean { return this.getVisibleWaterLevel(camera) !== null }

  getVisibleWaterLevel(camera: THREE.Camera): number | null {
    if (!this.surfaces.length) return null
    camera.updateMatrixWorld()
    this.projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
    this.frustum.setFromProjectionMatrix(this.projection)
    let largestArea = 0, height = 0
    for (const mesh of this.surfaces) {
      let visible = true
      for (let object: THREE.Object3D | null = mesh; object; object = object.parent) if (!object.visible) { visible = false; break }
      if (!visible) continue
      mesh.updateWorldMatrix(true, false)
      if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox()
      const count = mesh instanceof THREE.InstancedMesh ? mesh.count : 1
      for (let index = 0; index < count; index++) {
        let matrix = mesh.matrixWorld
        if (mesh instanceof THREE.InstancedMesh) {
          mesh.getMatrixAt(index, this.instanceWorld)
          matrix = this.instanceWorld.premultiply(mesh.matrixWorld)
        }
        if (this.up.set(0, 1, 0).transformDirection(matrix).y < 0.999) continue
        this.worldBox.copy(mesh.geometry.boundingBox!).applyMatrix4(matrix)
        if (!this.frustum.intersectsBox(this.worldBox)) continue
        const area = (this.worldBox.max.x - this.worldBox.min.x) * (this.worldBox.max.z - this.worldBox.min.z)
        if (area > largestArea) { largestArea = area; height = this.worldBox.max.y }
      }
    }
    return largestArea ? height : null
  }

  update(camera: THREE.Camera, force = false, visibleLevel?: number | null): void {
    this.active = false
    for (const material of this.materials) getWaterReflectionUniforms(material).strength.value = 0
    if (!this.enabled || !this.surfaces.length) return
    const height = visibleLevel === undefined ? this.getVisibleWaterLevel(camera) : visibleLevel
    if (height === null || this.cameraPosition.setFromMatrixPosition(camera.matrixWorld).y <= height) return
    this.renderer.getDrawingBufferSize(this.frameSize)
    const scale = Math.min(0.5, 1024 / Math.max(this.frameSize.x, this.frameSize.y))
    const width = Math.max(1, Math.round(this.frameSize.x * scale)), heightPx = Math.max(1, Math.round(this.frameSize.y * scale))
    if (!this.reflector) this.reflector = new Reflector(new THREE.PlaneGeometry(1, 1), { textureWidth: width, textureHeight: heightPx, clipBias: 0.003, multisample: 0 })
    const reflector = this.reflector
    const target = reflector.getRenderTarget()
    const sizeChanged = target.width !== width || target.height !== heightPx
    if (sizeChanged) target.setSize(width, heightPx)
    const changed = this.dirty || height !== this.capturedHeight || !this.cameraMatrix.equals(camera.matrixWorld)
      || !this.cameraProjection.equals(camera.projectionMatrix)
    // 水纹只改变采样法线。静止视图复用捕获；变化时最多每秒捕获 30 次。
    // 调整尺寸会清空纹理，必须在本帧重新填充。
    if (force || sizeChanged || (changed && performance.now() - this.lastCapture >= 1000 / 30)) {
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
      this.reflectionMatrix.copy(matrix).multiply(this.inverse.copy(reflector.matrixWorld).invert())
      this.cameraMatrix.copy(camera.matrixWorld)
      this.cameraProjection.copy(camera.projectionMatrix)
      this.capturedHeight = height
      this.lastCapture = performance.now()
      this.dirty = false
      this.captureCount++
    }
    for (const material of this.materials) {
      const uniforms = getWaterReflectionUniforms(material)
      uniforms.map.value = target.texture
      uniforms.matrix.value.copy(this.reflectionMatrix)
      // 限帧期间继续使用本次捕获对应的水位，其他水位由材质回退到环境反射。
      uniforms.height.value = this.capturedHeight
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
    this.captureCount = 0
    this.capturedHeight = NaN
  }

  dispose(): void { this.setRoot(null); this.releaseTarget() }
}
