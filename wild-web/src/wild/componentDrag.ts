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
