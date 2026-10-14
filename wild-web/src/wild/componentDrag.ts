import type {
  ComponentSpec,
  GeometryElement,
  Vec3,
} from 'wild-core/types'
import { resolveSpatialRelations } from 'wild-core/primitive'
import type { Blueprint } from '../types/blueprint'
import type { SceneOperation } from '../types/scenePatch'

/** 将视口中的世界坐标位移转换为组件蓝图字段更新。 */
export function createComponentTranslationChanges(
  component: ComponentSpec | GeometryElement,
  delta: Vec3,
  elements: readonly unknown[],
): Record<string, unknown> {
  if (
    component.type === 'door'
    || component.type === 'window'
    || component.type === 'canopy'
    || component.type === 'balcony'
    || component.type === 'bay_window'
    || component.type === 'opening'
  ) {
    return { from: translateWallAttachment(component.from, component.parentWall, delta, elements) }
  }
  if (component.type === 'railing' || component.type === 'cornice') {
    return { path: component.path.map(point => add(point, delta)) }
  }
  if (['ramp', 'wall', 'floor', 'beam', 'stair'].includes(component.type)) {
    const item = component as GeometryElement & { from: Vec3; to?: Vec3 }
    return { from: add(item.from, delta), ...(item.to ? { to: add(item.to, delta) } : {}) }
  }
  if (component.type === 'column') return { base: add(component.base, delta) }
  if (component.type === 'dense_brick') return { origin: add(component.origin, delta) }
  if (component.type === 'light' && component.body) {
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
  const movable = selectedIds.filter(id => items.has(id)
    && (!componentIds.has(id) || (items.get(id) as ComponentSpec).draggable !== false))
  const walls = new Set(movable.filter(id => items.get(id)?.type === 'wall'))
  const affected = new Set(movable)
  for (const item of items.values()) {
    if ('parentWall' in item && walls.has(item.parentWall)) affected.add(item.id)
  }
  return [...affected].map(id => {
    const item = items.get(id)!
    const changes = 'parentWall' in item && walls.has(item.parentWall)
      ? { from: [item.from[0], item.from[1] + delta[1], item.from[2]] }
      : createComponentTranslationChanges(item, delta, elements)
    return { op: componentIds.has(id) ? 'update_component' : 'update_element', id, changes }
  })
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
  const dx = wall.to[0] - wall.from[0]
  const dz = wall.to[2] - wall.from[2]
  const length = Math.hypot(dx, dz) || 1
  const directionX = dx / length
  const directionZ = dz / length
  const normalX = -directionZ
  const normalZ = directionX
  return [
    from[0] + delta[0] * directionX + delta[2] * directionZ,
    from[1] + delta[1],
    from[2] + delta[0] * normalX + delta[2] * normalZ,
  ]
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
