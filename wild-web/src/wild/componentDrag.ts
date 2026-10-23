import type {
  ComponentSpec,
  GeometryElement,
  Vec3,
  WallParams,
  CurveSegment,
} from 'wild-core/types'
import { resolveSpatialRelations } from 'wild-core/primitive'
import { getComponentCompiler, translateWallCoordinates, translateRoofAttachmentPoints } from 'wild-core/compiler'
import { buildGeometryRelationIndex, collectGeometryDependents, getGeometryReferences } from 'wild-core/relationships'
import type { Blueprint } from '../types/blueprint'
import type { SceneOperation } from '../types/scenePatch'

/** 将视口中的世界坐标位移转换为组件蓝图字段更新。 */
export function createComponentTranslationChanges(
  component: ComponentSpec | GeometryElement,
  delta: Vec3,
  elements: readonly unknown[],
): Record<string, unknown> {
  const editing = getComponentCompiler(component.type)?.editing
  const reference = getGeometryReferences(component)[0]
  if (reference?.coordinates === 'wall' && 'from' in component) {
    const host = elements.find(item => isRecord(item) && item.id === reference.targetId) as WallParams | undefined
    if (component.type === 'opening' && host?.curve
      && (Array.isArray(host.curve) ? host.curve : [host.curve]).some(curve => curve.type !== 'line')) {
      throw new Error('原生曲墙开口暂不支持直接拖动；请编辑沿墙参数或移动宿主墙')
    }
    return { from: translateWallAttachment(component.from, reference.targetId, delta, elements) }
  }
  if (reference?.field === 'parentRoof') {
    const item = component as { path?: Vec3[]; position?: Vec3 }
    const points = item.path || [item.position || [0, 0, 0]]
    const translated = translateRoofAttachmentPoints(reference.targetId, points, delta, { elements: elements as GeometryElement[], components: [] })
    return item.path ? { path: translated } : { position: translated[0] }
  }
  if (editing?.translation === 'path' && 'path' in component) {
    return { path: component.path!.map(point => add(point, delta)) }
  }
  if (editing?.translation === 'fromTo' || ['wall', 'floor', 'beam', 'stair'].includes(component.type)) {
    const item = component as GeometryElement & { from: Vec3; to?: Vec3 }
    const curve = component.type === 'wall' ? component.curve : undefined
    return { from: add(item.from, delta), ...(item.to ? { to: add(item.to, delta) } : {}),
      ...(curve ? { curve: translateWallCurve(curve, delta) } : {}),
    }
  }
  if (component.type === 'column') return { base: add(component.base, delta) }
  if (component.type === 'dense_brick') return { origin: add(component.origin, delta) }
  if (editing?.translation === 'lightBody' && component.type === 'light' && component.body) {
    return { position: add(component.position, delta), body: component.body.map(part => ({
      ...part,
      ...(part.position ? { position: add(part.position, delta) } : {}),
      ...(part.shape === 'profile_sweep' && part.path ? { path: part.path.map(p => add(p, delta)) } : {}),
    })) }
  }
  let position = (component as { position?: Vec3 }).position
  if (component.type === 'roof' && !position) {
    const resolved = resolveSpatialRelations(JSON.parse(JSON.stringify(elements)))
      .find(element => element.id === component.id)
    position = (resolved as { position?: Vec3 } | undefined)?.position
  }
  return { position: add(position || [0, 0, 0], delta) }
}

/** 原生元素与组合构件共用一次可撤销修改；移动墙时保留附属门窗的局部坐标。 */
export function createGeometryTranslationOperations(
  blueprint: Blueprint,
  selectedIds: readonly string[],
  delta: Vec3,
): SceneOperation[] {
  const components = blueprint.geometry.components || []
  const elements = blueprint.geometry.elements as unknown as GeometryElement[]
  const componentIds = new Set(components.map(item => item.id))
  const items = new Map<string, ComponentSpec | GeometryElement>([...elements, ...components].map(item => [item.id, item]))
  const affected = getGeometryTranslationIds(blueprint, selectedIds)
  return [...affected].filter(id => items.has(id)).flatMap(id => {
    const item = items.get(id)!
    const inherited = getGeometryReferences(item).find(ref => affected.has(ref.targetId))
    if (inherited?.coordinates === 'surface' || inherited?.field === 'parentFloor') return []
    const changes = inherited?.coordinates === 'wall' && 'from' in item
      ? { from: [item.from[0], item.from[1] + delta[1], item.from[2]] }
      : createComponentTranslationChanges(item, inherited?.field === 'parentRoof' ? [0, 0, 0] : delta, elements)
    return [{ op: componentIds.has(id) ? 'update_component' as const : 'update_element' as const, id, changes }]
  })
}

