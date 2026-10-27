import * as THREE from 'three'
import { Capsule } from 'three/examples/jsm/math/Capsule.js'
import { RobotAvatar } from './RobotAvatar'
import { RoamingCollisionWorld } from './RoamingCollisionWorld'
import type { CharacterView } from './store'

interface RoamingOptions {
  scene: THREE.Scene
  worldRoot: THREE.Object3D
  camera: THREE.PerspectiveCamera
  canvas: HTMLCanvasElement
  groundY: number
  view: CharacterView
  interact: (object: THREE.Object3D) => boolean
  onLockChange: (locked: boolean) => void
  onViewChange: (view: CharacterView) => void
  onTargetChange: (label: string) => void
  onMessage: (message: string) => void
  requestRender: () => void
}

const HEIGHT = 1.75
const RADIUS = 0.24
const EYE_HEIGHT = 1.58
const STEP_HEIGHT = 0.32
const MOVE_KEYS = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'Space'])

/** 独立运行时：宿主只提供相机、显示根、交互回调和逐帧调用。无文档/编辑器依赖。 */
export class CharacterRoamingRuntime {
  private readonly options: RoamingOptions
  private readonly world: RoamingCollisionWorld
  private readonly robot: RobotAvatar
  private readonly body = new Capsule(new THREE.Vector3(), new THREE.Vector3(), RADIUS)
  private readonly velocity = new THREE.Vector3()
  private readonly keys = new Set<string>()
  private readonly savedCamera: { position: THREE.Vector3; quaternion: THREE.Quaternion; near: number; fov: number }
  private readonly savedTabIndex: string | null
  private readonly raycaster = new THREE.Raycaster()
  private readonly eye = new THREE.Vector3()
  private readonly direction = new THREE.Vector3()
  private readonly orientation = new THREE.Euler(0, 0, 0, 'YXZ')
  private yaw = 0
  private pitch = -0.15
  private grounded = true
  private jumpQueued = false
  private view: CharacterView
  private targetClock = 0
  private targetLabel = ''
  private disposed = false

  constructor(options: RoamingOptions) {
    this.options = options
    this.view = options.view
    this.savedCamera = {
      position: options.camera.position.clone(), quaternion: options.camera.quaternion.clone(),
      near: options.camera.near, fov: options.camera.fov,
    }
    this.savedTabIndex = options.canvas.getAttribute('tabindex')
    this.world = new RoamingCollisionWorld(options.worldRoot, options.groundY)
    this.robot = new RobotAvatar()
    options.scene.add(this.robot.root)
    this.spawn()
    options.camera.near = 0.04
    options.camera.fov = 65
    options.camera.updateProjectionMatrix()
    options.canvas.tabIndex = 0
    options.canvas.addEventListener('pointerdown', this.onPointerDown, true)
    options.canvas.addEventListener('contextmenu', this.onContextMenu, true)
    document.addEventListener('mousemove', this.onMouseMove)
    document.addEventListener('pointerlockchange', this.onPointerLockChange)
    document.addEventListener('pointerlockerror', this.onPointerLockError)
    document.addEventListener('visibilitychange', this.onVisibilityChange)
    window.addEventListener('keydown', this.onKeyDown, true)
    window.addEventListener('keyup', this.onKeyUp, true)
    window.addEventListener('blur', this.pause)
    this.updateCamera()
  }

  get locked(): boolean { return document.pointerLockElement === this.options.canvas }

  private spawn(): void {
    const bounds = this.world.bounds
    const feet = new THREE.Vector3(0, this.options.groundY + 0.02, bounds.isEmpty() ? 4 : bounds.max.z + 2)
    if (!bounds.isEmpty()) feet.x = (bounds.min.x + bounds.max.x) / 2
    this.body.start.copy(feet).y += RADIUS
    this.body.end.copy(feet).y += HEIGHT - RADIUS
    this.velocity.set(0, 0, 0)
    this.grounded = true
    this.syncAvatar(0)
  }

