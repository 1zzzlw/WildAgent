import type { BayWindowComponent, GeometryElement, OpeningElementBehavior, Vec3, WindowComponent } from '../../../types'
import type { ComponentCompileContext } from '../types'
import { assertFrameDimensions, assertPositive, createBox, resolveOpeningInteractionSpec, resolveStraightWallFrame } from './attachedToWall'
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
  const interaction = resolveOpeningInteractionSpec('bay_window', component.interaction)
  const windowBase: WindowComponent = {
    ...component,
    type: 'window',
    frameDepth,
    interaction: interaction ?? false,
  }
  const baseElements = compileWindow(windowBase, context)
  const [along, bottomY, normalOffset] = component.from
  const centerAlong = along + component.width / 2
  const clearWidth = component.width - frameWidth * 2
  const clearHeight = component.height - frameWidth * 2
  const frontOffset = normalOffset + component.projectionDepth
  const rotation = frame.rotationAt(centerAlong)
  const baseCenter = frame.pointAt(centerAlong, bottomY, normalOffset)
  const frontCenter = frame.pointAt(centerAlong, bottomY, frontOffset)
  const project = (point: Vec3): Vec3 => [
    point[0] + frontCenter[0] - baseCenter[0],
    point[1],
    point[2] + frontCenter[2] - baseCenter[2],
  ]
  const projectInteraction = (behavior: OpeningElementBehavior): OpeningElementBehavior => ({
    ...behavior, pivot: project(behavior.pivot), closedPosition: project(behavior.closedPosition),
  })
  const elements: GeometryElement[] = []
  for (const element of baseElements) {
    if (element.type === 'opening' && element._interaction?.kind === 'opening') {
      // 裁墙洞口留在原墙；活动玻璃放在凸窗正面，不能再加一整片固定玻璃挡住它。
      elements.push({
        type: 'primitive', shape: 'box', id: element.id,
        position: project(element._interaction.closedPosition),
        rotation: [...element._interaction.closedRotation],
        dimensions: [element.width, element.height, element.depth!], material: element.material,
        _interaction: projectInteraction(element._interaction),
      })
    } else if (element.type === 'primitive' && element._interaction?.kind === 'opening') {
      elements.push({ ...element, position: project(element.position!), _interaction: projectInteraction(element._interaction) })
    } else {
      elements.push(element)
      // 墙洞边框与前立面边框分别承托洞口和窗扇。
      if (interaction && element.type === 'primitive') {
        elements.push({ ...element, id: `${element.id}__front`, position: project(element.position!) })
      }
    }
  }

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
    ...(!interaction ? [createBox(
      `${component.id}__front_glass`,
      frame.pointAt(centerAlong, bottomY + component.height / 2, frontOffset),
      [clearWidth, clearHeight, frameDepth],
      rotation,
      component.glassMaterial,
    )] : []),
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
