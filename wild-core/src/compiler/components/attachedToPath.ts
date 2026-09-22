import type { Vec3 } from '../../wild-core/types'
import { ComponentCompileError } from '../types'
import { assertPositive, assertVec3 } from './attachedToWall'

export function validatePath(path: Vec3[], field = 'path'): void {
  if (!Array.isArray(path) || path.length < 2) {
    throw new ComponentCompileError(`${field} 至少需要两个坐标点`, field)
  }
  path.forEach((point, index) => assertVec3(point, `${field}[${index}]`))
  for (let index = 0; index < path.length - 1; index++) {
    if (distance(path[index], path[index + 1]) < 1e-6) {
      throw new ComponentCompileError(
        `${field}[${index}] 与 ${field}[${index + 1}] 不能重合`,
        field,
      )
    }
  }
}

/** 按最大间距沿折线路径采样，并避免在连接点生成重复坐标。 */
export function samplePath(path: Vec3[], spacing: number): Vec3[] {
  validatePath(path)
  assertPositive(spacing, 'spacing')
  const points: Vec3[] = []
  for (let segmentIndex = 0; segmentIndex < path.length - 1; segmentIndex++) {
    const start = path[segmentIndex]
    const end = path[segmentIndex + 1]
    const intervals = Math.ceil(distance(start, end) / spacing)
    for (let step = segmentIndex === 0 ? 0 : 1; step <= intervals; step++) {
      const ratio = step / intervals
      points.push([
        start[0] + (end[0] - start[0]) * ratio,
        start[1] + (end[1] - start[1]) * ratio,
        start[2] + (end[2] - start[2]) * ratio,
      ])
    }
  }
  return points
}

/** 对一条直线路径做水平侧向偏移，供坡道两侧栏杆使用。 */
export function offsetStraightPath(path: [Vec3, Vec3], offset: number): [Vec3, Vec3] {
  const [start, end] = path
  const dx = end[0] - start[0]
  const dz = end[2] - start[2]
  const length = Math.hypot(dx, dz)
  if (length < 1e-6) {
    throw new ComponentCompileError('路径的水平投影长度必须大于 0', 'path')
  }
  const normalX = -dz / length
  const normalZ = dx / length
  return [
    [start[0] + normalX * offset, start[1], start[2] + normalZ * offset],
    [end[0] + normalX * offset, end[1], end[2] + normalZ * offset],
  ]
}

function distance(left: Vec3, right: Vec3): number {
  return Math.hypot(
    right[0] - left[0],
    right[1] - left[1],
    right[2] - left[2],
  )
}
