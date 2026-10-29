import * as THREE from 'three'
import type { BlueprintPresentation } from 'wild-core/types'
import {
  getWorldEnvironmentState, getWorldRenderingState,
  updateWorldEnvironmentState, updateWorldRenderingState,
} from './worldEnvironmentRuntime'

/** 在单蓝图查看器中应用作者默认值；离开后恢复查看器原来的选择。 */
export class BlueprintPresentationDefaults {
  private restore = () => {}

  apply(presentation?: BlueprintPresentation): void {
    this.reset()
    const environment = { ...getWorldEnvironmentState() }
    const style = getWorldRenderingState().style
    if (presentation?.environment) updateWorldEnvironmentState(presentation.environment)
    if (presentation?.style) updateWorldRenderingState({ style: presentation.style })
    this.restore = () => {
      if (presentation?.environment) updateWorldEnvironmentState(environment)
      if (presentation?.style) updateWorldRenderingState({ style })
    }
  }

  reset(): void { this.restore(); this.restore = () => {} }
}

interface EntrancePart {
  mesh: THREE.Mesh
  instance?: number
  matrix: THREE.Matrix4
  center: THREE.Vector3
  key: string
}

/** 展示变换与轮廓的生命周期；不修改几何数据、蓝图、历史或材质缓存。 */
export class BlueprintPresentationRuntime {
  private parts: EntrancePart[] = []
  private states = new Map<THREE.Mesh, { auto: boolean; culling: boolean }>()
  private outlines = new Map<THREE.Mesh, THREE.LineSegments[]>()
  private lineMaterial: THREE.LineBasicMaterial | null = null
  private elapsed = 0
  private duration = 1
  private ground = 0
  private readonly work = new THREE.Matrix4()
  private readonly scale = new THREE.Matrix4()
  private readonly pivot = new THREE.Matrix4()
  private readonly root: THREE.Group

  constructor(root: THREE.Group) { this.root = root }

  get active(): boolean { return this.parts.length > 0 }
  get progress(): number { return Math.min(1, this.elapsed / this.duration) }

  setStyle(style: BlueprintPresentation['style']): void {
    this.clearOutlines()
    if (style !== 'toon') return
    this.lineMaterial = new THREE.LineBasicMaterial({ color: 0x203148, transparent: true, opacity: .45 })
    for (const mesh of this.root.children) {
      if (!(mesh instanceof THREE.Mesh)) continue
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      if (materials.some(m => m.transparent || m instanceof THREE.MeshPhysicalMaterial && m.transmission > 0)) continue
      const geometry = new THREE.EdgesGeometry(mesh.geometry, 35)
      const lines: THREE.LineSegments[] = []
      const count = mesh instanceof THREE.InstancedMesh ? mesh.count : 1
      for (let index = 0; index < count; index++) {
        const line = new THREE.LineSegments(geometry, this.lineMaterial)
        line.name = 'PresentationOutline'
        line.raycast = () => {}
        if (mesh instanceof THREE.InstancedMesh) {
          line.matrixAutoUpdate = false
          mesh.getMatrixAt(index, line.matrix)
        }
        mesh.add(line)
        lines.push(line)
      }
      this.outlines.set(mesh, lines)
    }
  }

  start(entrance: BlueprintPresentation['entrance']): void {
    this.finish()
    if (!entrance) return
    this.duration = entrance.duration
    this.elapsed = 0
    let ordinal = 0
    let ground = Infinity
    for (const mesh of this.root.children) {
      if (!(mesh instanceof THREE.Mesh)) continue
      mesh.geometry.computeBoundingBox()
      const bounds = mesh.geometry.boundingBox!
      const count = mesh instanceof THREE.InstancedMesh ? mesh.count : 1
      this.states.set(mesh, { auto: mesh.matrixAutoUpdate, culling: mesh.frustumCulled })
      mesh.frustumCulled = false
      if (mesh.matrixAutoUpdate) mesh.updateMatrix()
      if (!(mesh instanceof THREE.InstancedMesh)) mesh.matrixAutoUpdate = false
      for (let index = 0; index < count; index++) {
        const matrix = mesh.matrix.clone()
        if (mesh instanceof THREE.InstancedMesh) mesh.getMatrixAt(index, matrix)
        const transformed = bounds.clone().applyMatrix4(matrix)
        ground = Math.min(ground, transformed.min.y)
        this.parts.push({ mesh, instance: mesh instanceof THREE.InstancedMesh ? index : undefined,
          matrix, center: transformed.getCenter(new THREE.Vector3()),
          key: `${mesh.userData.instanceElementIds?.[index] || mesh.name}:${ordinal++}` })
      }
    }
    this.ground = Number.isFinite(ground) ? ground : 0
    this.parts.sort((a, b) => a.center.y - b.center.y || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
    this.tick(0)
  }

  /** 返回本帧是否改变显示，包括结束时恢复最终变换的那一帧。 */
  tick(delta: number): boolean {
    if (!this.active) return false
    this.elapsed += Number.isFinite(delta) ? Math.max(0, delta) : 0
    if (this.elapsed >= this.duration) {
      this.finish()
      return true
    }
    this.parts.forEach((part, index) => {
      const delay = this.parts.length > 1 ? index / (this.parts.length - 1) * .7 : 0
      const t = THREE.MathUtils.clamp((this.elapsed / this.duration - delay) / .3, 0, 1)
      const eased = 1 - Math.pow(1 - t, 3)
      const s = .0001 + .9999 * eased
      const { center } = part
      this.work.makeTranslation(center.x, THREE.MathUtils.lerp(this.ground, center.y, eased), center.z)
      this.scale.makeScale(s, s, s)
      this.pivot.makeTranslation(-center.x, -center.y, -center.z)
      this.work.multiply(this.scale).multiply(this.pivot).multiply(part.matrix)
      this.setMatrix(part, this.work)
    })
    return true
  }

  finish(): void {
    for (const part of this.parts) this.setMatrix(part, part.matrix)
    for (const [mesh, state] of this.states) {
      mesh.matrixAutoUpdate = state.auto
      mesh.frustumCulled = state.culling
      if (mesh instanceof THREE.InstancedMesh) {
        mesh.boundingBox = null
        mesh.boundingSphere = null
      }
    }
    this.parts = []
    this.states.clear()
    this.elapsed = this.duration
  }

  reset(): void {
    this.finish()
    this.clearOutlines()
  }

  private setMatrix(part: EntrancePart, matrix: THREE.Matrix4): void {
    if (part.instance !== undefined && part.mesh instanceof THREE.InstancedMesh) {
      part.mesh.setMatrixAt(part.instance, matrix)
      part.mesh.instanceMatrix.needsUpdate = true
      const line = this.outlines.get(part.mesh)?.[part.instance]
      if (line) { line.matrix.copy(matrix); line.matrixWorldNeedsUpdate = true }
    } else {
      part.mesh.matrix.copy(matrix)
      part.mesh.matrixWorldNeedsUpdate = true
    }
  }

  private clearOutlines(): void {
    const geometries = new Set<THREE.BufferGeometry>()
    for (const lines of this.outlines.values()) for (const line of lines) {
      geometries.add(line.geometry)
      line.removeFromParent()
    }
    geometries.forEach(geometry => geometry.dispose())
    this.outlines.clear()
    this.lineMaterial?.dispose()
    this.lineMaterial = null
  }
}
