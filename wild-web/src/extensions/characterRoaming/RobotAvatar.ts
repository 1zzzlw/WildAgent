import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'

/** 米制卡通巡游者；共享一张原创贴图，正面为局部 -Z。资源由本对象独立持有。 */
export class RobotAvatar {
  readonly root = new THREE.Group()
  private readonly body = new THREE.Group()
  private readonly hips: THREE.Group[] = []
  private readonly knees: THREE.Group[] = []
  private readonly shoulders: THREE.Group[] = []
  private readonly elbows: THREE.Group[] = []
  private phase = 0
  private stride = 0
  private flight = 0
  private disposed = false
  private readonly atlas: THREE.Texture

  constructor(requestRender: () => void = () => {}) {
    this.root.name = 'RoamingRobot'
    this.root.add(this.body)
    this.atlas = new THREE.TextureLoader().load(`${import.meta.env.BASE_URL}characters/wild-explorer-atlas.png`, texture => {
      if (this.disposed) { texture.dispose(); return }
      requestRender()
    })
    this.atlas.colorSpace = THREE.SRGBColorSpace
    this.atlas.minFilter = THREE.LinearFilter
    this.atlas.generateMipmaps = false
    const cloth = new THREE.MeshStandardMaterial({ map: this.atlas, roughness: .9,
      emissiveMap: this.atlas, emissive: 0xffffff, emissiveIntensity: .08 })
    const skin = new THREE.MeshStandardMaterial({ color: 0xeec7a5, roughness: .85 })
    const green = new THREE.MeshStandardMaterial({ color: 0x5e7356, roughness: .9 })
    const sole = new THREE.MeshStandardMaterial({ color: 0x34322e, roughness: 1 })
    const sphere = new THREE.SphereGeometry(1, 16, 12)
    const boxes = new Map<string, THREE.BufferGeometry>()
    // 图集从上到下为：脸、头发、外套正/背；裤装、靴子、袖子、背包。
    const box = (width: number, height: number, depth: number, tiles: number | number[]) => {
      const faces = typeof tiles === 'number' ? Array(6).fill(tiles) as number[] : tiles
      const key = [width, height, depth, ...faces].join(',')
      const cached = boxes.get(key)
      if (cached) return cached
      const geometry = new RoundedBoxGeometry(width, height, depth, 3, Math.min(width, height, depth) * .14)
      const uv = geometry.getAttribute('uv')
      for (const group of geometry.groups) {
        const tile = faces[group.materialIndex ?? 0]!
        for (let i = group.start; i < group.start + group.count; i++) {
          const vertex = geometry.index ? geometry.index.getX(i) : i
          uv.setXY(vertex, tile % 4 * .25 + .001 + uv.getX(vertex) * .248,
            (1 - Math.floor(tile / 4)) * .5 + .001 + uv.getY(vertex) * .498)
        }
      }
      // 所有面用同一材质，UV 决定各自取哪一块图集。
      geometry.clearGroups()
      boxes.set(key, geometry)
      return geometry
    }
    const mesh = (parent: THREE.Object3D, geometry: THREE.BufferGeometry, material: THREE.Material,
      position: [number, number, number], scale: [number, number, number]) => {
      const part = new THREE.Mesh(geometry, material)
      part.position.fromArray(position)
      part.scale.fromArray(scale)
      part.castShadow = true
      part.receiveShadow = true
      parent.add(part)
      return part
    }
    const unit: [number, number, number] = [1, 1, 1]
    mesh(this.body, box(.44, .5, .27, [6, 6, 6, 4, 3, 2]), cloth, [0, 1.03, 0], unit)
    mesh(this.body, box(.35, .19, .25, 4), cloth, [0, .79, 0], unit)
    mesh(this.body, sphere, skin, [0, 1.29, 0], [.075, .085, .075])
    mesh(this.body, box(.45, .46, .4, [1, 1, 1, 1, 1, 0]), cloth, [0, 1.5, -.01], unit)
    for (const side of [-1, 1]) mesh(this.body, sphere, skin, [side * .223, 1.49, -.01], [.036, .06, .045])
    mesh(this.body, box(.3, .37, .16, 7), cloth, [0, 1.04, .2], unit)
    const upperLeg = box(.17, .34, .2, 4)
    const lowerLeg = box(.15, .3, .18, 4)
    const upperArm = box(.15, .25, .18, 6)
    const lowerArm = box(.135, .24, .16, 6)
    const boot = box(.19, .2, .32, 5)
    const bootSole = box(.2, .055, .33, 5)
    for (const side of [-1, 1]) {
      const hip = new THREE.Group()
      hip.position.set(side * .105, .79, 0)
      this.root.add(hip)
      this.hips.push(hip)
      mesh(hip, upperLeg, cloth, [0, -.16, 0], unit)
      const knee = new THREE.Group()
      knee.position.y = -.32
      hip.add(knee)
      this.knees.push(knee)
      mesh(knee, sphere, green, [0, 0, 0], [.075, .07, .08])
      mesh(knee, lowerLeg, cloth, [0, -.16, 0], unit)
      mesh(knee, boot, cloth, [0, -.37, -.055], unit)
      mesh(knee, bootSole, sole, [0, -.442, -.055], unit)
      const shoulder = new THREE.Group()
      shoulder.position.set(side * .28, 1.21, 0)
      shoulder.rotation.z = side * .1
      this.body.add(shoulder)
      this.shoulders.push(shoulder)
      mesh(shoulder, sphere, green, [0, -.01, 0], [.085, .09, .1])
      mesh(shoulder, upperArm, cloth, [0, -.125, 0], unit)
      const elbow = new THREE.Group()
      elbow.position.y = -.25
      shoulder.add(elbow)
      this.elbows.push(elbow)
      mesh(elbow, lowerArm, cloth, [0, -.12, 0], unit)
      mesh(elbow, sphere, skin, [0, -.27, 0], [.065, .08, .065])
    }
  }

  update(delta: number, speed: number, grounded: boolean, yaw: number, flying = false): void {
    this.root.rotation.y = yaw
    this.stride = THREE.MathUtils.damp(this.stride, grounded ? Math.min(1, speed / 3.2) : 0, 12, delta)
    this.flight = THREE.MathUtils.damp(this.flight, flying ? 1 : 0, 8, delta)
    this.phase += (speed * 3.7 + 1.5) * delta
    this.body.position.y = Math.sin(this.phase) * (.006 + this.stride * .016)
    this.body.rotation.x = -this.flight * .12
    for (let i = 0; i < 2; i++) {
      const swing = Math.sin(this.phase + i * Math.PI) * this.stride
      this.hips[i]!.rotation.x = grounded ? swing * 0.6 : -0.25
      this.knees[i]!.rotation.x = grounded ? Math.max(0, -swing) * 0.8 : 0.6
      this.shoulders[i]!.rotation.x = grounded ? -swing * 0.65 : -0.75
      this.shoulders[i]!.rotation.z = (i === 0 ? -1 : 1) * (.1 + this.flight * .5)
      this.elbows[i]!.rotation.x = -0.12 - Math.max(0, swing) * 0.35
    }
  }

  dispose(): void {
    this.disposed = true
    this.root.removeFromParent()
    const geometries = new Set<THREE.BufferGeometry>()
    const materials = new Set<THREE.Material>()
    this.root.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return
      geometries.add(object.geometry)
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material)
    })
    geometries.forEach(geometry => geometry.dispose())
    materials.forEach(material => material.dispose())
    this.atlas.dispose()
  }
}