  capturePointer(): void {
    if (this.disposed || this.locked) return
    const canvas = this.options.canvas
    if (!canvas.requestPointerLock) {
      this.options.onMessage('当前浏览器不支持鼠标锁定，请使用桌面版浏览器。')
      return
    }
    canvas.focus({ preventScroll: true })
    try {
      Promise.resolve(canvas.requestPointerLock())
        .then(() => { if (this.disposed && this.locked) document.exitPointerLock() })
        .catch(() => this.onPointerLockError())
    } catch { this.onPointerLockError() }
  }

  setView(view: CharacterView): void {
    if (this.view === view || this.disposed) return
    this.view = view
    this.options.onViewChange(view)
    this.world.syncMoving()
    this.updateCamera()
    this.options.requestRender()
  }

  private readonly onPointerDown = (event: PointerEvent): void => {
    if (event.button === 0 && !this.locked) this.capturePointer()
    if (event.button === 2 && this.locked) {
      this.world.syncMoving()
      this.updateCamera()
      const target = this.interactionTarget()
      if (target) this.options.interact(target)
    }
    // 事件不能再落到OrbitControls或编辑器选取上。
    event.stopImmediatePropagation()
  }

  private readonly onContextMenu = (event: MouseEvent): void => {
    event.preventDefault()
    event.stopImmediatePropagation()
  }

  private readonly onMouseMove = (event: MouseEvent): void => {
    if (!this.locked) return
    this.yaw -= event.movementX * 0.0023
    this.pitch = THREE.MathUtils.clamp(this.pitch - event.movementY * 0.0023, -1.35, 1.35)
    this.options.requestRender()
  }

  private readonly onKeyDown = (event: KeyboardEvent): void => {
    const target = event.target as HTMLElement | null
    if (target?.closest('input,textarea,select,[contenteditable="true"],[role="dialog"]')) return
    if (event.code === 'F5' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault()
      event.stopImmediatePropagation()
      if (!event.repeat) this.setView(this.view === 'first' ? 'third' : 'first')
      return
    }
    if (!this.locked) return
    if ((event.ctrlKey || event.metaKey) && event.code === 'KeyS') return
    // 人物控制期间不让编辑快捷键撤销/删除构件；Escape仍交给浏览器释放鼠标。
    event.stopImmediatePropagation()
    if (event.code === 'Escape') { this.clearInput(); return }
    if (event.ctrlKey || event.metaKey || event.altKey) {
      if (['KeyZ', 'KeyY'].includes(event.code)) event.preventDefault()
      return
    }
    if (MOVE_KEYS.has(event.code)) {
      event.preventDefault()
      this.keys.add(event.code)
      if (event.code === 'Space' && !event.repeat) this.jumpQueued = true
    }
  }

  private readonly onKeyUp = (event: KeyboardEvent): void => {
    this.keys.delete(event.code)
    if (this.locked && MOVE_KEYS.has(event.code)) {
      event.preventDefault()
      event.stopImmediatePropagation()
    }
  }

  private clearInput(): void {
    this.keys.clear()
    this.jumpQueued = false
    this.velocity.set(0, 0, 0)
  }

  private readonly onPointerLockChange = (): void => {
    if (!this.locked) { this.clearInput(); this.setTargetLabel('') }
    else this.options.onMessage('')
    this.options.onLockChange(this.locked)
    this.options.requestRender()
  }

  private readonly onPointerLockError = (): void => {
    if (!this.disposed) this.options.onMessage('未能锁定鼠标，请点击画面重试。')
  }

  private readonly pause = (): void => {
    this.clearInput()
    if (this.locked) document.exitPointerLock()
  }

  private readonly onVisibilityChange = (): void => { if (document.hidden) this.pause() }

