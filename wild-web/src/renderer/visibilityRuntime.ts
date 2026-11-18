import * as THREE from 'three'

interface BoundsCache {
  matrix: THREE.Matrix4
  geometry: THREE.BufferGeometry
  positionVersion: number
  indexVersion: number
  instanceVersion: number
  opaque: boolean
  range: string
  bounds: THREE.Box3
  triangles: THREE.Vector3[][]
}
interface Projection { minX: number; maxX: number; minY: number; maxY: number; near: number; far: number }
interface Occluder { mesh: THREE.Mesh; points: THREE.Vector3[]; far: number; area: number }

/**
 * 只剔除被一个真实不透明三角面完整遮住的包围盒，不以墙的包围盒代替墙面。
 * 因而门窗洞、玻璃、剖切和进入室内都不会被误判成封闭外壳。
 * 只在主画面及其 AO 绘制期间隐藏；阴影、反射、拾取仍使用完整场景。
 */
export class WorldVisibilityRuntime {
  enabled = true
  readonly stats = { tested: 0, occluded: 0, occluders: 0 }
  private readonly cache = new WeakMap<THREE.Mesh, BoundsCache>()
  private readonly viewProjection = new THREE.Matrix4()
  private readonly frustum = new THREE.Frustum()
  private readonly point = new THREE.Vector3()
  private readonly cameraPosition = new THREE.Vector3()
  private readonly cameraDirection = new THREE.Vector3()

  render(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera, draw: () => void): void {
    this.stats.tested = this.stats.occluded = this.stats.occluders = 0
    if (!this.enabled || renderer.clippingPlanes.length || renderer.xr.isPresenting) { draw(); return }
    const autoUpdate = scene.matrixWorldAutoUpdate
    if (autoUpdate) scene.updateMatrixWorld()
    if (camera.parent === null && camera.matrixWorldAutoUpdate) camera.updateMatrixWorld()
    // 主颜色与 AO 共享本帧变换，避免每个 pass 都遍历、重算整棵场景树。
    scene.matrixWorldAutoUpdate = false
    try { this.renderVisible(renderer,scene,camera,draw) }
    finally { scene.matrixWorldAutoUpdate = autoUpdate }
  }

  private renderVisible(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera, draw: () => void): void {
    this.cameraPosition.setFromMatrixPosition(camera.matrixWorld)
    camera.getWorldDirection(this.cameraDirection).negate()
    this.viewProjection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
    this.frustum.setFromProjectionMatrix(this.viewProjection)
    const meshes: THREE.Mesh[] = []
    const collect = (object: THREE.Object3D) => {
      if (!object.visible) return
      if (object.userData.wildRenderRoot) {
        // 组装动画暂时关闭 frustumCulled，期间使用原来的完整渲染。
        if (object.children.some(child => !child.frustumCulled)) return
        object.traverseVisible(child => {
          if (child instanceof THREE.Mesh && !(child instanceof THREE.SkinnedMesh) && !child.morphTargetInfluences?.length
            && child.frustumCulled && !child.children.length && child.layers.test(camera.layers)
            // 与 Three.js 绘制阶段使用同一保守球体测试，屏外网格不再参与遮挡投影计算。
            && this.frustum.intersectsObject(child)) meshes.push(child)
        })
      } else object.children.forEach(collect)
    }
    collect(scene)
    if (meshes.length < 32) { draw(); return }
    const occluders: Occluder[] = []
    for (const mesh of meshes) {
      if (mesh instanceof THREE.InstancedMesh) continue
      const sphere = mesh.geometry.boundingSphere
      const e = mesh.matrixWorld.elements
      const scaleBound = Math.hypot(e[0],e[1],e[2],e[4],e[5],e[6],e[8],e[9],e[10])
      // 半径 < 1.2m 的球容不下面积 ≥ 2m² 的三角形。
      // 矩阵 Frobenius 范数提供保守的缩放上界，包含非均匀缩放与剪切。
      if (sphere && sphere.radius * scaleBound < 1.2) continue
      const cached = this.bounds(mesh)
      for (const triangle of cached.triangles) {
        const [a,b,c] = triangle
        const towardCamera = camera instanceof THREE.OrthographicCamera ? this.cameraDirection : this.cameraPosition.clone().sub(a)
        const facing = new THREE.Vector3().subVectors(b,a).cross(new THREE.Vector3().subVectors(c,a))
          .dot(towardCamera) * Math.sign(mesh.matrixWorld.determinant())
        if ((mesh.material as THREE.Material).side === THREE.FrontSide && facing <= 0) continue
        const points = triangle.map(vertex => vertex.clone().applyMatrix4(this.viewProjection))
        if (points.some(p => p.z <= -1 || p.z >= 1)) continue
        if (points.every(p => p.x < -1) || points.every(p => p.x > 1)
          || points.every(p => p.y < -1) || points.every(p => p.y > 1)) continue
        const area = Math.abs((points[1].x-points[0].x)*(points[2].y-points[0].y)-(points[1].y-points[0].y)*(points[2].x-points[0].x))
        if (area < .005) continue
        const far = Math.max(...triangle.map(vertex => -vertex.clone().applyMatrix4(camera.matrixWorldInverse).z))
        occluders.push({ mesh, points, far, area })
      }
    }
    // 大面优先；限制判断预算，小构件不适合作遮挡体。
    occluders.sort((a,b) => b.area-a.area)
    occluders.length = Math.min(64, occluders.length)
    this.stats.occluders = occluders.length
    if (!occluders.length) { draw(); return }
    const hidden: THREE.Mesh[] = []
    for (const mesh of meshes) {
      const p = this.projectBounds(this.bounds(mesh).bounds, camera)
      if (!p) continue
      this.stats.tested++
      if (occluders.some(o => o.mesh !== mesh && o.far + .01 < p.near && this.covers(o.points,p))) {
        hidden.push(mesh)
        mesh.visible = false
      }
    }
    this.stats.occluded = hidden.length
    const shadowRender = renderer.shadowMap.render
    renderer.shadowMap.render = (...args) => {
      hidden.forEach(mesh => { mesh.visible = true })
      try { shadowRender.apply(renderer.shadowMap, args) }
      finally { hidden.forEach(mesh => { mesh.visible = false }) }
    }
    try { draw() }
    finally {
      hidden.forEach(mesh => { mesh.visible = true })
      renderer.shadowMap.render = shadowRender
    }
  }

