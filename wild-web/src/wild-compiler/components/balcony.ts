import type { BalconyComponent, GeometryElement, RailingComponent } from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import { assertPositive, createBox, resolveStraightWallFrame } from './attachedToWall'
import { compileRailing } from './railing'

/** 将墙体阳台展开为悬挑板和 U 形栏杆。 */
export function compileBalcony(
  component: BalconyComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  const frame = resolveStraightWallFrame(component, context)
  assertPositive(component.depth, 'depth')
  assertPositive(component.slabThickness, 'slabThickness')
  const railingHeight = component.railingHeight ?? 1.1
  const postSpacing = component.postSpacing ?? 0.9
  assertPositive(railingHeight, 'railingHeight')
  assertPositive(postSpacing, 'postSpacing')

  const [along, topY, normalOffset] = component.from
  const centerAlong = along + component.width / 2
  const exteriorSign = resolveExteriorSign(frame, context, centerAlong)
  const outwardDepth = exteriorSign * component.depth
  const slab = createBox(
    `${component.id}__slab`,
    frame.pointAt(
      centerAlong,
      topY - component.slabThickness / 2,
      normalOffset + outwardDepth / 2,
    ),
    [component.width, component.slabThickness, component.depth],
    frame.rotationAt(centerAlong),
    component.material,
  )
  const railing: RailingComponent = {
    type: 'railing',
    id: `${component.id}__railing`,
    path: [
      frame.pointAt(along, topY, normalOffset),
      frame.pointAt(along, topY, normalOffset + outwardDepth),
      frame.pointAt(along + component.width, topY, normalOffset + outwardDepth),
      frame.pointAt(along + component.width, topY, normalOffset),
    ],
    height: railingHeight,
    postSpacing,
    railLevels: [0.5, 1],
    material: component.railingMaterial,
  }
  return [slab, ...compileRailing(railing, context)]
}

/**
 * 根据所有墙体的水平包围盒判断父墙哪一侧背离建筑中心。
 * WILD 的墙方向并不保证顺/逆时针一致，因此不能固定使用局部 +normal。
 */
function resolveExteriorSign(
  frame: ReturnType<typeof resolveStraightWallFrame>,
  context: ComponentCompileContext,
  along: number,
): 1 | -1 {
  const walls = context.elements.filter(element => element.type === 'wall')
  const points = walls.flatMap(wall => [wall.from, wall.to])
  if (points.length === 0) return -1

  const minX = Math.min(...points.map(point => point[0]))
  const maxX = Math.max(...points.map(point => point[0]))
  const minZ = Math.min(...points.map(point => point[2]))
  const maxZ = Math.max(...points.map(point => point[2]))
  const buildingCenter = [(minX + maxX) / 2, (minZ + maxZ) / 2]
  const wallPoint = frame.pointAt(along, 0, 0)
  const normal = frame.normalAt(along)
  const outwardDot = (
    (wallPoint[0] - buildingCenter[0]) * normal[0]
    + (wallPoint[2] - buildingCenter[1]) * normal[2]
  )
  if (outwardDot > 1e-6) return 1
  if (outwardDot < -1e-6) return -1
  // 只有单墙、无法推断建筑内部时，优先兼容最常见的正立面 +X 墙。
  return -1
}
