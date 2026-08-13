import type { BalconyComponent, GeometryElement, RailingComponent } from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import {
  assertPositive,
  createBox,
  exteriorSurfaceOffset,
  resolveStraightWallFrame,
} from './attachedToWall'
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
  const { exteriorSign, surfaceOffset } = exteriorSurfaceOffset(
    frame, context, centerAlong, normalOffset,
  )
  const outwardDepth = exteriorSign * component.depth
  const slab = createBox(
    `${component.id}__slab`,
    frame.pointAt(
      centerAlong,
      topY - component.slabThickness / 2,
      surfaceOffset + outwardDepth / 2,
    ),
    [component.width, component.slabThickness, component.depth],
    frame.rotationAt(centerAlong),
    component.material,
  )
  const railing: RailingComponent = {
    type: 'railing',
    id: `${component.id}__railing`,
    path: [
      frame.pointAt(along, topY, surfaceOffset),
      frame.pointAt(along, topY, surfaceOffset + outwardDepth),
      frame.pointAt(along + component.width, topY, surfaceOffset + outwardDepth),
      frame.pointAt(along + component.width, topY, surfaceOffset),
    ],
    height: railingHeight,
    postSpacing,
    railLevels: [0.5, 1],
    material: component.railingMaterial,
  }
  return [slab, ...compileRailing(railing, context)]
}