  private bounds(mesh: THREE.Mesh): BoundsCache {
    const geometry = mesh.geometry, position = geometry.getAttribute('position') as THREE.BufferAttribute
    const material = mesh.material
    const opaque = !(mesh instanceof THREE.InstancedMesh) && !mesh.userData.interactive && !mesh.userData.interaction
      && material instanceof THREE.MeshStandardMaterial && material.visible && !material.transparent && material.opacity === 1
      && material.depthWrite && material.depthTest && !material.alphaHash && material.blending === THREE.NormalBlending
      && !(material instanceof THREE.MeshPhysicalMaterial && material.transmission > 0)
      && !material.alphaTest && !material.alphaMap && !material.displacementMap && !material.wireframe
      && !material.clippingPlanes?.length && material.side !== THREE.BackSide
    const instanceVersion = mesh instanceof THREE.InstancedMesh ? mesh.instanceMatrix.version : -1
    const range = `${geometry.drawRange.start}:${geometry.drawRange.count}`
    const previous = this.cache.get(mesh)
    if (previous && previous.geometry === geometry && previous.matrix.equals(mesh.matrixWorld)
      && previous.positionVersion === position.version && previous.indexVersion === (geometry.index?.version ?? -1)
      && previous.instanceVersion === instanceVersion && previous.opaque === opaque && previous.range === range) return previous
    geometry.computeBoundingBox()
    let localBounds = geometry.boundingBox!
    if (mesh instanceof THREE.InstancedMesh) {
      mesh.computeBoundingBox()
      localBounds = mesh.boundingBox!
    }
    const result: BoundsCache = { matrix: mesh.matrixWorld.clone(), geometry, positionVersion: position.version,
      indexVersion: geometry.index?.version ?? -1, instanceVersion, opaque, range, bounds: localBounds.clone().applyMatrix4(mesh.matrixWorld), triangles: [] }
    if (opaque && position.count <= 2048) {
      const index = geometry.index, end = Math.min(index?.count ?? position.count, geometry.drawRange.start + geometry.drawRange.count)
      for (let i=geometry.drawRange.start; i+2<end; i+=3) {
        const triangle = [0,1,2].map(offset => new THREE.Vector3().fromBufferAttribute(position, index ? index.getX(i+offset) : i+offset).applyMatrix4(mesh.matrixWorld))
        const [a,b,c] = triangle
        if (new THREE.Vector3().subVectors(b,a).cross(new THREE.Vector3().subVectors(c,a)).lengthSq() >= 16) result.triangles.push(triangle)
      }
    }
    this.cache.set(mesh, result)
    return result
  }

  private projectBounds(bounds: THREE.Box3, camera: THREE.Camera): Projection | null {
    const result = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity, near: Infinity, far: -Infinity }
    for (let i=0; i<8; i++) {
      const {min,max} = bounds
      this.point.set(i&1 ? max.x:min.x, i&2 ? max.y:min.y, i&4 ? max.z:min.z)
      const depth = -this.point.clone().applyMatrix4(camera.matrixWorldInverse).z
      this.point.applyMatrix4(this.viewProjection)
      if (this.point.z <= -1 || this.point.z >= 1) return null
      result.minX=Math.min(result.minX,this.point.x); result.maxX=Math.max(result.maxX,this.point.x)
      result.minY=Math.min(result.minY,this.point.y); result.maxY=Math.max(result.maxY,this.point.y)
      result.near=Math.min(result.near,depth); result.far=Math.max(result.far,depth)
    }
    if (result.maxX < -1 || result.minX > 1 || result.maxY < -1 || result.minY > 1) return null
    return result
  }

  private covers(triangle: THREE.Vector3[], p: Projection): boolean {
    // NDC 内缩余量避免浮点误差与边缘抗锯齿泄漏。
    let sign = 0
    for (let i=0;i<3;i++) {
      const a=triangle[i], b=triangle[(i+1)%3], dx=b.x-a.x, dy=b.y-a.y
      const center = dx*((p.minY+p.maxY)*.5-a.y)-dy*((p.minX+p.maxX)*.5-a.x)
      const nextSign = Math.sign(center)
      if (!nextSign || sign && sign!==nextSign) return false
      sign=nextSign
      const margin=.002 * Math.hypot(dx,dy)
      for (const x of [p.minX,p.maxX]) for (const y of [p.minY,p.maxY]) {
        if ((dx*(y-a.y)-dy*(x-a.x))*sign <= margin) return false
      }
    }
    return true
  }
}
