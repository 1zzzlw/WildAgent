import type { GeometryElement, PrimitiveParams, RampComponent, RailingComponent, Vec3 } from '../../wild-core/types'
import { ComponentCompileError } from '../types'
import type { ComponentCompileContext } from '../types'
import { assertNonEmptyString, assertPositive, assertVec3 } from './attachedToWall'
import { attachPointsToFloor } from './attachedToSurface'
import { offsetStraightPath } from './attachedToPath'
import { compileRailing } from './railing'

/** 将直线坡道展开为连续斜面、侧缘挡台和随坡栏杆。 */
export function compileRamp(
  component: RampComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  assertNonEmptyString(component.id, 'id')
  assertVec3(component.from, 'from')
  assertVec3(component.to, 'to')
  assertPositive(component.width, 'width')
  assertPositive(component.thickness, 'thickness')
  const resolved = component.parentFloor
    ? attachPointsToFloor(component.parentFloor, [component.from, component.to], context, { allowOutside: true })
    : [component.from, component.to]
  const from = resolved[0]
  const to = resolved[1]
  if (Math.hypot(to[0] - from[0], to[1] - from[1], to[2] - from[2]) < 1e-6) {
    throw new ComponentCompileError('坡道 from 与 to 不能重合', 'to')
  }
  if (Math.hypot(to[0] - from[0], to[2] - from[2]) < 1e-6) {
    throw new ComponentCompileError('坡道必须具有水平延伸距离，不能是竖直构件', 'to')
  }

  // profile_sweep 的 v=0 边严格经过 from/to，栏杆和挡台可以共享同一坡面基线；
  // 这比把矩形 beam 轴线下移半个厚度更准确，也不会在斜率变化时产生悬空。
  const ramp: PrimitiveParams = {
    type: 'primitive',
    id: `${component.id}__surface`,
    shape: 'profile_sweep',
    path: [from, to],
    profile: [
      [-component.width / 2, -component.thickness],
      [component.width / 2, -component.thickness],
      [component.width / 2, 0],
      [-component.width / 2, 0],
    ],
    closedProfile: true,
    material: component.material,
  }
  const elements: GeometryElement[] = [ramp]
  const sides = component.railingSides ?? 'both'
  if (sides === 'none') return elements

  const railingHeight = component.railingHeight ?? 1.1
  const postSpacing = component.postSpacing ?? 0.9
  assertPositive(railingHeight, 'railingHeight')
  assertPositive(postSpacing, 'postSpacing')
  const curbHeight = Math.min(0.1, railingHeight * 0.15)
  const curbWidth = Math.min(0.08, component.width * 0.08)
  const sideEntries: Array<{ name: string; sign: number }> = []
  if (sides === 'left' || sides === 'both') sideEntries.push({ name: 'left', sign: 1 })
  if (sides === 'right' || sides === 'both') sideEntries.push({ name: 'right', sign: -1 })

  for (const side of sideEntries) {
    const path = offsetStraightPath([from, to] as [Vec3, Vec3], component.width / 2 * side.sign)
    const curb: PrimitiveParams = {
      type: 'primitive',
      id: `${component.id}__curb_${side.name}`,
      shape: 'profile_sweep',
      path,
      profile: [
        [-curbWidth / 2, 0],
        [curbWidth / 2, 0],
        [curbWidth / 2, curbHeight],
        [-curbWidth / 2, curbHeight],
      ],
      closedProfile: true,
      material: component.material,
    }
    elements.push(curb)

    const railingPath = offsetPathAboveSlope(path, curbHeight)
    const railing: RailingComponent = {
      type: 'railing',
      id: `${component.id}__railing_${side.name}`,
      path: railingPath,
      height: railingHeight - curbHeight,
      postSpacing,
      railLevels: [0.55, 1],
      material: component.railingMaterial,
    }
    elements.push(...compileRailing(railing, context))
  }
  return elements
}

/** 沿坡面法线抬高路径，使栏杆立柱准确落在侧缘挡台顶面。 */
function offsetPathAboveSlope(path: [Vec3, Vec3], distance: number): [Vec3, Vec3] {
  const [start, end] = path
  const dx = end[0] - start[0]
  const dy = end[1] - start[1]
  const dz = end[2] - start[2]
  const horizontal = Math.hypot(dx, dz)
  const length = Math.hypot(horizontal, dy)
  const up: Vec3 = [
    -dy * dx / (length * horizontal),
    horizontal / length,
    -dy * dz / (length * horizontal),
  ]
  return [
    [start[0] + up[0] * distance, start[1] + up[1] * distance, start[2] + up[2] * distance],
    [end[0] + up[0] * distance, end[1] + up[1] * distance, end[2] + up[2] * distance],
  ]
}
