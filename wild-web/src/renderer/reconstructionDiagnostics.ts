import { Euler, Matrix4, Quaternion, Vector3 } from 'three'

import type {
  ReconstructionBounds,
  ReconstructionObservation,
  ReconstructionReport,
} from '../types/scene'

type Vec3Like = [number, number, number]

interface MeshLike {
  elementId?: string
  geometry?: ArrayLike<number>
  transform?: {
    position?: Vec3Like
    rotation?: Vec3Like
    scale?: Vec3Like
  }
}

interface DiagnosticLike {
  level: 'warning' | 'error'
  code: string
  message: string
  category: 'compiler_geometry' | 'core_geometry'
  repairLayer: 'compiler' | 'core'
  elementId?: string
  expectedBounds?: ReconstructionBounds
  actualBounds?: ReconstructionBounds
}

function emptyBounds(): ReconstructionBounds {
  return {
    min: [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY],
    max: [Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY],
  }
}

function isFiniteBounds(bounds: ReconstructionBounds): boolean {
  return bounds.min.every(Number.isFinite) && bounds.max.every(Number.isFinite)
}

function unionBounds(target: ReconstructionBounds, source: ReconstructionBounds): void {
  for (let axis = 0; axis < 3; axis += 1) {
    target.min[axis] = Math.min(target.min[axis], source.min[axis])
    target.max[axis] = Math.max(target.max[axis], source.max[axis])
  }
}

function meshWorldBounds(mesh: MeshLike): ReconstructionBounds | undefined {
  const positions = mesh.geometry
  if (!positions || positions.length < 3) return undefined

  const position = mesh.transform?.position ?? [0, 0, 0]
  const rotation = mesh.transform?.rotation ?? [0, 0, 0]
  const scale = mesh.transform?.scale ?? [1, 1, 1]
  const matrix = new Matrix4().compose(
    new Vector3(...position),
    new Quaternion().setFromEuler(new Euler(...rotation, 'XYZ')),
    new Vector3(...scale),
  )
  const bounds = emptyBounds()
  const point = new Vector3()
  for (let index = 0; index + 2 < positions.length; index += 3) {
    point.set(positions[index], positions[index + 1], positions[index + 2]).applyMatrix4(matrix)
    for (let axis = 0; axis < 3; axis += 1) {
      bounds.min[axis] = Math.min(bounds.min[axis], point.getComponent(axis))
      bounds.max[axis] = Math.max(bounds.max[axis], point.getComponent(axis))
    }
  }
  return isFiniteBounds(bounds) ? bounds : undefined
}

function aabbSeparation(left: ReconstructionBounds, right: ReconstructionBounds): number {
  const gaps = [0, 1, 2].map((axis) => Math.max(
    left.min[axis] - right.max[axis],
    right.min[axis] - left.max[axis],
    0,
  ))
  return Math.hypot(...gaps)
}

// ── 屋顶覆盖判据用的常量与工具 ────────────────────────────────
// 与 Python 侧 `app/tools/spatial_tools.py` 的 `_is_structural_wall` 一致：
// 矮墙（泳池壁、栏板）本来就不该有屋顶，不参与覆盖判定。
const STRUCTURAL_WALL_MIN_HEIGHT = 1.8
const STRUCTURAL_WALL_MIN_THICKNESS = 0.1
/** 边缘重合不算缺口：span/depth 恰等于墙中心线时浮点上会差几分之一毫米。 */
const ROOF_COVER_TOLERANCE = 0.1

/**
 * 结构性墙判定。用**蓝图参数**而不是网格包围盒：厚度是墙体参数，
 * 从渲染后的盒子上反推厚度会同时把门窗框算进去。
 */
function isStructuralWall(element: Record<string, any>): boolean {
  const bottom = Number(element.from?.[1])
  const top = Number(element.to?.[1])
  const thickness = Number(element.thickness ?? 0)
  if (!Number.isFinite(bottom) || !Number.isFinite(top)) return false
  return Math.abs(top - bottom) >= STRUCTURAL_WALL_MIN_HEIGHT
    && thickness >= STRUCTURAL_WALL_MIN_THICKNESS
}

