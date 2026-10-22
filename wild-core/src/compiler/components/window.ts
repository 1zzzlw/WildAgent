import type {
  GeometryElement,
  OpeningParams,
  WindowComponent,
} from '../../../types'
import type { ComponentCompileContext } from '../types'
import {
  assertFrameDimensions,
  assertWallDepthAlignment,
  assertNonNegativeInteger,
  createBox,
  createOpeningInteraction,
  resolveStraightWallFrame,
  withMaterial,
} from './attachedToWall'

/** 将窗展开为玻璃窗扇、四边窗框和可选水平/竖直窗棂。 */
export function compileWindow(
  component: WindowComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  const frame = resolveStraightWallFrame(component, context)
  const frameWidth = component.frameWidth ?? 0.06
  const frameDepth = component.frameDepth ?? frame.wall.thickness
  const glassDepth = component.glassDepth ?? Math.min(0.012, frameDepth)
  const verticalMullions = component.verticalMullions ?? 0
  const horizontalMullions = component.horizontalMullions ?? 0
  const mullionWidth = component.mullionWidth ?? Math.min(frameWidth, 0.02)
  assertFrameDimensions(component, frameWidth, frameDepth)
  assertWallDepthAlignment(component, frame.wall.thickness, frameDepth, glassDepth, 'glassDepth')
  assertNonNegativeInteger(verticalMullions, 'verticalMullions')
  assertNonNegativeInteger(horizontalMullions, 'horizontalMullions')

  const [along, bottomY, normalOffset] = component.from
  const clearWidth = component.width - frameWidth * 2
  const clearHeight = component.height - frameWidth * 2
  if (clearWidth <= 0 || clearHeight <= 0) throw new Error('frameWidth must leave a positive clear window area')
  const verticalMullionRatios = new Set<number>()
  for (let index = 0; index < verticalMullions; index++) {
    verticalMullionRatios.add((index + 1) / (verticalMullions + 1))
  }
  const ratios = [0, ...[...verticalMullionRatios].sort((a, b) => a - b), 1]
  const verticalSpacing = Math.min(...ratios.slice(1).map((r, i) => (r - ratios[i]) * clearWidth))
  if (verticalMullionRatios.size || horizontalMullions) {
    if (!Number.isFinite(mullionWidth) || mullionWidth <= 0
      || (verticalMullionRatios.size && mullionWidth >= verticalSpacing)
      || (horizontalMullions && mullionWidth >= clearHeight / (horizontalMullions + 1))) {
      throw new Error('mullionWidth must leave clear space between window bars')
    }
  }
  const createSash = (id: string, sashAlong: number, sashWidth: number): OpeningParams => (
    withMaterial<OpeningParams>({
      type: 'opening',
      id,
      parentWall: component.parentWall,
      from: [sashAlong, bottomY, normalOffset],
      width: sashWidth,
      height: component.height,
      depth: glassDepth,
      style: 'rectangular',
    }, component.glassMaterial)
  )

  const sashes: OpeningParams[] = []
  if (!component.interaction) sashes.push(createSash(`${component.id}__opening`, along, component.width))

  const elements: GeometryElement[] = [
    ...sashes,
    createBox(
      `${component.id}__frame_left`,
      frame.pointAt(along + frameWidth / 2, bottomY + component.height / 2, normalOffset),
      [frameWidth, component.height, frameDepth],
      frame.rotationAt(along + frameWidth / 2),
      component.frameMaterial,
    ),
    createBox(
      `${component.id}__frame_right`,
      frame.pointAt(along + component.width - frameWidth / 2, bottomY + component.height / 2, normalOffset),
      [frameWidth, component.height, frameDepth],
      frame.rotationAt(along + component.width - frameWidth / 2),
      component.frameMaterial,
    ),
    createBox(
      `${component.id}__frame_bottom`,
      frame.pointAt(along + component.width / 2, bottomY + frameWidth / 2, normalOffset),
      [clearWidth, frameWidth, frameDepth],
      frame.rotationAt(along + component.width / 2),
      component.frameMaterial,
    ),
    createBox(
      `${component.id}__frame_top`,
      frame.pointAt(along + component.width / 2, bottomY + component.height - frameWidth / 2, normalOffset),
      [clearWidth, frameWidth, frameDepth],
      frame.rotationAt(along + component.width / 2),
      component.frameMaterial,
    ),
  ]

  if (component.interaction) {
    elements.push(...compileMovingSashes(component, frame, frameWidth, frameDepth, glassDepth, mullionWidth))
    return elements
  }

  for (const [index, ratio] of [...verticalMullionRatios].sort((a, b) => a - b).entries()) {
    const localAlong = along + frameWidth + clearWidth * ratio
    elements.push(createBox(
      `${component.id}__mullion_vertical_${padIndex(index)}`,
      frame.pointAt(localAlong, bottomY + component.height / 2, normalOffset),
      [mullionWidth, clearHeight, frameDepth],
      frame.rotationAt(localAlong),
      component.frameMaterial,
    ))
  }

  for (let index = 0; index < horizontalMullions; index++) {
    const worldY = bottomY + frameWidth
      + clearHeight * (index + 1) / (horizontalMullions + 1)
    elements.push(createBox(
      `${component.id}__mullion_horizontal_${padIndex(index)}`,
      frame.pointAt(along + component.width / 2, worldY, normalOffset),
      [clearWidth, mullionWidth, frameDepth],
      frame.rotationAt(along + component.width / 2),
      component.frameMaterial,
    ))
  }

  return elements
}

