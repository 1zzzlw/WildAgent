import type {
  GeometryElement,
  OpeningParams,
  WindowComponent,
} from '../../wild-core/types'
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
  assertFrameDimensions(component, frameWidth, frameDepth)
  assertWallDepthAlignment(component, frame.wall.thickness, frameDepth, glassDepth, 'glassDepth')
  assertNonNegativeInteger(verticalMullions, 'verticalMullions')
  assertNonNegativeInteger(horizontalMullions, 'horizontalMullions')

  const [along, bottomY, normalOffset] = component.from
  const clearWidth = component.width - frameWidth * 2
  const clearHeight = component.height - frameWidth * 2
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
  if (component.interaction) {
    // 左右窗扇各自持有交互，右键命中哪一扇就只开合哪一扇。
    const sashWidth = component.width / 2
    const leftSash = createSash(`${component.id}__sash_left`, along, sashWidth)
    const rightSash = createSash(`${component.id}__sash_right`, along + sashWidth, sashWidth)
    leftSash._interaction = createOpeningInteraction(
      { ...component.interaction, hingeSide: 'left' },
      frame,
      along,
      bottomY,
      normalOffset,
      sashWidth,
      component.height,
    )
    rightSash._interaction = createOpeningInteraction(
      { ...component.interaction, hingeSide: 'right' },
      frame,
      along + sashWidth,
      bottomY,
      normalOffset,
      sashWidth,
      component.height,
    )
    sashes.push(leftSash, rightSash)
  } else {
    sashes.push(createSash(`${component.id}__opening`, along, component.width))
  }

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

  const verticalMullionRatios = new Set<number>()
  for (let index = 0; index < verticalMullions; index++) {
    verticalMullionRatios.add((index + 1) / (verticalMullions + 1))
  }
  // 双窗扇必须保留中缝；已有中央竖梃时 Set 会自动去重。
  if (component.interaction) verticalMullionRatios.add(0.5)

  for (const [index, ratio] of [...verticalMullionRatios].sort((a, b) => a - b).entries()) {
    const localAlong = along + frameWidth + clearWidth * ratio
    elements.push(createBox(
      `${component.id}__mullion_vertical_${padIndex(index)}`,
      frame.pointAt(localAlong, bottomY + component.height / 2, normalOffset),
      [frameWidth, clearHeight, frameDepth],
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
      [clearWidth, frameWidth, frameDepth],
      frame.rotationAt(along + component.width / 2),
      component.frameMaterial,
    ))
  }

  return elements
}

function padIndex(index: number): string {
  return String(index + 1).padStart(3, '0')
}
