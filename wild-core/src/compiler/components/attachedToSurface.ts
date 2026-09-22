import type {
  FloorParams,
  RoofParams,
  Vec3,
} from '../../wild-core/types'
import { ComponentCompileError } from '../types'
import type { ComponentCompileContext } from '../types'
import { assertNonEmptyString, assertVec3 } from './attachedToWall'

/** 把楼板局部坐标转换为世界坐标；局部原点位于矩形楼板左下角顶面。 */
export function attachPointsToFloor(
  parentFloor: string,
  points: Vec3[],
  context: ComponentCompileContext,
  options: { allowOutside?: boolean } = {},
): Vec3[] {
  assertNonEmptyString(parentFloor, 'parentFloor')
  const floor = findElement<FloorParams>(parentFloor, 'floor', context)
  if (floor.shape === 'circle') {
    return points.map((point, index) => {
      assertVec3(point, `path[${index}]`)
      if (!options.allowOutside && Math.hypot(point[0], point[2]) > (floor.radius ?? 0) + 1e-6) {
        throw new ComponentCompileError(`path[${index}] 超出圆形父楼板边界`, 'path')
      }
      return [
        floor.from[0] + point[0],
        floor.from[1] + floor.thickness + point[1],
        floor.from[2] + point[2],
      ]
    })
  }
  if (!floor.to) {
    throw new ComponentCompileError(`父楼板 "${floor.id}" 缺少 to`, 'parentFloor')
  }
  const originX = Math.min(floor.from[0], floor.to[0])
  const originZ = Math.min(floor.from[2], floor.to[2])
  const width = Math.abs(floor.to[0] - floor.from[0])
  const depth = Math.abs(floor.to[2] - floor.from[2])
  return points.map((point, index) => {
    assertVec3(point, `path[${index}]`)
    if (
      !options.allowOutside
      && (point[0] < -1e-6 || point[0] > width + 1e-6
        || point[2] < -1e-6 || point[2] > depth + 1e-6)
    ) {
      throw new ComponentCompileError(`path[${index}] 超出父楼板边界`, 'path')
    }
    return [
      originX + point[0],
      floor.from[1] + floor.thickness + point[1],
      originZ + point[2],
    ]
  })
}

/** 把屋顶局部坐标转换为屋面世界坐标，支持当前稳定的 flat/gable/hip。 */
export function attachPointsToRoof(
  parentRoof: string,
  points: Vec3[],
  context: ComponentCompileContext,
): Vec3[] {
  assertNonEmptyString(parentRoof, 'parentRoof')
  const roof = findElement<RoofParams>(parentRoof, 'roof', context)
  if (!['flat', 'gable', 'hip'].includes(roof.roofType)) {
    throw new ComponentCompileError(
      `父屋顶 "${roof.id}" 的 ${roof.roofType} 暂不支持确定性局部依附`,
      'parentRoof',
    )
  }
  const origin = roof.position ?? inferRoofOrigin(context)
  const halfWidth = roof.span / 2
  const halfDepth = roof.depth / 2
  points.forEach((point, index) => assertVec3(point, `path[${index}]`))
  const isLocalPath = points.every(point => (
    Math.abs(point[0]) <= halfWidth + 1e-6
    && Math.abs(point[2]) <= halfDepth + 1e-6
  ))
  const isLegacyWorldPath = !isLocalPath && points.every(point => (
    Math.abs(point[0] - origin[0]) <= halfWidth + 1e-6
    && Math.abs(point[2] - origin[2]) <= halfDepth + 1e-6
  ))
  if (!isLocalPath && !isLegacyWorldPath) {
    const invalidIndex = points.findIndex(point => (
      Math.abs(point[0]) > halfWidth + 1e-6
      || Math.abs(point[2]) > halfDepth + 1e-6
    ))
    throw new ComponentCompileError(`path[${Math.max(0, invalidIndex)}] 超出父屋顶平面边界`, 'path')
  }
  return points.map(point => {
    // 兼容 2026-08-26 以前由后端错误写出的 world-space parentRoof
    // 路径。必须整条路径都能无歧义地落入屋顶世界包围盒才迁移。
    const localX = isLegacyWorldPath ? point[0] - origin[0] : point[0]
    const localZ = isLegacyWorldPath ? point[2] - origin[2] : point[2]
    const localY = isLegacyWorldPath
      ? point[1] - origin[1] - roofSurfaceHeight(roof, localX, localZ)
      : point[1]
    return [
      origin[0] + localX,
      origin[1] + roofSurfaceHeight(roof, localX, localZ) + localY,
      origin[2] + localZ,
    ]
  })
}

/** 与 Core 的基础屋顶自动定位保持一致，供编译阶段的屋面依附先行使用。 */
function inferRoofOrigin(context: ComponentCompileContext): Vec3 {
  const walls = context.elements.filter(element => element.type === 'wall') as Array<{
    from: Vec3
    to: Vec3
  }>
  if (walls.length < 3) return [0, 0, 0]

  const maximumHeight = Math.max(...walls.map(wall => Math.abs(wall.to[1] - wall.from[1])))
  const structuralWalls = walls.filter(
    wall => Math.abs(wall.to[1] - wall.from[1]) >= maximumHeight * 0.5,
  )
  const structuralCandidates = structuralWalls.length >= 3 ? structuralWalls : walls
  const highestWallTop = Math.max(
    ...structuralCandidates.map(wall => Math.max(wall.from[1], wall.to[1])),
  )
  const topSupportWalls = structuralCandidates.filter(
    wall => Math.abs(Math.max(wall.from[1], wall.to[1]) - highestWallTop) <= 0.05,
  )
  const effectiveWalls = topSupportWalls.length >= 3
    ? topSupportWalls
    : structuralCandidates
  const xs = effectiveWalls.flatMap(wall => [wall.from[0], wall.to[0]])
  const zs = effectiveWalls.flatMap(wall => [wall.from[2], wall.to[2]])
  const topY = Math.max(...effectiveWalls.flatMap(wall => [wall.from[1], wall.to[1]]))
  return [
    (Math.min(...xs) + Math.max(...xs)) / 2,
    topY,
    (Math.min(...zs) + Math.max(...zs)) / 2,
  ]
}

function roofSurfaceHeight(roof: RoofParams, localX: number, localZ: number): number {
  if (roof.roofType === 'flat') return roof.thickness
  const widthRatio = Math.min(1, Math.abs(localX) / (roof.span / 2))
  if (roof.roofType === 'gable') return roof.height * (1 - widthRatio)
  const depthRatio = Math.min(1, Math.abs(localZ) / (roof.depth / 2))
  return roof.height * (1 - Math.max(widthRatio, depthRatio))
}

function findElement<T>(
  id: string,
  type: string,
  context: ComponentCompileContext,
): T {
  const element = context.elements.find(item => item.id === id)
  if (!element) {
    throw new ComponentCompileError(`依附目标 "${id}" 不存在`, `parent${type}`)
  }
  if (element.type !== type) {
    throw new ComponentCompileError(`依附目标 "${id}" 不是 ${type}`, `parent${type}`)
  }
  return element as T
}
