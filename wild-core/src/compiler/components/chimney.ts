import type { ChimneyComponent, GeometryElement, Vec3 } from '../../wild-core/types'
import { ComponentCompileError } from '../types'
import type { ComponentCompileContext } from '../types'
import { assertNonEmptyString, assertPositive, assertVec3, createBox } from './attachedToWall'
import { attachPointsToRoof } from './attachedToSurface'

/** 将烟囱展开为四面薄壁和顶部压顶；当前不对屋顶执行布尔穿透。 */
export function compileChimney(
  component: ChimneyComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  assertNonEmptyString(component.id, 'id')
  assertVec3(component.position, 'position')
  assertPositive(component.width, 'width')
  assertPositive(component.depth, 'depth')
  assertPositive(component.height, 'height')
  const thickness = component.wallThickness ?? 0.12
  const capHeight = component.capHeight ?? 0.08
  assertPositive(thickness, 'wallThickness')
  assertPositive(capHeight, 'capHeight')
  if (thickness * 2 >= Math.min(component.width, component.depth)) {
    throw new ComponentCompileError('wallThickness 必须小于烟囱宽度和深度的一半', 'wallThickness')
  }
  const base = component.parentRoof
    ? attachPointsToRoof(component.parentRoof, [component.position], context)[0]
    : component.position
  const center: Vec3 = [base[0], base[1] + component.height / 2, base[2]]
  const elements: GeometryElement[] = [
    createBox(`${component.id}__wall_left`, [center[0] - component.width / 2 + thickness / 2, center[1], center[2]], [thickness, component.height, component.depth], 0, component.material),
    createBox(`${component.id}__wall_right`, [center[0] + component.width / 2 - thickness / 2, center[1], center[2]], [thickness, component.height, component.depth], 0, component.material),
    createBox(`${component.id}__wall_front`, [center[0], center[1], center[2] + component.depth / 2 - thickness / 2], [component.width - thickness * 2, component.height, thickness], 0, component.material),
    createBox(`${component.id}__wall_back`, [center[0], center[1], center[2] - component.depth / 2 + thickness / 2], [component.width - thickness * 2, component.height, thickness], 0, component.material),
    createBox(
      `${component.id}__cap`,
      [base[0], base[1] + component.height + capHeight / 2, base[2]],
      [component.width + thickness, capHeight, component.depth + thickness],
      0,
      component.capMaterial ?? component.material,
    ),
  ]
  return elements
}
