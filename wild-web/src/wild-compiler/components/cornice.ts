import type { CorniceComponent, GeometryElement, PrimitiveParams } from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import { ComponentCompileError } from '../types'
import { assertNonEmptyString } from './attachedToWall'
import { attachPointsToRoof } from './attachedToSurface'
import { validatePath } from './attachedToPath'

/** 将檐口截面沿路径扫掠；复用 Core 的 profile_sweep 通用几何。 */
export function compileCornice(
  component: CorniceComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  assertNonEmptyString(component.id, 'id')
  const path = component.parentRoof
    ? attachPointsToRoof(component.parentRoof, component.path, context)
    : component.path
  validatePath(path)
  if (!Array.isArray(component.profile) || component.profile.length < 3) {
    throw new ComponentCompileError('profile 至少需要三个二维截面点', 'profile')
  }
  for (const [index, point] of component.profile.entries()) {
    if (!Array.isArray(point) || point.length !== 2 || !point.every(Number.isFinite)) {
      throw new ComponentCompileError(`profile[${index}] 必须是两个有限数字`, 'profile')
    }
  }
  const sweep: PrimitiveParams = {
    type: 'primitive',
    id: `${component.id}__sweep`,
    shape: 'profile_sweep',
    path,
    profile: component.profile,
    closedProfile: component.closedProfile ?? true,
    material: component.material,
  }
  return [sweep]
}