/** 逐轴描述"覆盖范围比目标范围小"的那几侧，供诊断消息使用。 */
function describeUncovered(
  cover: ReconstructionBounds,
  target: ReconstructionBounds,
  tolerance: number,
): string[] {
  const messages: string[] = []
  const axes: Array<[0 | 2, string]> = [[0, 'X'], [2, 'Z']]
  for (const [axis, name] of axes) {
    const lowGap = cover.min[axis] - target.min[axis]
    const highGap = target.max[axis] - cover.max[axis]
    if (lowGap > tolerance) messages.push(`${name} 低侧缺 ${lowGap.toFixed(2)}m`)
    if (highGap > tolerance) messages.push(`${name} 高侧缺 ${highGap.toFixed(2)}m`)
  }
  return messages
}

function mappingIds(mapping: unknown, sourceId: string): string[] {
  if (Array.isArray(mapping)) {
    const entry = mapping.find((item) => item?.sourceId === sourceId || item?.componentId === sourceId)
    const ids = entry?.generatedElementIds ?? entry?.elementIds ?? entry?.renderedElementIds
    return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : []
  }
  if (mapping && typeof mapping === 'object') {
    const byComponent = (mapping as Record<string, any>).generatedElementIdsByComponentId
    const ids = byComponent?.[sourceId] ?? (mapping as Record<string, unknown>)[sourceId]
    return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : []
  }
  return []
}

function parentIdOf(component: Record<string, any>): string | undefined {
  const value = component.parentWall
    ?? component.parentFloor
    ?? component.parentRoof
    ?? component.parentWallId
    ?? component.wallId
    ?? component.parentId
    ?? component.properties?.parentWallId
    ?? component.properties?.wallId
    ?? component.properties?.parentId
  return typeof value === 'string' ? value : undefined
}

/**
 * 比较蓝图语义关系与 wild-core 实际网格包围盒。
 * 它只负责诊断，不修改几何，也不会把警告伪装成已修复。
 */
