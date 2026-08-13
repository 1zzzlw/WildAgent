import type {
  GeometryElement,
  OpeningElementBehavior,
  OpeningInteractionSpec,
  PrimitiveParams,
  Vec3,
  WallParams,
} from '../../wild-core/types'
import { ComponentCompileError } from '../types'
import type { ComponentCompileContext } from '../types'

export interface WallAttachedComponent {
  id: string
  parentWall: string
  from: Vec3
  width: number
  height?: number
}

export interface StraightWallFrame {
  wall: WallParams
  length: number
  rotationY: number
  pointAt: (along: number, worldY: number, normalOffset: number) => Vec3
  directionAt: (along: number) => Vec3
  normalAt: (along: number) => Vec3
  rotationAt: (along: number) => number
}

/** 计算墙体法向中背离建筑水平包围盒中心的一侧。 */
export function resolveExteriorSign(
  frame: StraightWallFrame,
  context: ComponentCompileContext,
  along: number,
): 1 | -1 {
  const walls = context.elements.filter(element => element.type === 'wall')
  const points = walls.flatMap(wall => [wall.from, wall.to])
  if (points.length === 0) return -1

  const minX = Math.min(...points.map(point => point[0]))
  const maxX = Math.max(...points.map(point => point[0]))
  const minZ = Math.min(...points.map(point => point[2]))
  const maxZ = Math.max(...points.map(point => point[2]))
  const buildingCenter = [(minX + maxX) / 2, (minZ + maxZ) / 2]
  const wallPoint = frame.pointAt(along, 0, 0)
  const normal = frame.normalAt(along)
  const outwardDot = (
    (wallPoint[0] - buildingCenter[0]) * normal[0]
    + (wallPoint[2] - buildingCenter[1]) * normal[2]
  )
  if (outwardDot > 1e-6) return 1
  if (outwardDot < -1e-6) return -1
  return -1
}

/** 把附墙悬挑组件的局部起点从墙中心线移动到墙外表面。 */
export function exteriorSurfaceOffset(
  frame: StraightWallFrame,
  context: ComponentCompileContext,
  along: number,
  normalOffset: number,
): { exteriorSign: 1 | -1; surfaceOffset: number } {
  const exteriorSign = resolveExteriorSign(frame, context, along)
  return {
    exteriorSign,
    surfaceOffset: normalOffset + exteriorSign * frame.wall.thickness / 2,
  }
}

/** 查找父墙并建立“弧长方向 + 墙体法线方向”的局部坐标系。 */
export function resolveStraightWallFrame(
  component: WallAttachedComponent,
  context: ComponentCompileContext,
): StraightWallFrame {
  assertNonEmptyString(component.id, 'id')
  assertNonEmptyString(component.parentWall, 'parentWall')
  assertVec3(component.from, 'from')
  assertPositive(component.width, 'width')
  if (component.height !== undefined) assertPositive(component.height, 'height')

  const parent = context.elements.find(element => element.id === component.parentWall)
  if (!parent) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 的 parentWall "${component.parentWall}" 不存在`,
      'parentWall',
    )
  }
  if (parent.type !== 'wall') {
    throw new ComponentCompileError(
      `组件 "${component.id}" 的 parentWall "${component.parentWall}" 不是 wall`,
      'parentWall',
    )
  }

  const wall = parent as WallParams
  const wallCurves = wall.curve
    ? (Array.isArray(wall.curve) ? wall.curve : [wall.curve])
    : []
  if (
    component.height !== undefined
    && wallCurves.some(curve => curve.type !== 'line' && curve.type !== 'arc')
  ) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 会在父墙上形成开口，当前仅支持直线墙或单段圆弧墙`,
      'parentWall',
    )
  }
  const path = sampleWallPath(wall)
  const cumulative = cumulativeLengths(path)
  const length = cumulative[cumulative.length - 1]
  if (length < 1e-6) {
    throw new ComponentCompileError(`父墙 "${wall.id}" 的水平长度为 0`, 'parentWall')
  }

  const alongStart = component.from[0]
  if (alongStart < 0 || alongStart + component.width > length + 1e-6) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 超出父墙水平范围 0–${formatNumber(length)}m`,
      'from',
    )
  }

  const wallBottom = Math.min(wall.from[1], wall.to[1])
  const wallTop = Math.max(wall.from[1], wall.to[1])
  const componentBottom = component.from[1]
  if (component.height !== undefined && (
    componentBottom < wallBottom - 1e-6
    || componentBottom + component.height > wallTop + 1e-6
  )) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 超出父墙垂直范围 ${formatNumber(wallBottom)}–${formatNumber(wallTop)}m`,
      'from',
    )
  }

  const frameAt = (along: number) => interpolatePathFrame(path, cumulative, along)
  const rotationAt = (along: number) => {
    const direction = frameAt(along).direction
    return Math.atan2(-direction[2], direction[0])
  }

  return {
    wall,
    length,
    rotationY: rotationAt(alongStart + component.width / 2),
    pointAt(along, worldY, normalOffset) {
      const { point, normal } = frameAt(along)
      return [
        point[0] + normalOffset * normal[0],
        worldY,
        point[2] + normalOffset * normal[2],
      ]
    },
    directionAt(along) {
      return frameAt(along).direction
    },
    normalAt(along) {
      return frameAt(along).normal
    },
    rotationAt,
  }
}

