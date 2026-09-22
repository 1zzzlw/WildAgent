import type {
  BalconyComponent,
  CanopyComponent,
  CorniceComponent,
  GeometryElement,
  PrimitiveParams,
  Vec3,
} from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import { ComponentCompileError } from '../types'
import {
  assertNonEmptyString,
  exteriorSurfaceOffset,
  resolveStraightWallFrame,
} from './attachedToWall'
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
  const visiblePaths = splitAroundWallAttachments(component, path, context)
  return visiblePaths.map((visiblePath, index): PrimitiveParams => ({
    type: 'primitive',
    id: visiblePaths.length === 1
      ? `${component.id}__sweep`
      : `${component.id}__sweep_${String(index + 1).padStart(3, '0')}`,
    shape: 'profile_sweep',
    path: visiblePath,
    profile: component.profile,
    closedProfile: component.closedProfile ?? true,
    material: component.material,
  }))
}

/**
 * 阳台板或雨棚与水平檐口占用同一墙面和标高时，只移除被遮挡的檐口段。
 * 路径按可见直线段输出，避免两个实体继续共面或互相穿插。
 */
function splitAroundWallAttachments(
  cornice: CorniceComponent,
  path: Vec3[],
  context: ComponentCompileContext,
): Vec3[][] {
  if (cornice.parentRoof) return [path]
  const minProfileY = Math.min(...cornice.profile.map(point => point[1]))
  const maxProfileY = Math.max(...cornice.profile.map(point => point[1]))
  const maxProfileOutset = Math.max(...cornice.profile.map(point => Math.abs(point[0])))
  const blockers = context.components.filter((item): item is BalconyComponent | CanopyComponent => (
    item.id !== cornice.id && (item.type === 'balcony' || item.type === 'canopy')
  ))
  if (blockers.length === 0) return [path]

  const visible: Vec3[][] = []
  let changed = false
  for (let segmentIndex = 0; segmentIndex < path.length - 1; segmentIndex++) {
    const start = path[segmentIndex]
    const end = path[segmentIndex + 1]
    const dx = end[0] - start[0]
    const dz = end[2] - start[2]
    const length = Math.hypot(dx, dz)
    if (length < 1e-6 || Math.abs(end[1] - start[1]) > 1e-6) {
      visible.push([start, end])
      continue
    }
    const direction = [dx / length, dz / length]
    const corniceMinY = start[1] + minProfileY
    const corniceMaxY = start[1] + maxProfileY
    const cuts: Array<[number, number]> = []

    for (const blocker of blockers) {
      const frame = resolveStraightWallFrame(blocker, context)
      const wallDx = frame.wall.to[0] - frame.wall.from[0]
      const wallDz = frame.wall.to[2] - frame.wall.from[2]
      const wallLength = Math.hypot(wallDx, wallDz)
      if (wallLength < 1e-6) continue
      const parallel = Math.abs(
        direction[0] * wallDx / wallLength + direction[1] * wallDz / wallLength,
      )
      if (parallel < 0.999) continue

      const wallNormal = frame.normalAt(blocker.from[0] + blocker.width / 2)
      const corniceNormalDistances = [start, end].map(point => (
        (point[0] - frame.wall.from[0]) * wallNormal[0]
        + (point[2] - frame.wall.from[2]) * wallNormal[2]
      ))
      const corniceNormalRange: [number, number] = [
        Math.min(...corniceNormalDistances) - maxProfileOutset,
        Math.max(...corniceNormalDistances) + maxProfileOutset,
      ]
      const { exteriorSign, surfaceOffset } = exteriorSurfaceOffset(
        frame,
        context,
        blocker.from[0] + blocker.width / 2,
        blocker.from[2],
      )
      const componentDepthEnd = surfaceOffset + exteriorSign * blocker.depth
      const componentNormalRange: [number, number] = [
        Math.min(surfaceOffset, componentDepthEnd),
        Math.max(surfaceOffset, componentDepthEnd),
      ]
      if (intervalOverlap(corniceNormalRange, componentNormalRange) <= 1e-6) continue

      const blockerMinY = blocker.type === 'balcony'
        ? blocker.from[1] - blocker.slabThickness
        : blocker.from[1] - blocker.thickness / 2
      const blockerMaxY = blocker.type === 'balcony'
        ? blocker.from[1]
        : blocker.from[1] + blocker.thickness / 2
      if (Math.min(corniceMaxY, blockerMaxY) - Math.max(corniceMinY, blockerMinY) <= 1e-6) {
        continue
      }

      const blockerStart = frame.pointAt(blocker.from[0], start[1], 0)
      const blockerEnd = frame.pointAt(blocker.from[0] + blocker.width, start[1], 0)
      const startDistance = projectDistance(start, direction, blockerStart)
      const endDistance = projectDistance(start, direction, blockerEnd)
      const clearance = maxProfileOutset
      cuts.push([
        Math.max(0, Math.min(startDistance, endDistance) - clearance),
        Math.min(length, Math.max(startDistance, endDistance) + clearance),
      ])
    }

    const mergedCuts = mergeIntervals(cuts.filter(([from, to]) => to - from > 1e-6))
    if (mergedCuts.length === 0) {
      visible.push([start, end])
      continue
    }
    changed = true
    let cursor = 0
    for (const [cutStart, cutEnd] of mergedCuts) {
      if (cutStart - cursor > 1e-6) {
        visible.push([
          pointAlong(start, end, cursor / length),
          pointAlong(start, end, cutStart / length),
        ])
      }
      cursor = Math.max(cursor, cutEnd)
    }
    if (length - cursor > 1e-6) {
      visible.push([pointAlong(start, end, cursor / length), end])
    }
  }
  return changed ? visible : [path]
}

function projectDistance(origin: Vec3, direction: number[], point: Vec3): number {
  return (point[0] - origin[0]) * direction[0] + (point[2] - origin[2]) * direction[1]
}

function intervalOverlap(left: [number, number], right: [number, number]): number {
  return Math.min(left[1], right[1]) - Math.max(left[0], right[0])
}

function pointAlong(start: Vec3, end: Vec3, ratio: number): Vec3 {
  return [
    start[0] + (end[0] - start[0]) * ratio,
    start[1] + (end[1] - start[1]) * ratio,
    start[2] + (end[2] - start[2]) * ratio,
  ]
}

function mergeIntervals(intervals: Array<[number, number]>): Array<[number, number]> {
  const sorted = [...intervals].sort((left, right) => left[0] - right[0])
  const merged: Array<[number, number]> = []
  for (const interval of sorted) {
    const previous = merged[merged.length - 1]
    if (!previous || interval[0] > previous[1] + 1e-6) merged.push([...interval])
    else previous[1] = Math.max(previous[1], interval[1])
  }
  return merged
}
