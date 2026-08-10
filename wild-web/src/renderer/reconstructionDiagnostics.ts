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
  const wallBounds = emptyBounds()
  for (const wall of walls) {
    const bounds = boundsByElement.get(wall.id)
    if (bounds) unionBounds(wallBounds, bounds)
  }

  const addObservation = (
    item: Record<string, any>,
    renderedElementIds: string[],
    expectedRelation: ReconstructionObservation['expectedRelation'],
    targetId?: string,
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
      const observation = observations[observations.length - 1]
      observation.expectedBounds = wallBounds
      const roof = observation.actualBounds
      if (roof && (
        roof.min[0] > wallBounds.min[0] + 0.1
        || roof.max[0] < wallBounds.max[0] - 0.1
        || roof.min[2] > wallBounds.min[2] + 0.1
        || roof.max[2] < wallBounds.max[2] - 0.1
      )) {
        observation.status = 'warning'
        observation.message = '屋顶重建范围未完全覆盖墙体范围'
        diagnostics.push({
          level: 'warning',
          code: 'RECONSTRUCTION_ROOF_COVERAGE',
          message: `[${element.id}] ${observation.message}`,
          elementId: element.id,
          expectedBounds: wallBounds,
          actualBounds: roof,
        })
      }
    }
  }

  for (const component of components) {
    if (!component?.id) continue
    const generated = mappingIds(componentMapping, component.id)
    const parentId = parentIdOf(component)
    addObservation(component, generated, parentId ? 'attached_to_parent' : 'self', parentId)
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