/** Preview and commit share the same transitive affected set, even for unchanged local fields. */
export function getGeometryTranslationIds(blueprint: Blueprint, selectedIds: readonly string[]): Set<string> {
  const index = buildGeometryRelationIndex(blueprint.geometry)
  const movable = selectedIds.filter(id => {
    const item = index.items.get(id)
    return item && (item as { draggable?: boolean }).draggable !== false
  })
  return collectGeometryDependents(index, movable)
}

function translateWallCurve(curve: NonNullable<WallParams['curve']>, delta: Vec3): NonNullable<WallParams['curve']> {
  const translate = (part: CurveSegment) => 'center' in part ? { ...part, center: add(part.center, delta) } : part
  return Array.isArray(curve) ? curve.map(translate) : translate(curve)
}

/** 绕构件自身中心水平旋转 90°，只改写 WILD 实际支持的朝向字段。 */
export function createGeometryRotationOperations(
  blueprint: Blueprint,
  selectedIds: readonly string[],
): SceneOperation[] {
  if (selectedIds.length !== 1) return []
  const id = selectedIds[0]
  const component = blueprint.geometry.components?.find(item => item.id === id)
  const element = blueprint.geometry.elements.find(item => item.id === id) as GeometryElement | undefined
  const item = component || element
  if (!item || (component && component.draggable === false)) return []
  const relations = buildGeometryRelationIndex(blueprint.geometry)
  const attached = collectGeometryDependents(relations, [id])
  if (attached.size > 1 && (item.type === 'floor' || item.type === 'roof')) return []
  if ([...attached].some(child => (relations.references.get(child) || []).some(ref => attached.has(ref.targetId) && ref.coordinates === 'world'))) return []
  let changes: Record<string, unknown>
  if (item.type === 'primitive' || item.type === 'furniture') {
    const current = item.rotation || [0, 0, 0]
    changes = { rotation: [current[0], current[1] + Math.PI / 2, current[2]] }
  } else if (item.type === 'roof') {
    changes = {
      span: item.depth,
      depth: item.span,
      ...(item.roofType === 'gable'
        ? { ridgeAxis: item.ridgeAxis === 'x' ? 'z' : 'x' }
        : {}),
    }
  } else if (item.type === 'railing' || item.type === 'cornice') {
    if (!item.path.length) return []
    const xs = item.path.map(point => point[0])
    const zs = item.path.map(point => point[2])
    const center: Vec3 = [(Math.min(...xs) + Math.max(...xs)) / 2, 0, (Math.min(...zs) + Math.max(...zs)) / 2]
    changes = { path: item.path.map(point => rotateQuarter(point, center)) }
  } else if (item.type === 'wall' || item.type === 'beam' || item.type === 'stair'
    || item.type === 'floor' || item.type === 'ramp') {
    if (('curve' in item && item.curve && (Array.isArray(item.curve) || item.curve.type !== 'line'))
      || (item.type === 'floor' && (!item.to || item.shape === 'circle'))) return []
    const from = item.from
    const to = item.to
    if (!to) return []
    const center: Vec3 = [(from[0] + to[0]) / 2, 0, (from[2] + to[2]) / 2]
    const rotatedFrom = rotateQuarter(from, center)
    const rotatedTo = rotateQuarter(to, center)
    changes = item.type === 'floor'
      ? {
          from: [Math.min(rotatedFrom[0], rotatedTo[0]), from[1], Math.min(rotatedFrom[2], rotatedTo[2])],
          to: [Math.max(rotatedFrom[0], rotatedTo[0]), to[1], Math.max(rotatedFrom[2], rotatedTo[2])],
        }
      : { from: rotatedFrom, to: rotatedTo }
  } else {
    return []
  }
  return [{ op: component ? 'update_component' : 'update_element', id, changes }]
}

function rotateQuarter(point: Vec3, center: Vec3): Vec3 {
  return [center[0] + point[2] - center[2], point[1], center[2] - point[0] + center[0]]
}

function translateWallAttachment(
  from: Vec3,
  parentWall: string,
  delta: Vec3,
  elements: readonly unknown[],
): Vec3 {
  const wall = elements.find(element => (
    isRecord(element) && element.id === parentWall && element.type === 'wall'
  ))
  if (
    !isRecord(wall)
    || !isVec3(wall.from)
    || !isVec3(wall.to)
  ) return [from[0], from[1] + delta[1], from[2]]
  return translateWallCoordinates(wall as unknown as WallParams, from, delta)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isVec3(value: unknown): value is Vec3 {
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite)
}

function add(left: Vec3, right: Vec3): Vec3 {
  return [left[0] + right[0], left[1] + right[1], left[2] + right[2]]
}
