import type {
  BeamParams,
  GeometryElement,
  PrimitiveParams,
  RailingComponent,
} from '../../wild-core/types'
import { ComponentCompileError } from '../types'
import type { ComponentCompileContext } from '../types'
import {
  assertNonEmptyString,
  assertPositive,
} from './attachedToWall'
import { attachPointsToFloor } from './attachedToSurface'
import { samplePath, validatePath } from './attachedToPath'

const MAX_POSTS = 2000

/** 将路径栏杆展开为等距圆柱立杆和沿路径分段的圆形横杆。 */
export function compileRailing(
  component: RailingComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  assertNonEmptyString(component.id, 'id')
  const path = component.parentFloor
    ? attachPointsToFloor(component.parentFloor, component.path, context)
    : component.path
  validatePath(path)
  assertPositive(component.height, 'height')

  const postSpacing = component.postSpacing ?? 1.2
  const postRadius = component.postRadius ?? 0.035
  const railRadius = component.railRadius ?? 0.045
  const railLevels = component.railLevels ?? [1]
  assertPositive(postSpacing, 'postSpacing')
  assertPositive(postRadius, 'postRadius')
  assertPositive(railRadius, 'railRadius')
  validateRailLevels(railLevels)

  const elements: GeometryElement[] = []
  const postBases = samplePath(path, postSpacing)
  if (postBases.length > MAX_POSTS) {
    throw new ComponentCompileError(
      `栏杆将生成 ${postBases.length} 根立杆，超过上限 ${MAX_POSTS}`,
      'postSpacing',
    )
  }

  postBases.forEach((base, index) => {
    const post: PrimitiveParams = {
      type: 'primitive',
      id: `${component.id}__post_${padIndex(index)}`,
      shape: 'cylinder',
      position: [base[0], base[1] + component.height / 2, base[2]],
      radius: postRadius,
      height: component.height,
      segments: 12,
    }
    if (component.material) post.material = component.material
    elements.push(post)
  })

  railLevels.forEach((level, levelIndex) => {
    for (let segmentIndex = 0; segmentIndex < path.length - 1; segmentIndex++) {
      const start = path[segmentIndex]
      const end = path[segmentIndex + 1]
      const rail: BeamParams = {
        type: 'beam',
        id: `${component.id}__rail_${padIndex(levelIndex)}_${padIndex(segmentIndex)}`,
        from: [start[0], start[1] + component.height * level, start[2]],
        to: [end[0], end[1] + component.height * level, end[2]],
        crossSection: 'circular',
        width: railRadius * 2,
        height: railRadius * 2,
      }
      if (component.material) rail.material = component.material
      elements.push(rail)
    }
  })

  return elements
}

function validateRailLevels(levels: number[]): void {
  if (!Array.isArray(levels) || levels.length === 0) {
    throw new ComponentCompileError('railLevels 至少需要一个高度比例', 'railLevels')
  }
  if (levels.length > 8) {
    throw new ComponentCompileError('railLevels 最多允许 8 层横杆', 'railLevels')
  }
  for (const level of levels) {
    if (!Number.isFinite(level) || level <= 0 || level > 1) {
      throw new ComponentCompileError(
        'railLevels 中的值必须位于 (0, 1] 范围',
        'railLevels',
      )
    }
  }
  if (new Set(levels).size !== levels.length) {
    throw new ComponentCompileError('railLevels 不能包含重复值', 'railLevels')
  }
}

function padIndex(index: number): string {
  return String(index + 1).padStart(3, '0')
}
