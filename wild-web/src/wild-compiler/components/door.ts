import type {
  DoorComponent,
  GeometryElement,
  OpeningParams,
} from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import {
  assertFrameDimensions,
  createBox,
  createOpeningInteraction,
  resolveStraightWallFrame,
  withMaterial,
} from './attachedToWall'

/** 将门展开为一个墙洞覆盖面与门框 primitive。
 *
 * 支持参数：
 * - openingStyle: "rectangular"（默认）或 "arched"（拱形门洞）
 * - doorStyle: "single"（默认，单扇）或 "double"（双开：一个宽洞口+四段框，无中框）
 */
export function compileDoor(
  component: DoorComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  const frame = resolveStraightWallFrame(component, context)
  const openingStyle = component.openingStyle ?? 'rectangular'
  const doorStyle = component.doorStyle ?? 'single'

  if (doorStyle === 'double') {
    return compileDoubleDoor(component, frame, openingStyle)
  }
  return compileSingleDoor(component, frame, openingStyle)
}

/** 单扇门：1 个 opening + 3 段门框（左/右/顶）。 */
function compileSingleDoor(
  component: DoorComponent,
  frame: ReturnType<typeof resolveStraightWallFrame>,
  openingStyle: 'rectangular' | 'arched',
): GeometryElement[] {
  const frameWidth = component.frameWidth ?? 0.08
  const frameDepth = component.frameDepth ?? frame.wall.thickness + 0.04
  assertFrameDimensions(component, frameWidth, frameDepth)

  const [along, bottomY, normalOffset] = component.from
  const opening = withMaterial<OpeningParams>({
    type: 'opening',
    id: `${component.id}__opening`,
    parentWall: component.parentWall,
    from: [...component.from],
    width: component.width,
    height: component.height,
    style: openingStyle,
  }, component.leafMaterial)
  opening._interaction = createOpeningInteraction(
    component.interaction,
    frame,
    along,
    bottomY,
    normalOffset,
    component.width,
    component.height,
  )

  return [
    opening,
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
      `${component.id}__frame_top`,
      frame.pointAt(along + component.width / 2, bottomY + component.height - frameWidth / 2, normalOffset),
      [component.width - frameWidth * 2, frameWidth, frameDepth],
      frame.rotationAt(along + component.width / 2),
      component.frameMaterial,
    ),
  ]
}

/** 双开门：1 个宽 opening + 4 段门框（左外/右外/左扇顶/右扇顶），无双扇之间的中竖框。 */
function compileDoubleDoor(
  component: DoorComponent,
  frame: ReturnType<typeof resolveStraightWallFrame>,
  openingStyle: 'rectangular' | 'arched',
): GeometryElement[] {
  const frameWidth = component.frameWidth ?? 0.08
  const frameDepth = component.frameDepth ?? frame.wall.thickness + 0.04
  // 双开门的内侧框可设为 0（两扇之间无缝），但仍需验证外侧框尺寸
  const halfWidth = component.width / 2

  const [along, bottomY, normalOffset] = component.from
  const opening = withMaterial<OpeningParams>({
    type: 'opening',
    id: `${component.id}__opening`,
    parentWall: component.parentWall,
    from: [...component.from],
    width: component.width,
    height: component.height,
    style: openingStyle,
  }, component.leafMaterial)

  // 双开门：左扇铰链在左，右扇铰链在右
  opening._interaction = createOpeningInteraction(
    component.interaction,
    frame,
    along,
    bottomY,
    normalOffset,
    component.width,
    component.height,
  )

  const elements: GeometryElement[] = [opening]

  // 左侧外框（仅在 frameWidth > 0 时生成）
  if (frameWidth > 0) {
    elements.push(createBox(
      `${component.id}__frame_left_outer`,
      frame.pointAt(along + frameWidth / 2, bottomY + component.height / 2, normalOffset),
      [frameWidth, component.height, frameDepth],
      frame.rotationAt(along + frameWidth / 2),
      component.frameMaterial,
    ))
  }

  // 右侧外框（仅在 frameWidth > 0 时生成）
  if (frameWidth > 0) {
    elements.push(createBox(
      `${component.id}__frame_right_outer`,
      frame.pointAt(along + component.width - frameWidth / 2, bottomY + component.height / 2, normalOffset),
      [frameWidth, component.height, frameDepth],
      frame.rotationAt(along + component.width - frameWidth / 2),
      component.frameMaterial,
    ))
  }

  // 左扇顶框
  elements.push(createBox(
    `${component.id}__frame_top_left`,
    frame.pointAt(along + halfWidth / 2, bottomY + component.height - frameWidth / 2, normalOffset),
    [halfWidth - frameWidth, frameWidth, frameDepth],
    frame.rotationAt(along + halfWidth / 2),
    component.frameMaterial,
  ))

  // 右扇顶框
  elements.push(createBox(
    `${component.id}__frame_top_right`,
    frame.pointAt(along + halfWidth + halfWidth / 2, bottomY + component.height - frameWidth / 2, normalOffset),
    [halfWidth - frameWidth, frameWidth, frameDepth],
    frame.rotationAt(along + halfWidth + halfWidth / 2),
    component.frameMaterial,
  ))

  return elements
}
