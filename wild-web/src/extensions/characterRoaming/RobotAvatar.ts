import * as THREE from 'three'

/** 米制程序化火柴机器人；所有资源由本对象独立持有。正面为局部 -Z。 */
export class RobotAvatar {
  readonly root = new THREE.Group()
  private readonly hips: THREE.Group[] = []
  private readonly knees: THREE.Group[] = []
  private readonly shoulders: THREE.Group[] = []
  private readonly elbows: THREE.Group[] = []
  private phase = 0
  private stride = 0

  constructor() {
    this.root.name = 'RoamingRobot'
    const sphere = new THREE.SphereGeometry(1, 12, 8)
    const rod = new THREE.CylinderGeometry(1, 1, 1, 8)
    const box = new THREE.BoxGeometry(1, 1, 1)
    const shell = new THREE.MeshStandardMaterial({ color: 0x293b48, metalness: 0.65, roughness: 0.35 })
    const joint = new THREE.MeshStandardMaterial({ color: 0xc3d0d4, metalness: 0.7, roughness: 0.3 })
    const glow = new THREE.MeshStandardMaterial({ color: 0x83f5d9, emissive: 0x36c8a7, emissiveIntensity: 0.8, roughness: 0.35 })
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
    mesh(this.root, rod, shell, [0, 1.17, 0], [0.065, 0.46, 0.065])
    mesh(this.root, box, shell, [0, 1.33, 0], [0.28, 0.23, 0.15])
    mesh(this.root, box, glow, [0, 1.33, -0.081], [0.11, 0.045, 0.015])
    mesh(this.root, sphere, joint, [0, 1.45, 0], [0.065, 0.065, 0.065])
    mesh(this.root, sphere, shell, [0, 1.58, 0], [0.16, 0.16, 0.15])
    mesh(this.root, box, glow, [0, 1.6, -0.14], [0.2, 0.043, 0.025])
    for (const side of [-1, 1]) {
      const hip = new THREE.Group()
      hip.position.set(side * 0.105, 0.87, 0)
      this.root.add(hip)
      this.hips.push(hip)
      mesh(hip, sphere, joint, [0, 0, 0], [0.075, 0.075, 0.075])
      mesh(hip, rod, shell, [0, -0.19, 0], [0.047, 0.38, 0.047])
      const knee = new THREE.Group()
      knee.position.y = -0.38
      hip.add(knee)
      this.knees.push(knee)
      mesh(knee, sphere, joint, [0, 0, 0], [0.06, 0.06, 0.06])
      mesh(knee, rod, shell, [0, -0.19, 0], [0.04, 0.38, 0.04])
      mesh(knee, box, shell, [0, -0.43, -0.045], [0.12, 0.12, 0.24])
      const shoulder = new THREE.Group()
      shoulder.position.set(side * 0.23, 1.37, 0)
      shoulder.rotation.z = side * 0.08
      this.root.add(shoulder)
      this.shoulders.push(shoulder)
      mesh(shoulder, sphere, joint, [0, 0, 0], [0.07, 0.07, 0.07])
      mesh(shoulder, rod, shell, [0, -0.145, 0], [0.035, 0.29, 0.035])
      const elbow = new THREE.Group()
      elbow.position.y = -0.29
      shoulder.add(elbow)
      this.elbows.push(elbow)
      mesh(elbow, sphere, joint, [0, 0, 0], [0.05, 0.05, 0.05])
      mesh(elbow, rod, shell, [0, -0.14, 0], [0.03, 0.28, 0.03])
      mesh(elbow, sphere, joint, [0, -0.3, 0], [0.055, 0.065, 0.055])
    }
  }

  update(delta: number, speed: number, grounded: boolean, yaw: number): void {
    this.root.rotation.y = yaw
    this.stride = THREE.MathUtils.damp(this.stride, grounded ? Math.min(1, speed / 3.2) : 0, 12, delta)
    this.phase += speed * delta * 3.7
    for (let i = 0; i < 2; i++) {
      const swing = Math.sin(this.phase + i * Math.PI) * this.stride
      this.hips[i]!.rotation.x = grounded ? swing * 0.6 : -0.25
      this.knees[i]!.rotation.x = grounded ? Math.max(0, -swing) * 0.8 : 0.6
      this.shoulders[i]!.rotation.x = grounded ? -swing * 0.65 : -0.75
      this.elbows[i]!.rotation.x = -0.12 - Math.max(0, swing) * 0.35
    }
  }

  dispose(): void {
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
  }
}
