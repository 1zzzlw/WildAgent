import type { BayWindowComponent, GeometryElement, WindowComponent } from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import { assertFrameDimensions, assertPositive, createBox, resolveStraightWallFrame } from './attachedToWall'
import { compileWindow } from './window'

/** 将凸窗展开为墙洞、基础窗框、挑板和投影窗体。 */
export function compileBayWindow(
  component: BayWindowComponent,
  context: ComponentCompileContext,
): GeometryElement[] {
  const frame = resolveStraightWallFrame(component, context)
  assertPositive(component.projectionDepth, 'projectionDepth')
  const frameWidth = component.frameWidth ?? 0.06
  const frameDepth = component.frameDepth ?? 0.05
  assertFrameDimensions(component, frameWidth, frameDepth)
  const windowBase: WindowComponent = {
    ...component,
    type: 'window',
  }
  const elements = compileWindow(windowBase, context)
  const [along, bottomY, normalOffset] = component.from
  const centerAlong = along + component.width / 2
  const clearWidth = component.width - frameWidth * 2
  const clearHeight = component.height - frameWidth * 2
  const frontOffset = normalOffset + component.projectionDepth
  const rotation = frame.rotationAt(centerAlong)

  elements.push(
    createBox(
      `${component.id}__projection_bottom`,
      frame.pointAt(centerAlong, bottomY + frameWidth / 2, normalOffset + component.projectionDepth / 2),
      [component.width, frameWidth, component.projectionDepth],
      rotation,
      component.frameMaterial,
    ),
    createBox(
      `${component.id}__projection_top`,
      frame.pointAt(centerAlong, bottomY + component.height - frameWidth / 2, normalOffset + component.projectionDepth / 2),
      [component.width, frameWidth, component.projectionDepth],
      rotation,
      component.frameMaterial,
    ),
    createBox(
      `${component.id}__front_glass`,
      frame.pointAt(centerAlong, bottomY + component.height / 2, frontOffset),
      [clearWidth, clearHeight, frameDepth],
      rotation,
      component.glassMaterial,
    ),
    createBox(
      `${component.id}__side_left`,
      frame.pointAt(along + frameWidth / 2, bottomY + component.height / 2, normalOffset + component.projectionDepth / 2),
      [frameWidth, clearHeight, component.projectionDepth],
      frame.rotationAt(along),
      component.glassMaterial,
    ),
    createBox(
      `${component.id}__side_right`,
      frame.pointAt(along + component.width - frameWidth / 2, bottomY + component.height / 2, normalOffset + component.projectionDepth / 2),
      [frameWidth, clearHeight, component.projectionDepth],
      frame.rotationAt(along + component.width),
      component.glassMaterial,
    ),
  )
  return elements
}