export function buildReconstructionDiagnostics(
  source: Record<string, any>,
  meshes: MeshLike[],
  componentMapping: unknown,
): { report: ReconstructionReport; diagnostics: DiagnosticLike[] } {
  const boundsByElement = new Map<string, ReconstructionBounds>()
  const meshCountByElement = new Map<string, number>()
  for (const mesh of meshes) {
    if (!mesh.elementId) continue
    const bounds = meshWorldBounds(mesh)
    if (!bounds) continue
    const aggregate = boundsByElement.get(mesh.elementId) ?? emptyBounds()
    unionBounds(aggregate, bounds)
    boundsByElement.set(mesh.elementId, aggregate)
    meshCountByElement.set(mesh.elementId, (meshCountByElement.get(mesh.elementId) ?? 0) + 1)
  }

  const observations: ReconstructionObservation[] = []
  const diagnostics: DiagnosticLike[] = []
  const sourceElements = Array.isArray(source.geometry?.elements) ? source.geometry.elements : []
  const components = Array.isArray(source.geometry?.components) ? source.geometry.components : []
  const walls = sourceElements.filter((element: Record<string, any>) => element.type === 'wall')
  // ⚠️ 这里必须是**结构性墙**的并集。用全量墙并集时，矮墙会把它拉大：
  // 本蓝图的泳池四壁高 1.5m、落在 z∈[-7,-2.6]，会把墙并集往 −Z 撑到 -7，
  // 而任何屋顶都不可能盖到泳池上 → 必然误报"覆盖不足"。
  const wallBounds = emptyBounds()
  for (const wall of walls) {
    if (!isStructuralWall(wall)) continue
    const bounds = boundsByElement.get(wall.id)
    if (bounds) unionBounds(wallBounds, bounds)
  }

  const addObservation = (
    item: Record<string, any>,
    renderedElementIds: string[],
    expectedRelation: ReconstructionObservation['expectedRelation'],
    targetId?: string,
    diagnosticLayer: 'compiler' | 'core' = 'core',
  ) => {
    const actualBounds = emptyBounds()
    let meshCount = 0
    for (const id of renderedElementIds) {
      const bounds = boundsByElement.get(id)
      if (bounds) unionBounds(actualBounds, bounds)
      meshCount += meshCountByElement.get(id) ?? 0
    }
    const actual = isFiniteBounds(actualBounds) ? actualBounds : undefined
    const expected = targetId ? boundsByElement.get(targetId) : undefined
    const separation = actual && expected ? aabbSeparation(actual, expected) : undefined
    let status: ReconstructionObservation['status'] = 'ok'
    let message: string | undefined

    if (!actual) {
      status = 'error'
      message = '源对象没有生成任何可定位网格'
      diagnostics.push({
        level: 'error',
        code: 'RECONSTRUCTION_MISSING_MESH',
        message: `[${item.id}] ${message}`,
        category: diagnosticLayer === 'compiler' ? 'compiler_geometry' : 'core_geometry',
        repairLayer: diagnosticLayer,
        elementId: item.id,
        expectedBounds: expected,
      })
    } else if (expectedRelation === 'attached_to_parent' && expected && separation !== undefined && separation > 0.35) {
      status = 'warning'
      message = `与宿主 ${targetId} 相距 ${separation.toFixed(3)}m`
      diagnostics.push({
        level: 'warning',
        code: 'RECONSTRUCTION_PARENT_SEPARATION',
        message: `[${item.id}] ${message}`,
        category: 'compiler_geometry',
        repairLayer: 'compiler',
        elementId: item.id,
        expectedBounds: expected,
        actualBounds: actual,
      })
    }

    observations.push({
      sourceId: item.id,
      sourceType: item.type ?? 'unknown',
      renderedElementIds,
      meshCount,
      status,
      expectedRelation,
      targetId,
      expectedBounds: expected,
      actualBounds: actual,
      separation,
      message,
    })
  }

  for (const element of sourceElements) {
    if (!element?.id || element.type === 'opening') continue
    addObservation(
      element,
      [element.id],
      element.type === 'roof' ? 'covers_walls' : 'self',
    )
    if (element.type === 'roof' && isFiniteBounds(wallBounds)) {
      // 只是把"期望范围"记进观测里供人看，**不再**在这里判对错。
      observations[observations.length - 1].expectedBounds = wallBounds
    }
  }

  // ── 屋顶覆盖：一次聚合判定，「屋顶并集 vs 结构墙并集」────────────
  // 历史实现逐块屋顶去比全楼墙并集，于是**任何多体量建筑**（L 形 / 退台 /
  // 主体+门廊）每一块屋顶都会被判"未完全覆盖"——实测一栋 3 块屋顶的别墅
  // 3 块全报 warning，而 Python 侧 7e 校验器 PASS、真实渲染也正常。
  // 多体量本来就该"每个体量各盖一块"，每块都不覆盖全楼是**正确**的。
  //
  // 本判据只做渲染侧自检，权威结论仍是流水线的 7e
  // （`validate_roof_top_coverage`，它还认"上层楼板 / 上层墙"也能盖住墙顶）。
  // 严重度：只报 ⚠️ 不报 ❌ —— 覆盖不完整按项目政策只标记、不阻断。
  if (isFiniteBounds(wallBounds)) {
    const roofUnion = emptyBounds()
    let roofCount = 0
    for (const element of sourceElements) {
      if (element?.type !== 'roof') continue
      const bounds = boundsByElement.get(element.id)
      if (!bounds) continue
      unionBounds(roofUnion, bounds)
      roofCount += 1
    }
    if (roofCount > 0 && isFiniteBounds(roofUnion)) {
      const uncovered = describeUncovered(roofUnion, wallBounds, ROOF_COVER_TOLERANCE)
      if (uncovered.length > 0) {
        diagnostics.push({
          level: 'warning',
          code: 'RECONSTRUCTION_ROOF_COVERAGE',
          message: `屋顶并集（${roofCount} 块）未完全覆盖结构墙范围：${uncovered.join('；')}`,
          category: 'core_geometry',
          repairLayer: 'core',
          expectedBounds: wallBounds,
          actualBounds: roofUnion,
        })
      }
    }
  }

  for (const component of components) {
    if (!component?.id) continue
    const generated = mappingIds(componentMapping, component.id)
    const parentId = parentIdOf(component)
    addObservation(component, generated, parentId ? 'attached_to_parent' : 'self', parentId, 'compiler')
  }

  return {
    report: {
      observations,
      errorCount: observations.filter((item) => item.status === 'error').length,
      warningCount: observations.filter((item) => item.status === 'warning').length,
    },
    diagnostics,
  }
}
