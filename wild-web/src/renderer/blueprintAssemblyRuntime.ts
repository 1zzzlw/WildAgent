import * as THREE from 'three'

interface AssemblyPart {
  mesh: THREE.Mesh
  instance?: number
  matrix: THREE.Matrix4
  center: THREE.Vector3
  key: string
}

/** 前端组装动画；不读取蓝图字段，不改写几何或文档。 */
export class BlueprintAssemblyRuntime {
  private readonly root: THREE.Group
  private parts: AssemblyPart[] = []
  private states = new Map<THREE.Mesh, { auto: boolean; culling: boolean }>()
  private elapsed = 0
  private readonly duration = 10
  private ground = 0
  private readonly work = new THREE.Matrix4()
  private readonly scale = new THREE.Matrix4()
  private readonly pivot = new THREE.Matrix4()

  constructor(root: THREE.Group) {
    this.root = root
  }

  get active(): boolean { return this.parts.length > 0 }
  get progress(): number { return Math.min(1, this.elapsed / this.duration) }

  start(): void {
    this.finish()
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

  /** 包括结束后恢复原变换的最后一帧。 */
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

  private setMatrix(part: AssemblyPart, matrix: THREE.Matrix4): void {
    if (part.instance !== undefined && part.mesh instanceof THREE.InstancedMesh) {
      part.mesh.setMatrixAt(part.instance, matrix)
      part.mesh.instanceMatrix.needsUpdate = true
    } else {
      part.mesh.matrix.copy(matrix)
      part.mesh.matrixWorldNeedsUpdate = true
    }
  }
}
