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
  activeCount = 0
  shadowCount = 0

  setRoot(root: THREE.Object3D | null): void {
    for (const light of this.fixtures) {
      light.visible = true
      light.castShadow = false
      light.shadow.map?.dispose()
      light.shadow.map = null
    }
    this.fixtures = []
    this.selected.clear()
    root?.traverse(object => {
      if ((object instanceof THREE.PointLight || object instanceof THREE.SpotLight) && object.userData.fixtureLight) this.fixtures.push(object)
    })
  }

  update(camera: THREE.Camera, quality: QualityLevel): boolean {
    camera.updateMatrixWorld()
    const cameraPosition = camera.getWorldPosition(new THREE.Vector3())
    const candidates = this.fixtures.filter(light => {
      if ((light.userData.requestedIntensity ?? light.intensity) <= 0) return false
      for (let parent = light.parent; parent; parent = parent.parent) if (!parent.visible) return false
      return true
    })
      .map(light => {
        light.getWorldPosition(this.position)
        const distance = this.position.distanceTo(cameraPosition)
        const inFront = this.position.clone().applyMatrix4(camera.matrixWorldInverse).z < 0
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
        const size = SHADOW_SIZE[quality]
        if (light.shadow.mapSize.x !== size) {
          light.shadow.map?.dispose()
          light.shadow.map = null
          light.shadow.mapSize.set(size, size)
          shadowsDirty = true
        }
        light.shadow.camera.near = 0.05
        light.shadow.camera.far = Math.max(0.1, light.distance || 12)
        light.shadow.camera.updateProjectionMatrix()
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
