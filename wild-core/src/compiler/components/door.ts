import type { DoorComponent, GeometryElement, OpeningInteractionSpec, OpeningParams } from '../../../types'
import type { ComponentCompileContext } from '../types'
import { assertFrameDimensions, assertNonEmptyString, assertPositive, assertVec3, assertWallDepthAlignment, createBox, createOpeningInteraction, resolveOpeningInteractionSpec, resolveStraightWallFrame, withMaterial } from './attachedToWall'
import { buildOpeningContour } from '../../primitive/geometry/openingContour'

/** 一个完整洞口，按轮廓生成门框；双开门的两扇共享操作、各绕自己的外侧铰链。 */
export function compileDoor(component: DoorComponent, context: ComponentCompileContext): GeometryElement[] {
  const frame = resolveStraightWallFrame(component, context)
  const border = component.frameWidth ?? 0.08
  const frameDepth = component.frameDepth ?? frame.wall.thickness
  const leafDepth = component.leafDepth ?? Math.min(0.04, frameDepth)
  assertFrameDimensions(component, border, frameDepth)
  assertWallDepthAlignment(component, frame.wall.thickness, frameDepth, leafDepth, 'leafDepth')
  const [along, bottom, offset] = component.from
  const style = component.openingStyle ?? 'rectangular'
  const interaction = resolveOpeningInteractionSpec('door', component.interaction)
  const double = component.doorStyle === 'double' && (!interaction || interaction.mode === 'swing')
  const width = component.width - border * 2
  const height = component.height - border
  const opening = withMaterial<OpeningParams>({ type: 'opening', id: `${component.id}__opening`, parentWall: component.parentWall, from: [...component.from], width: component.width, height: component.height, depth: leafDepth, style, _leafInset: border, _doorLeafDetail: createDoorLeafDetail(component, double, interaction) }, component.leafMaterial)
  if (double && interaction) {
    opening._leafInteractions = [0, 1].map(index => ({ ...createOpeningInteraction({ ...interaction, hingeSide: index ? 'right' : 'left' }, frame, along + border + index * width / 2, bottom, offset, width / 2, height)!, groupId: component.id }))
  } else {
    opening._interaction = createOpeningInteraction(interaction, frame, along + border, bottom, offset, width, height)
    if (opening._interaction && component.leafParts?.length) opening._interaction.groupId = component.id
  }
  const elements: GeometryElement[] = [opening]
  const partIds = new Set<string>()
  for (const part of component.leafParts ?? []) {
    assertNonEmptyString(part.id, 'leafParts.id')
    assertNonEmptyString(part.material, 'leafParts.material')
    assertVec3(part.position, 'leafParts.position')
    assertVec3(part.dimensions, 'leafParts.dimensions')
    part.dimensions.forEach(value => assertPositive(value, 'leafParts.dimensions'))
    if (partIds.has(part.id)) throw new Error(`leafParts.id 重复: ${part.id}`)
    partIds.add(part.id)
    const index = part.leaf ?? 0
    if (index !== 0 && !(double && index === 1)) throw new Error('leafParts.leaf 超出门扇范围')
    const leafWidth = width / (double ? 2 : 1)
    const [x, y, z] = part.position
    if (Math.abs(x) + part.dimensions[0] / 2 > leafWidth / 2 + 1e-6
      || y - part.dimensions[1] / 2 < -1e-6 || y + part.dimensions[1] / 2 > height + 1e-6) {
      throw new Error(`leafParts "${part.id}" 超出门扇平面范围`)
    }
    const centerAlong = along + component.width / 2
    const center = frame.pointAt(centerAlong, bottom, offset)
    const yaw = frame.rotationAt(centerAlong)
    const leafX = x + (double ? (index - .5) * leafWidth : 0)
    const position: [number, number, number] = [center[0] + Math.cos(yaw) * leafX + Math.sin(yaw) * z,
      bottom + y, center[2] - Math.sin(yaw) * leafX + Math.cos(yaw) * z]
    const element = createBox(`${component.id}__leafpart_${part.id}`, position, [...part.dimensions], yaw, part.material)
    const behavior = opening._leafInteractions?.[index] ?? opening._interaction
    if (behavior?.kind === 'opening') element._interaction = { ...behavior, groupId: component.id }
    elements.push(element)
  }
  if (!border) return elements
  const contour = buildOpeningContour(style, component.width / 2, component.height / 2, component.width, component.height)
  // 轮廓逆时针排列，跳过门槛，框向洞口内侧收进半个框宽。
  for (let i = 1; i < contour.length; i++) {
    const a = contour[i], b = contour[(i + 1) % contour.length]
    const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx,dy)
    if (length < 1e-9) continue
    const x = (a[0] + b[0]) / 2 - dy / length * border / 2
    const y = (a[1] + b[1]) / 2 + dx / length * border / 2
    const box = createBox(`${component.id}__frame_${i}`, frame.pointAt(along + component.width / 2 + x, bottom + component.height / 2 + y, offset), [length + border * 0.15, border, frameDepth], frame.rotationAt(along + component.width / 2 + x), component.frameMaterial)
    box.rotation = [0, frame.rotationAt(along + component.width / 2 + x), Math.atan2(dy,dx)]
    elements.push(box)
  }
  return elements
}

function createDoorLeafDetail(
  component: DoorComponent,
  doubleDoor: boolean,
  interaction: OpeningInteractionSpec | undefined,
): NonNullable<OpeningParams['_doorLeafDetail']> {
  let hash = 2166136261
  const variationKey = [
    component.id,
    component.width,
    component.height,
    component.frameMaterial ?? '',
    component.leafMaterial ?? '',
  ].join(':')
  for (const character of variationKey) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  const declaredRows = component.leafRows
  const rows = typeof declaredRows === 'number' && Number.isFinite(declaredRows)
    ? Math.max(1, Math.min(8, Math.round(declaredRows)))
    : (Math.abs(hash) % 2 === 0 ? 2 : 3)
  return {
    rows,
    columns: doubleDoor ? 2 : 1,
    hingeSide: interaction ? interaction.hingeSide ?? 'left' : (Math.abs(hash) % 3 === 0 ? 'right' : 'left'),
    doubleDoor,
  }
}
