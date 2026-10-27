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
      // 扇叶是头顶视觉转子，不建立过时的静态碰撞网格；电机与吊杆仍阻挡。
      if (object.userData.interaction?.kind === 'rotor' && object.userData.interaction.role === 'rotor') return
      this.meshes.push(object)
      this.bounds.expandByObject(object)
      if (object.userData.interaction?.kind === 'opening' || object.userData.interaction?.kind === 'elevator') {
        const tree = new Octree()
        this.addMesh(tree, object)
        this.buildTree(tree)
        this.moving.push({ mesh: object, matrix: object.matrixWorld.clone(), tree })
        this.trees.push(tree)
      } else {
        this.addMesh(this.fixed, object)
      }
    })
    this.buildTree(this.fixed)
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

  private buildTree(tree: Octree): void {
    if (!tree.triangles.length) return
    // Octree 只给最小边留余量；移动后的最大平面可能因分割舍入被所有子盒排除。
    // 将三角形留在外包盒内部，避免薄地板重建后间歇性丢失承重面。
    tree.bounds.expandByScalar(0.00001)
    tree.build()
  }

  /** 门窗动画只更新发生变换的活动碰撞体，不重新编译整个建筑。 */
  syncMoving(): void {
    for (const item of this.moving) {
      item.mesh.updateWorldMatrix(true, false)
      if (item.matrix.equals(item.mesh.matrixWorld)) continue
      item.matrix.copy(item.mesh.matrixWorld)
      item.tree.clear()
      this.addMesh(item.tree, item.mesh)
      this.buildTree(item.tree)
    }
  }

  /** 用上一帧的平台平面确认支撑，再携带乘客；上行与下行都无需靠碰撞挤推。 */
  carryPlatform(capsule: Capsule): void {
    const feet = capsule.start.y - capsule.radius
    for (const item of this.moving) {
      if (item.mesh.name !== item.mesh.userData.interaction?.groupId + '__cab') continue
      item.mesh.geometry.computeBoundingBox()
      const previous = item.mesh.geometry.boundingBox!.clone().applyMatrix4(item.matrix)
      if (Math.abs(feet - previous.max.y) > 0.08
        || capsule.start.x < previous.min.x || capsule.start.x > previous.max.x
        || capsule.start.z < previous.min.z || capsule.start.z > previous.max.z) continue
      item.mesh.updateWorldMatrix(true, false)
      const before = new THREE.Vector3().setFromMatrixPosition(item.matrix)
      const after = new THREE.Vector3().setFromMatrixPosition(item.mesh.matrixWorld)
      capsule.translate(after.sub(before))
      return
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
