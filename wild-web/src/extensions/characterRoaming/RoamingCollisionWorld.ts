import * as THREE from 'three'
import { Octree } from 'three/examples/jsm/math/Octree.js'
import { Capsule } from 'three/examples/jsm/math/Capsule.js'

interface DynamicCollider {
  mesh: THREE.Mesh
  matrix: THREE.Matrix4
  tree: Octree
}

/** 只读取宿主提供的显示网格，既不修改几何，也不拥有它的GPU资源。 */
export class RoamingCollisionWorld {
  readonly meshes: THREE.Mesh[] = []
  readonly bounds = new THREE.Box3()
  readonly groundY: number
  private readonly fixed = new Octree()
  private readonly moving: DynamicCollider[] = []
  private readonly trees: Octree[] = [this.fixed]

  constructor(root: THREE.Object3D, groundY: number) {
    this.groundY = groundY
    root.updateWorldMatrix(true, true)
    root.traverse(object => {
      if (!(object instanceof THREE.Mesh) || object.userData.isError) return
      // 不把文字面片、辅助线或水面当作承重实体；玻璃仍参与碰撞。
      if (!object.userData.materialRef && !object.userData.instanceElementIds) return
      const materials = Array.isArray(object.material) ? object.material : [object.material]
      if (materials.some(material => material.userData.wildWaterSurface)) return
      this.meshes.push(object)
      this.bounds.expandByObject(object)
      if (object.userData.interaction?.kind === 'opening' || object.userData.interaction?.kind === 'elevator') {
        const tree = new Octree()
        this.addMesh(tree, object)
        if (tree.triangles.length) tree.build()
        this.moving.push({ mesh: object, matrix: object.matrixWorld.clone(), tree })
        this.trees.push(tree)
      } else {
        this.addMesh(this.fixed, object)
      }
    })
    if (this.fixed.triangles.length) this.fixed.build()
  }

  private addMesh(tree: Octree, mesh: THREE.Mesh): void {
    const positions = mesh.geometry.getAttribute('position')
    if (!positions) return
    const indices = mesh.geometry.getIndex()
    const count = indices?.count ?? positions.count
    const matrix = new THREE.Matrix4()
    const instances = mesh instanceof THREE.InstancedMesh ? mesh.count : 1
    for (let instance = 0; instance < instances; instance++) {
      if (mesh instanceof THREE.InstancedMesh) {
        mesh.getMatrixAt(instance, matrix)
        matrix.premultiply(mesh.matrixWorld)
      } else matrix.copy(mesh.matrixWorld)
      const mirrored = matrix.determinant() < 0
      for (let i = 0; i + 2 < count; i += 3) {
        const triangle = new THREE.Triangle(
          new THREE.Vector3().fromBufferAttribute(positions, indices ? indices.getX(i) : i).applyMatrix4(matrix),
          new THREE.Vector3().fromBufferAttribute(positions, indices ? indices.getX(i + 1) : i + 1).applyMatrix4(matrix),
          new THREE.Vector3().fromBufferAttribute(positions, indices ? indices.getX(i + 2) : i + 2).applyMatrix4(matrix),
        )
        if (mirrored) [triangle.b, triangle.c] = [triangle.c, triangle.b]
        if (triangle.getArea() > 1e-10) tree.addTriangle(triangle)
      }
    }
  }

  /** 门窗动画只更新发生变换的活动碰撞体，不重新编译整个建筑。 */
  syncMoving(): void {
    for (const item of this.moving) {
      item.mesh.updateWorldMatrix(true, false)
      if (item.matrix.equals(item.mesh.matrixWorld)) continue
      item.matrix.copy(item.mesh.matrixWorld)
      item.tree.clear()
      this.addMesh(item.tree, item.mesh)
      if (item.tree.triangles.length) item.tree.build()
    }
  }

  resolve(capsule: Capsule, velocity: THREE.Vector3): { grounded: boolean; wall: boolean } {
    let grounded = false
    let wall = false
    for (let pass = 0; pass < 3; pass++) {
      let corrected = false
      for (const tree of this.trees) {
        if (!tree.box || !capsule.intersectsBox(tree.box)) continue
        const hit = tree.capsuleIntersect(capsule) as false | { normal: THREE.Vector3; depth: number }
        if (!hit || hit.depth < 1e-6) continue
        grounded ||= hit.normal.y > 0.55
        wall ||= Math.abs(hit.normal.y) < 0.55
        const inward = velocity.dot(hit.normal)
        if (inward < 0) velocity.addScaledVector(hit.normal, -inward)
        capsule.translate(hit.normal.clone().multiplyScalar(hit.depth + 1e-5))
        corrected = true
      }
      if (!corrected) break
    }
    const feet = capsule.start.y - capsule.radius
    if (feet < this.groundY) {
      capsule.translate(new THREE.Vector3(0, this.groundY - feet, 0))
      velocity.y = Math.max(0, velocity.y)
      grounded = true
    }
    return { grounded, wall }
  }

  rayDistance(ray: THREE.Ray, limit: number, walkableOnly = false): number {
    let distance = limit
    for (const tree of this.trees) {
      if (!tree.box || !ray.intersectsBox(tree.box)) continue
      const hit = tree.rayIntersect(ray) as false | { distance: number; triangle: THREE.Triangle }
      if (!hit || hit.distance > distance) continue
      if (walkableOnly && hit.triangle.getNormal(new THREE.Vector3()).y < 0.55) continue
      distance = hit.distance
    }
    if (walkableOnly && ray.direction.y < 0) {
      const groundDistance = (this.groundY - ray.origin.y) / ray.direction.y
      if (groundDistance >= 0 && groundDistance < distance) distance = groundDistance
    }
    return distance
  }

  floorHeight(position: THREE.Vector3, drop: number): number | null {
    const ray = new THREE.Ray(position, new THREE.Vector3(0, -1, 0))
    const distance = this.rayDistance(ray, drop, true)
    return distance < drop ? position.y - distance : null
  }

  dispose(): void {
    this.fixed.clear()
    for (const item of this.moving) item.tree.clear()
    this.moving.length = 0
    this.meshes.length = 0
    this.trees.length = 0
  }
}