export function createBox(
  id: string,
  position: Vec3,
  dimensions: Vec3,
  rotationY: number,
  material?: string,
): PrimitiveParams {
  const box: PrimitiveParams = {
    type: 'primitive',
    id,
    shape: 'box',
    position,
    rotation: [0, rotationY, 0],
    dimensions,
  }
  if (material) box.material = material
  return box
}

export function createOpeningInteraction(
  interaction: OpeningInteractionSpec | undefined,
  frame: StraightWallFrame,
  along: number,
  bottomY: number,
  normalOffset: number,
  width: number,
  height: number,
): OpeningElementBehavior | undefined {
  if (!interaction) return undefined

  const hingeSide = interaction.hingeSide ?? 'left'
  const centerAlong = along + width / 2
  const closedPosition = frame.pointAt(
    centerAlong,
    bottomY + height / 2,
    normalOffset,
  )
  const rotationY = frame.rotationAt(centerAlong)
  const behavior: OpeningElementBehavior = {
    kind: 'opening',
    mode: interaction.mode,
    pivot: frame.pointAt(
      hingeSide === 'left' ? along : along + width,
      bottomY + height / 2,
      normalOffset,
    ),
    closedPosition,
    closedRotation: [0, rotationY, 0],
    initiallyOpen: interaction.initiallyOpen ?? false,
  }

  if (interaction.mode === 'swing') {
    const angle = (interaction.openAngle ?? 90) * Math.PI / 180
    behavior.openRotation = [0, rotationY + (hingeSide === 'left' ? angle : -angle), 0]
  } else {
    const direction = frame.directionAt(centerAlong)
    const distance = interaction.openDistance ?? width * 0.8
    const sign = hingeSide === 'left' ? -1 : 1
    behavior.openOffset = [
      direction[0] * distance * sign,
      0,
      direction[2] * distance * sign,
    ]
  }
  return behavior
}

export function assertFrameDimensions(
  component: WallAttachedComponent & { height: number },
  frameWidth: number,
  frameDepth: number,
): void {
  if (frameWidth < 0 || !Number.isFinite(frameWidth)) {
    throw new ComponentCompileError('frameWidth 必须为非负有限数字', 'frameWidth')
  }
  assertPositive(frameDepth, 'frameDepth')
  if (frameWidth > 0 && (frameWidth * 2 >= component.width || frameWidth >= component.height)) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 的 frameWidth 必须小于宽度的一半且小于高度`,
      'frameWidth',
    )
  }
}

/** 校验门窗深度与父墙仍有实体交叠，防止门框、门扇或玻璃悬在墙面之外。 */
export function assertWallDepthAlignment(
  component: WallAttachedComponent & { height: number },
  wallThickness: number,
  frameDepth: number,
  panelDepth: number,
  panelField: 'leafDepth' | 'glassDepth',
): void {
  assertPositive(wallThickness, 'parentWall.thickness')
  assertPositive(panelDepth, panelField)
  if (frameDepth > wallThickness + 0.12 + 1e-9) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 的 frameDepth 最多只能比父墙厚 0.12m`,
      'frameDepth',
    )
  }
  if (panelDepth > frameDepth + 1e-9) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 的 ${panelField} 不能大于 frameDepth`,
      panelField,
    )
  }

  const normalOffset = Math.abs(component.from[2])
  if (normalOffset >= (wallThickness + frameDepth) / 2 - 1e-6) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 的门窗框深度与父墙没有实体交叠`,
      'from',
    )
  }
  if (normalOffset >= (wallThickness + panelDepth) / 2 - 1e-6) {
    throw new ComponentCompileError(
      `组件 "${component.id}" 的 ${panelField} 与父墙没有实体交叠`,
      'from',
    )
  }
}

