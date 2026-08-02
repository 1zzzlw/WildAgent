import type { CanopyComponent, GeometryElement } from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import { ComponentCompileError } from '../types'
import {
  assertNonNegativeInteger,
  assertPositive,
  createBox,
  resolveStraightWallFrame,
} from './attachedToWall'

/** 将墙体雨棚展开为顶板和可选支柱。 */
export function compileCanopy(
  component: CanopyComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  const frame = resolveStraightWallFrame(component, context)
  assertPositive(component.depth, 'depth')
  assertPositive(component.thickness, 'thickness')
  const supportCount = component.supportCount ?? 0
  const supportSize = component.supportSize ?? 0.06
  assertNonNegativeInteger(supportCount, 'supportCount', 16)
  assertPositive(supportSize, 'supportSize')

  const [along, mountY, normalOffset] = component.from
  const centerAlong = along + component.width / 2
  const elements: GeometryElement[] = [createBox(
    `${component.id}__slab`,
    frame.pointAt(centerAlong, mountY, normalOffset + component.depth / 2),
    [component.width, component.thickness, component.depth],
    frame.rotationAt(centerAlong),
    component.material,
  )]

  if (supportCount > 0) {
    const wallBottom = Math.min(frame.wall.from[1], frame.wall.to[1])
    const supportHeight = mountY - component.thickness / 2 - wallBottom
    if (supportHeight <= 0) {
      throw new ComponentCompileError('雨棚安装高度不足以生成支柱', 'from')
    }
    for (let index = 0; index < supportCount; index++) {
      const ratio = (index + 1) / (supportCount + 1)
      const supportAlong = along + component.width * ratio
      elements.push(createBox(
        `${component.id}__support_${padIndex(index)}`,
        frame.pointAt(
          supportAlong,
          wallBottom + supportHeight / 2,
          normalOffset + component.depth - supportSize / 2,
        ),
        [supportSize, supportHeight, supportSize],
        frame.rotationAt(supportAlong),
        component.supportMaterial ?? component.material,
      ))
    }
  }
  return elements
}

function padIndex(index: number): string {
  return String(index + 1).padStart(3, '0')
}
