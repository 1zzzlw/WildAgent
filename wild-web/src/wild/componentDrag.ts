import type {
  ComponentSpec,
  Vec3,
} from '../wild-core/types'

/** 将视口中的世界坐标位移转换为组件蓝图字段更新。 */
export function createComponentTranslationChanges(
  component: ComponentSpec,
  delta: Vec3,
  elements: readonly unknown[],
): Record<string, unknown> {
  if (
    component.type === 'door'
    || component.type === 'window'
    || component.type === 'canopy'
    || component.type === 'balcony'
    || component.type === 'bay_window'
  ) {
    return { from: translateWallAttachment(component.from, component.parentWall, delta, elements) }
  }
  if (component.type === 'railing' || component.type === 'cornice') {
    return { path: component.path.map(point => add(point, delta)) }
  }
  if (component.type === 'ramp') {
    return { from: add(component.from, delta), to: add(component.to, delta) }
  }
  return { position: add(component.position, delta) }
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
