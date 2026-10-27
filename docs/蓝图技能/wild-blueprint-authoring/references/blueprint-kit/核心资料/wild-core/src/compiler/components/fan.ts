import type { FanComponent, GeometryElement, PrimitiveParams, RotorElementBehavior } from '../../../types'
import { assertNonEmptyString, assertPositive, assertVec3 } from './attachedToWall'

export function compileFan(c: FanComponent): GeometryElement[] {
  assertNonEmptyString(c.id, 'id')
  assertVec3(c.position, 'position')
  assertVec3(c.controlPosition, 'controlPosition')
  const r = c.radius ?? 0.65, count = c.bladeCount ?? 4, drop = c.drop ?? 0.25, rpm = c.rpm ?? 180
  assertPositive(r, 'radius'); assertPositive(drop, 'drop'); assertPositive(rpm, 'rpm')
  if (!Number.isInteger(count) || count < 3 || count > 8 || rpm > 600) throw new Error('风扇叶片数须为 3–8，rpm 不超过 600')
  const [x, y, z] = c.position
  const behavior = (role: RotorElementBehavior['role']): RotorElementBehavior => ({ kind: 'rotor', groupId: c.id, role, pivot: c.position, rpm, initiallyOn: c.initiallyOn ?? false })
  const result: PrimitiveParams[] = [
    { type: 'primitive', id: c.id + '__rod', shape: 'cylinder', position: [x, y + drop / 2, z], radius: 0.018, height: drop, material: c.frameMaterial },
    { type: 'primitive', id: c.id + '__motor', shape: 'cylinder', position: c.position, radius: r * 0.19, height: 0.12, material: c.frameMaterial },
    { type: 'primitive', id: c.id + '__hub', shape: 'sphere', position: [x, y - 0.065, z], radius: r * 0.15, scale: [1, 0.5, 1], material: c.frameMaterial, _interaction: behavior('rotor') },
    { type: 'primitive', id: c.id + '__control', shape: 'box', position: c.controlPosition, dimensions: [0.12, 0.17, 0.035], material: c.frameMaterial, label: { text: 'FAN', color: [1, 1, 1] }, _interaction: behavior('control') },
  ]
  for (let i = 0; i < count; i++) {
    const a = i * Math.PI * 2 / count
    result.push({ type: 'primitive', id: c.id + '__blade_' + i, shape: 'box', position: [x + Math.cos(a) * r * 0.55, y - 0.04, z - Math.sin(a) * r * 0.55], dimensions: [r * 0.85, 0.018, r * 0.2], rotation: [0, a, 0.12], material: c.material, _interaction: behavior('rotor') })
  }
  return result as GeometryElement[]
}
