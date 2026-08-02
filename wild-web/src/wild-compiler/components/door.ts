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

/** 将静态门展开为一个墙洞覆盖面和三段门框。 */
export function compileDoor(
  component: DoorComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  const frame = resolveStraightWallFrame(component, context)
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
    style: 'rectangular',
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
