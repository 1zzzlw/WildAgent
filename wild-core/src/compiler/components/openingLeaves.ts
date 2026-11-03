import type {
  GeometryElement,
  OpeningLeaf,
  OpeningElementBehavior,
  PrimitiveParams,
  Vec3
} from '../../../types'
import type { StraightWallFrame } from './attachedToWall'
export function assertLeafCount(leaves: OpeningLeaf[] | undefined, count: number): void {
  if (
    leaves !== undefined &&
    (!Array.isArray(leaves) ||
      leaves.length !== count ||
      leaves.some(l => !Array.isArray(l.parts) || !l.parts.length || l.parts.length > 1024))
  ) {
    throw new Error(`leaves must contain exactly ${count} non-empty sash definitions (1..1024 parts each)`)
  }
}
/** Compose world Y with a local XYZ Euler. Adding Euler Y is not a rigid rotation. */
function composeYaw(yaw: number, rotation: Vec3): Vec3 {
  const [x, y, z] = rotation,
    a = Math.cos(x),
    b = Math.sin(x),
    c = Math.cos(y),
    d = Math.sin(y),
    e = Math.cos(z),
    f = Math.sin(z)
  const C = Math.cos(yaw),
    S = Math.sin(yaw)
  const m11 = C * c * e + S * (b * f - a * d * e),
    m12 = -C * c * f + S * (b * e + a * d * f),
    m13 = C * d + S * a * c
  const m22 = a * e - b * d * f,
    m23 = -b * c,
    m32 = S * c * f + C * (b * e + a * d * f),
    m33 = -S * d + C * a * c
  return Math.abs(m13) < 0.9999999
    ? [Math.atan2(-m23, m33), Math.asin(Math.max(-1, Math.min(1, m13))), Math.atan2(-m12, m11)]
    : [Math.atan2(m32, m22), Math.asin(Math.max(-1, Math.min(1, m13))), 0]
}
export function compileOpeningLeaf(
  id: string,
  leaf: OpeningLeaf,
  frame: StraightWallFrame,
  along: number,
  bottom: number,
  offset: number,
  behavior?: OpeningElementBehavior,
  material?: string
): GeometryElement[] {
  const yaw = frame.rotationAt(along),
    direction = frame.directionAt(along),
    origin = frame.pointAt(along, bottom, offset)
  // Custom leaves currently require a straight host; curved frames would distort rigid sashes.
  if (frame.wall.curve) throw new Error('custom leaves require a straight parentWall')
  return leaf.parts.map((part, index): PrimitiveParams => {
    const pos = part.position ?? [0, 0, 0],
      normal = frame.normalAt(along)
    const rotation = composeYaw(yaw, part.rotation ?? [0, 0, 0])
    const result: PrimitiveParams = {
      ...part,
      type: 'primitive',
      id: `${id}__part_${String(index + 1).padStart(3, '0')}`,
      position: [
        origin[0] + direction[0] * pos[0] + normal[0] * pos[2],
        origin[1] + pos[1],
        origin[2] + direction[2] * pos[0] + normal[2] * pos[2]
      ],
      rotation,
      material: part.material ?? material
    }
    if (behavior) {
      const delta = behavior.openRotation ? behavior.openRotation[1] - behavior.closedRotation[1] : 0
      result._interaction = {
        ...behavior,
        closedPosition: result.position!,
        closedRotation: rotation,
        openRotation: behavior.openRotation ? [rotation[0], rotation[1] + delta, rotation[2]] : undefined
      }
    }
    return result
  })
}