function padIndex(index: number): string {
  return String(index + 1).padStart(3, '0')
}

/** 整个洞口裁墙，窗扇在净空内沿独立轨道移动；玻璃、窗框和窗棂共享交互。 */
function compileMovingSashes(
  component: WindowComponent,
  frame: ReturnType<typeof resolveStraightWallFrame>,
  border: number, depth: number, glassDepth: number, mullion: number,
): GeometryElement[] {
  const interaction = component.interaction!
  const [along, bottom, offset] = component.from
  const width = component.width - border * 2
  const height = component.height - border * 2
  const stacked = interaction.mode === 'lift'
  const tracked = interaction.mode !== 'swing'
  const sashDepth = tracked ? depth * 0.42 : depth * 0.7
  if (tracked && glassDepth > sashDepth) throw new Error('glassDepth 过大，无法在 frameDepth 内容纳两条独立窗扇轨道')
  const sashWidth = stacked ? width : width / 2
  const sashHeight = stacked ? height / 2 : height
  const sashBorder = Math.min(Math.max(border * 0.65, 0.012), 0.035, sashWidth * 0.15, sashHeight * 0.15)
  const cutout: OpeningParams = { type: 'opening', id: `${component.id}__cutout`, parentWall: component.parentWall, from: [...component.from], width: component.width, height: component.height, style: 'rectangular', _cutoutOnly: true }
  const elements: GeometryElement[] = [cutout]
  for (let index = 0; index < 2; index++) {
    const id = `${component.id}__sash_${stacked ? (index ? 'top' : 'bottom') : (index ? 'right' : 'left')}`
    const x = along + border + (stacked ? 0 : index * sashWidth)
    const y = bottom + border + (stacked ? index * sashHeight : 0)
    const z = offset + (tracked ? (index ? 1 : -1) * depth * 0.25 : 0)
    const behavior = createOpeningInteraction({ ...interaction, hingeSide: index ? 'right' : 'left' }, frame, x, y, z, sashWidth, sashHeight)!
    behavior.groupId = id
    if (tracked) {
      const limit = stacked ? height - sashHeight : width - sashWidth
      const travel = Math.max(0, Math.min(interaction.openDistance ?? limit, limit)) * (index ? -1 : 1)
      const direction = frame.directionAt(x + sashWidth / 2)
      behavior.openOffset = stacked ? [0, travel, 0] : [direction[0] * travel, 0, direction[2] * travel]
    }
    elements.push(withMaterial<OpeningParams>({ type: 'opening', id, parentWall: component.parentWall, from: [x, y, z], width: sashWidth, height: sashHeight, depth: glassDepth, style: 'rectangular', _interaction: behavior, _skipWallCutout: true }, component.glassMaterial))
    const bar = (suffix: string, cx: number, cy: number, w: number, h: number) => {
      const box = createBox(`${id}__${suffix}`, frame.pointAt(cx, cy, z), [w, h, sashDepth], frame.rotationAt(cx), component.frameMaterial)
      elements.push(Object.assign(box, { _interaction: behavior }))
    }
    bar('left', x + sashBorder / 2, y + sashHeight / 2, sashBorder, sashHeight)
    bar('right', x + sashWidth - sashBorder / 2, y + sashHeight / 2, sashBorder, sashHeight)
    bar('bottom', x + sashWidth / 2, y + sashBorder / 2, sashWidth - 2 * sashBorder, sashBorder)
    bar('top', x + sashWidth / 2, y + sashHeight - sashBorder / 2, sashWidth - 2 * sashBorder, sashBorder)
    for (let i = 0; i < (component.verticalMullions ?? 0); i++) bar(`vertical_${i}`, x + sashWidth * (i + 1) / ((component.verticalMullions ?? 0) + 1), y + sashHeight / 2, mullion, sashHeight - 2 * sashBorder)
    for (let i = 0; i < (component.horizontalMullions ?? 0); i++) bar(`horizontal_${i}`, x + sashWidth / 2, y + sashHeight * (i + 1) / ((component.horizontalMullions ?? 0) + 1), sashWidth - 2 * sashBorder, mullion)
  }
  return elements
}