function sampleWallPath(wall: WallParams): Vec3[] {
  const curves = wall.curve
    ? (Array.isArray(wall.curve) ? wall.curve : [wall.curve])
    : []
  if (curves.length === 0 || curves.every(curve => curve.type === 'line')) {
    return [
      [wall.from[0], 0, wall.from[2]],
      [wall.to[0], 0, wall.to[2]],
    ]
  }
  if (curves.length !== 1) {
    throw new ComponentCompileError(
      `父墙 "${wall.id}" 的复合曲线路径暂不支持组合构件依附`,
      'parentWall',
    )
  }

  const curve = curves[0]
  const segments = Math.max(8, ('segments' in curve ? curve.segments : undefined) ?? 24)
  const points: Vec3[] = []
  if (curve.type === 'arc') {
    const start = Math.atan2(
      wall.from[2] - curve.center[2],
      wall.from[0] - curve.center[0],
    )
    const radius = Math.hypot(
      wall.from[0] - curve.center[0],
      wall.from[2] - curve.center[2],
    )
    const sweep = curve.sweep * Math.PI / 180
    for (let index = 0; index <= segments; index++) {
      const angle = start + sweep * index / segments
      points.push([
        curve.center[0] + Math.cos(angle) * radius,
        0,
        curve.center[2] + Math.sin(angle) * radius,
      ])
    }
    return points
  }
  if (curve.type === 'ellipse') {
    const start = (curve.startAngle ?? 0) * Math.PI / 180
    const sweep = (curve.sweep ?? 360) * Math.PI / 180
    for (let index = 0; index <= segments; index++) {
      const angle = start + sweep * index / segments
      points.push([
        curve.center[0] + Math.cos(angle) * curve.radiusX,
        0,
        curve.center[2] + Math.sin(angle) * curve.radiusZ,
      ])
    }
    return points
  }
  if (curve.type === 'catenary') {
    const dx = wall.to[0] - wall.from[0]
    const dz = wall.to[2] - wall.from[2]
    const length = Math.hypot(dx, dz)
    if (length < 1e-6) return [[wall.from[0], 0, wall.from[2]]]
    const dirX = dx / length
    const dirZ = dz / length
    for (let index = 0; index <= segments; index++) {
      const ratio = index / segments
      const rise = curve.rise * Math.sin(ratio * Math.PI)
      points.push([
        wall.from[0] + dx * ratio - dirZ * rise,
        0,
        wall.from[2] + dz * ratio + dirX * rise,
      ])
    }
    return points
  }
  return [
    [wall.from[0], 0, wall.from[2]],
    [wall.to[0], 0, wall.to[2]],
  ]
}

function cumulativeLengths(path: Vec3[]): number[] {
  const lengths = [0]
  for (let index = 1; index < path.length; index++) {
    lengths.push(lengths[index - 1] + Math.hypot(
      path[index][0] - path[index - 1][0],
      path[index][2] - path[index - 1][2],
    ))
  }
  return lengths
}

function interpolatePathFrame(
  path: Vec3[],
  cumulative: number[],
  along: number,
): { point: Vec3; direction: Vec3; normal: Vec3 } {
  const distance = Math.max(0, Math.min(along, cumulative[cumulative.length - 1]))
  let segment = cumulative.findIndex((value, index) => (
    index > 0 && distance <= value + 1e-9
  ))
  if (segment < 1) segment = cumulative.length - 1
  const start = path[segment - 1]
  const end = path[segment]
  const segmentLength = cumulative[segment] - cumulative[segment - 1]
  const ratio = segmentLength > 1e-9
    ? (distance - cumulative[segment - 1]) / segmentLength
    : 0
  const dx = end[0] - start[0]
  const dz = end[2] - start[2]
  const horizontalLength = Math.hypot(dx, dz) || 1
  const direction: Vec3 = [dx / horizontalLength, 0, dz / horizontalLength]
  const normal: Vec3 = [-direction[2], 0, direction[0]]
  return {
    point: [
      start[0] + dx * ratio,
      0,
      start[2] + dz * ratio,
    ],
    direction,
    normal,
  }
}

export function assertNonNegativeInteger(
  value: number,
  field: string,
  maximum = 32,
): void {
  if (!Number.isInteger(value) || value < 0 || value > maximum) {
    throw new ComponentCompileError(
      `${field} 必须是 0–${maximum} 的整数`,
      field,
    )
  }
}

export function assertPositive(value: number, field: string): void {
  if (!Number.isFinite(value) || value <= 0) {
    throw new ComponentCompileError(`${field} 必须是正有限数字`, field)
  }
}

export function assertVec3(value: Vec3, field: string): void {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(Number.isFinite)) {
    throw new ComponentCompileError(`${field} 必须是三个有限数字组成的数组`, field)
  }
}

export function assertNonEmptyString(value: string, field: string): void {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new ComponentCompileError(`${field} 必须是非空字符串`, field)
  }
}

export function withMaterial<T extends GeometryElement>(
  element: T,
  material?: string,
): T {
  if (material) (element as T & { material?: string }).material = material
  return element
}

function formatNumber(value: number): string {
  return String(Math.round(value * 1000) / 1000)
}
