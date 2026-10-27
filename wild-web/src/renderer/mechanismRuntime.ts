import * as THREE from 'three'
import type { ElevatorElementBehavior, RotorElementBehavior } from 'wild-core/types'

type Member = THREE.Mesh & { userData: THREE.Mesh['userData'] }
interface ElevatorState {
  kind: 'elevator'; members: Member[]; anchor: Member; floor: number; target: number
  queue: number[]; phase: 'idle' | 'closing' | 'moving' | 'opening'; door: number
  offset: number; from: number; elapsed: number; dwell: number
}
interface RotorState {
  kind: 'rotor'; members: Member[]; anchor: Member; level: number; speed: number; angle: number
}
type Mechanism = ElevatorState | RotorState
const roots = new WeakMap<THREE.Object3D, Map<string, Mechanism>>()
const owners = new WeakMap<THREE.Object3D, Mechanism>()

/** 每次增量重建刷新成员；未被替换的设备继续运行，删除设备不留 RAF/计时器。 */
export function syncMechanisms(root: THREE.Object3D): void {
  const previous = roots.get(root), next = new Map<string, Mechanism>()
  const groups = new Map<string, Member[]>()
  root.traverse(object => {
    const b = object.userData.interaction
    if (!(object instanceof THREE.Mesh) || (b?.kind !== 'elevator' && b?.kind !== 'rotor')) return
    const list = groups.get(b.groupId) ?? []
    list.push(object); groups.set(b.groupId, list)
  })
  for (const [id, members] of groups) {
    const b = members[0]!.userData.interaction as ElevatorElementBehavior | RotorElementBehavior
    const anchor = members.find(m => m.name === id + '__cab' || m.name === id + '__hub')!
    if (!anchor) continue
    const old = previous?.get(id)
    let state: Mechanism
    if (old?.anchor === anchor) state = old
    else if (b.kind === 'elevator') state = { kind: 'elevator', members, anchor, floor: b.initialFloor, target: b.initialFloor, queue: [], phase: 'idle', door: 0, offset: 0, from: 0, elapsed: 0, dwell: 0 }
    else state = { kind: 'rotor', members, anchor, level: b.initiallyOn ? 1 : 0, speed: 0, angle: 0 }
    state.members = members
    next.set(id, state)
    for (const m of members) owners.set(m, state)
    applyState(state)
  }
  roots.set(root, next)
}

export function isMechanismControl(object: Pick<THREE.Object3D, 'userData'>): boolean {
  const b = object.userData.interaction
  return b?.kind === 'elevator' && (b.role === 'carButton' || b.role === 'hallButton')
    || b?.kind === 'rotor' && b.role === 'control'
}

export function interactMechanism(object: THREE.Object3D, requestRender: () => void): boolean {
  if (!isMechanismControl(object)) return false
  const state = owners.get(object)
  if (!state) return false
  if (state.kind === 'rotor') state.level = (state.level + 1) % 3
  else {
    const b = object.userData.interaction as ElevatorElementBehavior
    if (b.action === 'open') {
      if (state.phase === 'moving') return true
      state.phase = 'opening'; state.dwell = 0
    } else if (b.action === 'close') {
      if (state.phase !== 'moving') state.phase = 'closing'
    } else if (b.floor !== undefined) {
      if (state.phase !== 'moving' && b.floor === state.floor) state.phase = 'opening'
      else if (b.floor !== state.target || state.phase !== 'moving') {
        if (!state.queue.includes(b.floor)) state.queue.push(b.floor)
      }
    }
  }
  applyState(state)
  requestRender()
  return true
}

