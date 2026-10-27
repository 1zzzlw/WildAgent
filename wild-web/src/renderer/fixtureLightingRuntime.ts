import * as THREE from 'three'
import type { QualityLevel } from './defaultWorldLook'

type Fixture = THREE.PointLight | THREE.SpotLight
const BUDGET = { low: 2, medium: 4, high: 8 }
const SHADOW_SIZE = { low: 256, medium: 512, high: 1024 }

/** 每个活跃实时灯都参与遮挡；通过灯数和分辨率控制成本，不能用穿墙光补亮。 */
export class FixtureLightingRuntime {
  private fixtures: Fixture[] = []
  private selected = new Set<Fixture>()
  private position = new THREE.Vector3()
  private cameraPosition = new THREE.Vector3()
  private viewPosition = new THREE.Vector3()
  private projection = new THREE.Matrix4()
  private frustum = new THREE.Frustum()
  private influence = new THREE.Sphere()
  private shadowTransforms = new WeakMap<Fixture, string>()
  activeCount = 0
  shadowCount = 0

  setRoot(root: THREE.Object3D | null): void {
    const previous = this.fixtures
    this.fixtures = []
    root?.traverse(object => {
      if ((object instanceof THREE.PointLight || object instanceof THREE.SpotLight) && object.userData.fixtureLight) this.fixtures.push(object)
    })
    const retained = new Set(this.fixtures)
    for (const light of previous) if (!retained.has(light)) {
      light.visible = true
      light.castShadow = false
      light.shadow.dispose()
      light.shadow.map = null
      light.shadow.mapPass = null
      this.selected.delete(light)
    }
    // 增量更新保留同一灯的贴图；几何可能改变，内容仍须失效。
    this.invalidateShadows()
  }

  invalidateShadows(): void {
    for (const light of this.fixtures) light.shadow.needsUpdate = true
  }

  update(camera: THREE.Camera, quality: QualityLevel): boolean {
    camera.updateMatrixWorld()
    this.cameraPosition.setFromMatrixPosition(camera.matrixWorld)
    this.projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
    this.frustum.setFromProjectionMatrix(this.projection)
    const candidates = this.fixtures.filter(light => {
      if ((light.userData.requestedIntensity ?? light.intensity) <= 0) return false
      for (let parent = light.parent; parent; parent = parent.parent) if (!parent.visible) return false
      light.getWorldPosition(this.position)
      this.influence.set(this.position, light.distance)
      // 按光照范围剔除，不能只看灯泡是否在画面内。
      if (light.distance > 0 && !this.frustum.intersectsSphere(this.influence)) return false
      return true
    })
      .map(light => {
        light.getWorldPosition(this.position)
        const distance = this.position.distanceTo(this.cameraPosition)
        const inFront = this.viewPosition.copy(this.position).applyMatrix4(camera.matrixWorldInverse).z < 0
        const score = (inFront ? 1 : 0.25) * (this.selected.has(light) ? 1.15 : 1)
          * Math.sqrt(light.userData.requestedIntensity ?? light.intensity) / (1 + distance * distance)
        return { light, score }
      }).sort((a, b) => b.score - a.score)
    const selected = new Set(candidates.slice(0, BUDGET[quality]).map(entry => entry.light))
    let shadowsDirty = false
    for (const light of this.fixtures) {
      light.visible = selected.has(light)
      const castShadow = selected.has(light)
      if (light.castShadow !== castShadow) {
        light.castShadow = castShadow
        shadowsDirty = true
        if (!castShadow) { light.shadow.map?.dispose(); light.shadow.map = null }
      }
      if (castShadow) {
        light.shadow.autoUpdate = false
        const size = SHADOW_SIZE[quality]
        if (light.shadow.mapSize.x !== size) {
          light.shadow.map?.dispose()
          light.shadow.map = null
          light.shadow.mapSize.set(size, size)
          shadowsDirty = true
        }
        light.getWorldPosition(this.position)
        const target = light instanceof THREE.SpotLight ? light.target.getWorldPosition(this.viewPosition).toArray() : []
        const transform = [...this.position.toArray(), ...target, light.distance,
          light instanceof THREE.SpotLight ? light.angle : 0, size].join(',')
        if (this.shadowTransforms.get(light) !== transform || !light.shadow.map || !this.selected.has(light)) {
          this.shadowTransforms.set(light, transform)
          light.shadow.camera.near = 0.05
          light.shadow.camera.far = Math.max(0.1, light.distance || 12)
          light.shadow.camera.updateProjectionMatrix()
          light.shadow.needsUpdate = true
        }
        if (light.shadow.needsUpdate) shadowsDirty = true
        light.shadow.bias = -0.0002
        light.shadow.normalBias = 0.002
      }
    }
    this.selected = selected
    this.activeCount = selected.size
    this.shadowCount = selected.size
    return shadowsDirty
  }

  dispose(): void { this.setRoot(null) }
}