  /** 复用宿主RAF；固定小步长避免低帧率时穿过薄墙，不再启动第二套渲染循环。 */
  tick(delta: number): boolean {
    if (this.disposed || !this.locked) return false
    const elapsed = THREE.MathUtils.clamp(delta, 0, 0.05)
    if (this.grounded && this.velocity.y <= 0) this.world.carryPlatform(this.body)
    this.world.syncMoving()
    const steps = Math.max(1, Math.ceil(elapsed / (1 / 120)))
    for (let i = 0; i < steps; i++) this.move(elapsed / steps)
    this.syncAvatar(elapsed)
    this.updateCamera()
    this.targetClock += elapsed
    if (this.targetClock >= 0.1) {
      this.targetClock = 0
      const target = this.interactionTarget()
      const kind = target?.userData.interaction?.kind
      const b = target?.userData.interaction
      this.setTargetLabel(kind === 'opening' ? '右键 · 开关门窗' : kind === 'light' ? '右键 · 切换灯光' : kind === 'elevator' && b.role.endsWith('Button') ? '右键 · 电梯按钮' : kind === 'rotor' && b.role === 'control' ? '右键 · 风扇调速' : '')
    }
    return true
  }

  private move(delta: number): void {
    const x = Number(this.keys.has('KeyD')) - Number(this.keys.has('KeyA'))
    const z = Number(this.keys.has('KeyW')) - Number(this.keys.has('KeyS'))
    const wish = new THREE.Vector3(x, 0, -z)
    if (wish.lengthSq() > 0) wish.normalize().applyAxisAngle(THREE.Object3D.DEFAULT_UP, this.yaw).multiplyScalar(3.2)
    this.velocity.x = THREE.MathUtils.damp(this.velocity.x, wish.x, 14, delta)
    this.velocity.z = THREE.MathUtils.damp(this.velocity.z, wish.z, 14, delta)
    const wasGrounded = this.grounded
    const jumping = this.jumpQueued && wasGrounded
    this.jumpQueued = false
    if (jumping) this.velocity.y = 6
    this.velocity.y -= 18 * delta
    const before = this.body.clone()
    const movement = this.velocity.clone().multiplyScalar(delta)
    this.body.translate(movement)
    const contact = this.world.resolve(this.body, this.velocity)
    this.grounded = contact.grounded
    if (this.grounded && this.velocity.y < 0) this.velocity.y = 0
    const blocked = Math.hypot(this.body.start.x - before.start.x - movement.x, this.body.start.z - before.start.z - movement.z) > 0.005
    if (wasGrounded && !jumping && (contact.wall || blocked) && movement.x ** 2 + movement.z ** 2 > 1e-8) {
      this.tryStep(before, movement, delta)
    }
    if (wasGrounded && !jumping && this.velocity.y <= 0) this.snapToFloor()
  }

  private tryStep(before: Capsule, movement: THREE.Vector3, delta: number): void {
    const candidate = before.clone()
    candidate.translate(new THREE.Vector3(0, STEP_HEIGHT, 0))
    const expected = candidate.start.clone().add(new THREE.Vector3(movement.x, 0, movement.z))
    // 先检查抬高过程的头部空间，再检查水平通路。
    const emptyVelocity = new THREE.Vector3()
    this.world.resolve(candidate, emptyVelocity)
    if (candidate.start.distanceTo(before.start.clone().add(new THREE.Vector3(0, STEP_HEIGHT, 0))) > 0.01) return
    candidate.translate(new THREE.Vector3(movement.x, 0, movement.z))
    this.world.resolve(candidate, emptyVelocity)
    if (Math.hypot(candidate.start.x - expected.x, candidate.start.z - expected.z) > 0.005) return
    // 用整个胶囊向下找落脚。中心射线会漏掉尚位于脚前方的踏步边缘。
    const forward = new THREE.Vector3(movement.x, 0, movement.z).normalize()
    const blockedProgress = this.body.start.clone().sub(before.start).dot(forward)
    let remaining = STEP_HEIGHT + 0.06
    while (remaining > 0) {
      const down = Math.min(0.025, remaining)
      remaining -= down
      candidate.translate(new THREE.Vector3(0, -down, 0))
      const contact = this.world.resolve(candidate, emptyVelocity)
      if (!contact.grounded) continue
      const progress = candidate.start.clone().sub(before.start).dot(forward)
      if (candidate.start.y < before.start.y - 0.03 || progress <= blockedProgress + 1e-4) return
      this.body.copy(candidate)
      this.velocity.x = delta > 0 ? movement.x / delta : 0
      this.velocity.z = delta > 0 ? movement.z / delta : 0
      this.velocity.y = 0
      this.grounded = true
      return
    }
  }

