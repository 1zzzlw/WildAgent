import type { ElevatorComponent, ElevatorElementBehavior, GeometryElement, PrimitiveParams, Vec3 } from '../../../types'
import type { ComponentCompileContext } from '../types'
import { COMPONENT_MATERIAL } from '../componentMaterials'
import { assertNonEmptyString, assertPositive, assertVec3, resolveStraightWallFrame } from './attachedToWall'

/** 入口朝 +Z；position.y 是初始停靠层的地板完成面。井壁与楼板井洞仍由蓝图负责。 */
export function compileElevator(c: ElevatorComponent, context: ComponentCompileContext): GeometryElement[] {
  assertNonEmptyString(c.id, 'id')
  assertVec3(c.position, 'position')
  for (const [key, value] of Object.entries(c.dimensions)) assertPositive(value, 'dimensions.' + key)
  assertPositive(c.floorHeight, 'floorHeight')
  if (!Number.isInteger(c.floorCount) || c.floorCount < 1) throw new Error('elevator.floorCount 必须为正整数')
  const initialFloor = c.initialFloor ?? 0
  if (!Number.isInteger(initialFloor) || initialFloor < 0 || initialFloor >= c.floorCount) throw new Error('initialFloor 超出楼层范围')
  const { width: w, depth: d, height } = c.dimensions
  const h = Math.min(height, c.floorHeight - 0.15)
  if (w < 1.2 || d < 1.2 || h < 2.1) throw new Error('电梯净尺寸不足：宽深至少 1.2m、高至少 2.1m')
  if (c.landingWalls && c.landingWalls.length !== c.floorCount) throw new Error('landingWalls 必须逐层对应 floorCount')
  const [x, y, z] = c.position
  const baseY = y - initialFloor * c.floorHeight
  // 对开门完全收纳在轿厢正面两侧，不能滑出井道撞进相邻房间。
  const doorW = Math.min(1.1, (w - 0.16) / 2), doorH = h - 0.15, front = z + d / 2
  const result: GeometryElement[] = []
  const behavior = (role: ElevatorElementBehavior['role'], extra: Partial<ElevatorElementBehavior> = {}): ElevatorElementBehavior => ({
    kind: 'elevator', groupId: c.id, role, floorHeight: c.floorHeight, floorCount: c.floorCount, initialFloor, ...extra,
  })
  const box = (suffix: string, position: Vec3, dimensions: Vec3, material = c.material, interaction?: ElevatorElementBehavior, text?: string, rotation?: Vec3) => {
    const p: PrimitiveParams = { type: 'primitive', id: c.id + '__' + suffix, shape: 'box', position, dimensions, material }
    if (interaction) p._interaction = interaction
    if (text) p.label = { text, color: [1, 1, 1] }
    if (rotation) p.rotation = rotation
    result.push(p)
  }
  box('cab', [x, y - 0.05, z], [w, 0.1, d], c.floorMaterial ?? c.material, behavior('cab'))
  box('cab_roof', [x, y + h, z], [w, 0.08, d], c.material, behavior('cab'))
  box('cab_light', [x, y + h - 0.05, z], [0.35, 0.015, 0.3], COMPONENT_MATERIAL.bulbEmitter, behavior('cab', {
    light: { kind: 'light', lightType: 'point', color: [1, 0.87, 0.7], lowIntensity: 8, highIntensity: 8, distance: 3.5, angle: 60, initiallyOn: true, offset: [0, -0.05, 0] },
  }))
  box('cab_back', [x, y + h / 2, z - d / 2], [w, h, 0.06], c.material, behavior('cab'))
  for (const side of [-1, 1]) {
    box('cab_front_' + side, [x + side * (w + doorW) / 4, y + h / 2, front - 0.1], [(w - doorW) / 2, h, 0.06], c.material, behavior('cab'))
    box('cab_side_' + side, [x + side * w / 2, y + h / 2, z], [0.06, h, d], c.material, behavior('cab'))
    box('rail_' + side, [x + side * (w / 2 + 0.09), baseY + ((c.floorCount - 1) * c.floorHeight + h) / 2, z - d / 2 - 0.08], [0.06, (c.floorCount - 1) * c.floorHeight + h, 0.06], c.frameMaterial)
    box('cab_door_' + side, [x + side * doorW / 4, y + doorH / 2, front - 0.02], [doorW / 2 - 0.006, doorH, 0.035], c.doorMaterial ?? c.frameMaterial, behavior('cabDoor', { doorOffset: [side * doorW / 2, 0, 0] }))
  }
  box('cab_header', [x, y + (h + doorH) / 2, front - 0.1], [doorW, h - doorH, 0.06], c.material, behavior('cab'))
  for (let f = 0; f < c.floorCount; f++) {
    const fy = baseY + f * c.floorHeight
    if (c.landingWalls) {
      const wall = context.elements.find(e => e.id === c.landingWalls![f])
      if (wall?.type !== 'wall' || wall.curve) throw new Error('landingWalls 必须引用正对 +Z 入口的直线墙')
      const dx = wall.to[0] - wall.from[0], dz = wall.to[2] - wall.from[2]
      const length = Math.hypot(dx, dz)
      const along = (x - wall.from[0]) * dx / length
      if (Math.abs(dz) > 1e-6 || Math.abs(wall.from[2] - front - 0.08) > 0.03) throw new Error('层门墙应位于轿厢前方 0.08m，且沿 X 轴')
      resolveStraightWallFrame({ id: c.id, parentWall: wall.id, from: [along - doorW / 2, fy, 0], width: doorW, height: doorH }, context)
      result.push({ type: 'opening', id: c.id + '__landing_cutout_' + f, parentWall: wall.id, from: [along - doorW / 2, fy, 0], width: doorW, height: doorH, style: 'rectangular', _cutoutOnly: true })
    }
    for (const side of [-1, 1]) {
      box('landing_door_' + f + '_' + side, [x + side * doorW / 4, fy + doorH / 2, front + 0.08], [doorW / 2 - 0.006, doorH, 0.035], c.doorMaterial ?? c.frameMaterial, behavior('landingDoor', { floor: f, doorOffset: [side * doorW / 2, 0, 0] }))
      box('landing_jamb_' + f + '_' + side, [x + side * (doorW / 2 + 0.04), fy + doorH / 2, front + 0.08], [0.08, doorH + 0.08, 0.14], c.frameMaterial)
    }
    box('landing_header_' + f, [x, fy + doorH + 0.04, front + 0.08], [doorW + 0.16, 0.08, 0.14], c.frameMaterial)
    box('landing_sill_' + f, [x, fy - 0.025, front + 0.1], [doorW, 0.05, 0.26], c.frameMaterial)
    box('hall_' + f, [x + w / 2 + 0.16, fy + 1.1, front + 0.22], [0.12, 0.16, 0.035], COMPONENT_MATERIAL.frame, behavior('hallButton', { floor: f, action: 'call' }), String(f + 1))
  }
  // 轿内背板朝 +Z，便于从入口直接看到选层、开门和关门按钮。
  const columns = Math.max(1, Math.floor((w - 0.2) / 0.14))
  const actions = [...Array.from({ length: c.floorCount }, (_, floor) => ({ floor, action: 'call' as const, text: String(floor + 1) })),
    { action: 'open' as const, text: '◀▶' }, { action: 'close' as const, text: '▶◀' }]
  if (Math.ceil(actions.length / columns) * 0.16 > h - 0.8) throw new Error('选层按钮过多，当前轿厢无法容纳')
  actions.forEach((action, i) => box('car_button_' + i,
    [x + (i % columns - (Math.min(columns, actions.length) - 1) / 2) * 0.14, y + 1.1 + Math.floor(i / columns) * 0.16, z - d / 2 + 0.045],
    [0.11, 0.12, 0.025], COMPONENT_MATERIAL.frame, behavior('carButton', action), action.text))
  return result
}