/** 与视口共用一条 RAF；返回 true 时继续绘制。 */
export function tickMechanisms(root: THREE.Object3D | null, delta: number): boolean {
  if (!root) return false
  let active = false
  const dt = THREE.MathUtils.clamp(delta, 0, 0.1)
  for (const state of roots.get(root)?.values() ?? []) {
    // 最后一次状态变化也必须绘制，下一帧才允许按需渲染休眠。
    active ||= state.kind === 'rotor' ? state.speed > 0 || state.level > 0 : state.phase !== 'idle' || state.queue.length > 0
    if (state.kind === 'rotor') {
      const b = state.anchor.userData.interaction as RotorElementBehavior
      const target = b.rpm * Math.PI * 2 / 60 * (state.level === 2 ? 1 : state.level === 1 ? 0.45 : 0)
      state.speed = THREE.MathUtils.damp(state.speed, target, 2, dt)
      if (!state.level && state.speed < 0.005) state.speed = 0
      state.angle = (state.angle + state.speed * dt) % (Math.PI * 2)
      active ||= state.speed > 0 || state.level > 0
    } else {
      const b = state.anchor.userData.interaction as ElevatorElementBehavior
      if (state.phase === 'idle' && state.queue.length) {
        state.dwell += dt
        if (state.door === 0 || state.dwell >= 2) state.phase = 'closing'
      }
      if (state.phase === 'closing') {
        state.door = Math.max(0, state.door - dt / 0.8)
        if (state.door === 0) {
          const target = state.queue.shift()
          if (target === undefined) state.phase = 'idle'
          else {
            state.target = target; state.from = state.offset; state.elapsed = 0
            state.phase = target === state.floor ? 'opening' : 'moving'
          }
        }
      } else if (state.phase === 'moving') {
        const to = (state.target - b.initialFloor) * b.floorHeight
        state.elapsed += dt
        const t = Math.min(1, state.elapsed / Math.max(1, Math.abs(to - state.from) / 0.9))
        state.offset = THREE.MathUtils.lerp(state.from, to, t * t * (3 - 2 * t))
        if (t === 1) { state.floor = state.target; state.phase = 'opening' }
      } else if (state.phase === 'opening') {
        state.door = Math.min(1, state.door + dt / 0.8)
        if (state.door === 1) { state.phase = 'idle'; state.dwell = 0 }
      }
      active ||= state.phase !== 'idle' || state.queue.length > 0
    }
    applyState(state)
  }
  return active
}

function applyState(state: Mechanism): void {
  for (const m of state.members) {
    const b = m.userData.interaction as ElevatorElementBehavior | RotorElementBehavior
    const origin = m.userData.interaction.closedPosition as [number, number, number]
    m.position.fromArray(origin)
    if (state.kind === 'elevator' && b.kind === 'elevator') {
      if (b.role === 'cab' || b.role === 'cabDoor' || b.role === 'carButton') m.position.y += state.offset
      const door = b.role === 'cabDoor' || b.role === 'landingDoor' && b.floor === state.floor && state.phase !== 'moving'
      if (door && b.doorOffset) m.position.addScaledVector(new THREE.Vector3(...b.doorOffset), state.door)
      m.userData.elevatorFloor = state.floor
      m.userData.elevatorTargetFloor = state.target
      m.userData.elevatorPhase = state.phase
      m.userData.elevatorDoorProgress = door ? state.door : 0
      if (isMechanismControl(m)) setIndicator(m, b.floor === state.floor && state.phase !== 'moving' || b.floor !== undefined && state.queue.includes(b.floor) || b.floor === state.target && state.phase === 'moving')
    } else if (state.kind === 'rotor' && b.kind === 'rotor') {
      if (b.role === 'rotor') {
        const pivot = new THREE.Vector3(...b.pivot)
        m.position.sub(pivot).applyAxisAngle(new THREE.Vector3(0, 1, 0), state.angle).add(pivot)
        m.rotation.fromArray([...m.userData.interaction.closedRotation, 'XYZ'] as [number, number, number, THREE.EulerOrder])
        m.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), state.angle))
      } else setIndicator(m, state.level > 0)
      m.userData.rotorLevel = state.level
      m.userData.rotorSpeed = state.speed
    }
  }
}

function setIndicator(mesh: THREE.Mesh, on: boolean): void {
  if (mesh.material instanceof THREE.MeshStandardMaterial) {
    mesh.material.emissive.setHex(on ? 0x63c7a0 : 0x000000)
    mesh.material.emissiveIntensity = on ? 0.7 : 0
  }
}
