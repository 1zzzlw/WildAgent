/** Explicit geometric hosts; editor groups and room membership are not ownership. */
export interface GeometryReference {
  field: 'parentWall' | 'parentFloor' | 'parentRoof' | 'attachment.parent' | 'onSurface.parent' | 'landingWalls'
  targetId: string
  expectedType?: 'wall' | 'floor' | 'roof'
  coordinates: 'wall' | 'local' | 'world' | 'surface'
}
type Item = { id: string; type?: string }
export interface RelatedGeometry {
  elements?: readonly Item[]
  components?: readonly Item[]
  placements?: readonly Item[]
}

/** One field contract reused by deletion, movement, validation, cache and tree. */
export function getGeometryReferences(item: object): GeometryReference[] {
  const row = item as Record<string, unknown>
  const nested = (key: string, field: string) => (row[key] as Record<string, unknown> | undefined)?.[field]
  const candidates: Array<Omit<GeometryReference, 'targetId'> & { targetId: unknown }> = [
    { field: 'parentWall', targetId: row.parentWall, expectedType: 'wall', coordinates: 'wall' },
    { field: 'parentFloor', targetId: row.parentFloor, expectedType: 'floor', coordinates: 'local' },
    { field: 'parentRoof', targetId: row.parentRoof, expectedType: 'roof', coordinates: 'local' },
    // Dense-brick mapping is metadata today, not an inherited transform.
    { field: 'attachment.parent', targetId: nested('attachment', 'parent'), coordinates: 'world' },
    { field: 'onSurface.parent', targetId: nested('onSurface', 'parent'), coordinates: 'surface' },
  ]
  if (Array.isArray(row.landingWalls)) for (const targetId of row.landingWalls) {
    candidates.push({ field: 'landingWalls', targetId, expectedType: 'wall', coordinates: 'world' })
  }
  return candidates.filter((ref): ref is GeometryReference => typeof ref.targetId === 'string' && ref.targetId.length > 0)
}

export function buildGeometryRelationIndex(geometry: RelatedGeometry) {
  const items = new Map([...(geometry.elements || []), ...(geometry.components || []), ...(geometry.placements || [])].map(item => [item.id, item]))
  const references = new Map<string, GeometryReference[]>()
  const dependents = new Map<string, Set<string>>()
  for (const item of items.values()) {
    const refs = getGeometryReferences(item)
    references.set(item.id, refs)
    for (const ref of refs) {
      if (!dependents.has(ref.targetId)) dependents.set(ref.targetId, new Set())
      dependents.get(ref.targetId)!.add(item.id)
    }
  }
  return { items, references, dependents }
}
export type GeometryRelationIndex = ReturnType<typeof buildGeometryRelationIndex>

/** Includes the roots; cycles terminate without losing siblings or grandchildren. */
export function collectGeometryDependents(index: GeometryRelationIndex, roots: Iterable<string>): Set<string> {
  const result = new Set(roots), queue = [...result]
  for (let i = 0; i < queue.length; i++) for (const id of index.dependents.get(queue[i]) || []) {
    if (!result.has(id)) { result.add(id); queue.push(id) }
  }
  return result
}

export function validateGeometryRelations(geometry: RelatedGeometry): Array<{ elementId: string; message: string }> {
  const index = buildGeometryRelationIndex(geometry)
  const issues: Array<{ elementId: string; message: string }> = []
  for (const [id, refs] of index.references) for (const ref of refs) {
    const host = index.items.get(ref.targetId)
    if (!host) issues.push({ elementId: id, message: `${id}.${ref.field} 的宿主不存在: ${ref.targetId}` })
    else if (ref.expectedType && host.type !== ref.expectedType) issues.push({ elementId: id, message: `${id}.${ref.field} 必须引用 ${ref.expectedType}: ${ref.targetId}` })
  }
  const visited = new Set<string>(), active = new Set<string>(), reported = new Set<string>()
  const visit = (id: string) => {
    if (active.has(id)) {
      if (!reported.has(id)) issues.push({ elementId: id, message: `几何依附存在循环: ${id}` })
      reported.add(id)
      return
    }
    if (visited.has(id)) return
    active.add(id)
    for (const ref of index.references.get(id) || []) if (index.items.has(ref.targetId)) visit(ref.targetId)
    active.delete(id)
    visited.add(id)
  }
  for (const id of index.items.keys()) visit(id)
  return issues
}