  private snapToFloor(): void {
    const probe = this.body.start.clone(); probe.y += 0.08 - RADIUS
    const floor = this.world.floorHeight(probe, STEP_HEIGHT + 0.08)
    if (floor === null) return
    const candidate = this.body.clone()
    candidate.translate(new THREE.Vector3(0, floor + RADIUS + 0.002 - candidate.start.y, 0))
    const landing = candidate.start.clone()
    this.world.resolve(candidate, new THREE.Vector3())
    if (candidate.start.distanceTo(landing) > 0.015) return
    this.body.copy(candidate)
    this.velocity.y = 0
    this.grounded = true
  }

  private syncAvatar(delta: number): void {
    this.robot.root.position.copy(this.body.start).y -= RADIUS
    this.robot.update(delta, Math.hypot(this.velocity.x, this.velocity.z), this.grounded, this.yaw)
  }

  private updateCamera(): void {
    const camera = this.options.camera
    this.eye.copy(this.body.start).y += EYE_HEIGHT - RADIUS
    this.orientation.set(this.pitch, this.yaw, 0)
    camera.quaternion.setFromEuler(this.orientation)
    this.direction.set(0, 0, -1).applyQuaternion(camera.quaternion)
    camera.position.copy(this.eye)
    let distance = 0
    if (this.view === 'third') {
      const backwards = this.direction.clone().negate()
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion)
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion)
      distance = 3.8
      for (const offset of [new THREE.Vector3(), right.clone().multiplyScalar(0.14), right.clone().multiplyScalar(-0.14), up.clone().multiplyScalar(0.14), up.clone().multiplyScalar(-0.14)]) {
        distance = Math.min(distance, this.world.rayDistance(new THREE.Ray(this.eye.clone().add(offset), backwards), distance))
      }
      // 给近裁剪面留空间；相机贴墙时收近，不能透过墙体观察。
      distance = Math.max(0.05, distance - 0.2)
      camera.position.addScaledVector(backwards, distance)
    }
    this.robot.root.visible = this.view === 'third' && distance > 0.55
    camera.updateMatrixWorld(true)
  }

  private interactionTarget(): THREE.Mesh | null {
    this.raycaster.set(this.eye, this.direction)
    this.raycaster.far = 2.8
    // 只处理最近实体，不穿过墙壁挑选后面的门窗，也不命中机器人自己。
    const first = this.raycaster.intersectObjects(this.world.meshes, false)[0]
    return first?.object.userData.interaction ? first.object as THREE.Mesh : null
  }

  private setTargetLabel(label: string): void {
    if (label === this.targetLabel) return
    this.targetLabel = label
    this.options.onTargetChange(label)
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    const { canvas, camera } = this.options
    canvas.removeEventListener('pointerdown', this.onPointerDown, true)
    canvas.removeEventListener('contextmenu', this.onContextMenu, true)
    document.removeEventListener('mousemove', this.onMouseMove)
    document.removeEventListener('pointerlockchange', this.onPointerLockChange)
    document.removeEventListener('pointerlockerror', this.onPointerLockError)
    document.removeEventListener('visibilitychange', this.onVisibilityChange)
    window.removeEventListener('keydown', this.onKeyDown, true)
    window.removeEventListener('keyup', this.onKeyUp, true)
    window.removeEventListener('blur', this.pause)
    this.pause()
    if (this.savedTabIndex === null) canvas.removeAttribute('tabindex')
    else canvas.setAttribute('tabindex', this.savedTabIndex)
    this.robot.dispose()
    this.world.dispose()
    camera.position.copy(this.savedCamera.position)
    camera.quaternion.copy(this.savedCamera.quaternion)
    camera.near = this.savedCamera.near
    camera.fov = this.savedCamera.fov
    camera.updateProjectionMatrix()
    camera.updateMatrixWorld(true)
    this.options.onLockChange(false)
    this.options.onTargetChange('')
  }
}
