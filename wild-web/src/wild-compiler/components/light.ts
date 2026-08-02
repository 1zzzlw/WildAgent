import type {
  GeometryElement,
  LightComponent,
  LightElementBehavior,
  PrimitiveParams,
} from '../../wild-core/types'
import type { ComponentCompileContext } from '../types'
import {
  assertNonEmptyString,
  assertPositive,
  assertVec3,
} from './attachedToWall'

/** 将灯泡或台灯展开为基础 primitive；光源行为统一挂在发光灯泡网格上。 */
export function compileLight(
  component: LightComponent,
  _context: ComponentCompileContext,
): GeometryElement[] {
  assertNonEmptyString(component.id, 'id')
  assertVec3(component.position, 'position')
  const radius = component.bulbRadius ?? 0.16
  const baseHeight = component.baseHeight ?? 0.12
  const height = component.height ?? 0.72
  const shadeRadius = component.shadeRadius ?? 0.28
  const lowIntensity = component.lowIntensity ?? 25
  const highIntensity = component.highIntensity ?? 90
  const distance = component.distance ?? 12
  const angle = component.angle ?? 45
  assertPositive(radius, 'bulbRadius')
  assertPositive(baseHeight, 'baseHeight')
  assertPositive(height, 'height')
  assertPositive(shadeRadius, 'shadeRadius')
  assertPositive(lowIntensity, 'lowIntensity')
  assertPositive(highIntensity, 'highIntensity')
  assertPositive(distance, 'distance')
  assertPositive(angle, 'angle')
  if (highIntensity < lowIntensity) {
    throw new Error('highIntensity 不能小于 lowIntensity')
  }
  if (angle > 90) throw new Error('angle 不能大于 90 度')

  const interaction: LightElementBehavior = {
    kind: 'light',
    lightType: component.lightType ?? 'point',
    color: component.color ?? [1, 0.82, 0.58],
    lowIntensity,
    highIntensity,
    distance,
    angle,
    initiallyOn: component.initiallyOn ?? false,
  }
  if ((component.fixtureType ?? 'bulb') === 'table_lamp') {
    return compileTableLamp(component, interaction, height, shadeRadius, baseHeight)
  }

  const bulb = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__bulb`,
    shape: 'sphere',
    position: [...component.position],
    radius,
    segments: 24,
    _interaction: interaction,
  }, component.material)
  const base = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__base`,
    shape: 'cylinder',
    position: [
      component.position[0],
      component.position[1] + radius + baseHeight / 2,
      component.position[2],
    ],
    radiusTop: radius * 0.62,
    radiusBottom: radius * 0.78,
    height: baseHeight,
    segments: 20,
  }, component.baseMaterial ?? component.material)
  return [bulb, base]
}

function compileTableLamp(
  component: LightComponent,
  interaction: LightElementBehavior,
  height: number,
  shadeRadius: number,
  baseHeight: number,
): GeometryElement[] {
  const [x, y, z] = component.position
  const bulbRadius = component.bulbRadius ?? Math.min(0.09, shadeRadius * 0.38)
  const shadeHeight = height * 0.38
  const shadeCenterY = y + height - shadeHeight / 2
  const bulbCenterY = y + height - shadeHeight * 0.52
  const stemBottom = y + baseHeight
  const stemTop = shadeCenterY - shadeHeight * 0.34
  const stemHeight = Math.max(0.05, stemTop - stemBottom)
  const baseRadius = Math.max(shadeRadius * 0.72, bulbRadius * 1.6)

  const bulb = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__bulb`,
    shape: 'sphere',
    position: [x, bulbCenterY, z],
    radius: bulbRadius,
    segments: 24,
    _interaction: interaction,
  }, component.material)
  const base = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__base`,
    shape: 'cylinder',
    position: [x, y + baseHeight / 2, z],
    radiusTop: baseRadius * 0.86,
    radiusBottom: baseRadius,
    height: baseHeight,
    segments: 24,
  }, component.baseMaterial ?? component.material)
  const stem = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__stem`,
    shape: 'cylinder',
    position: [x, stemBottom + stemHeight / 2, z],
    radius: Math.max(0.018, shadeRadius * 0.09),
    height: stemHeight,
    segments: 18,
  }, component.baseMaterial ?? component.material)
  const shade = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__shade`,
    shape: 'cylinder',
    position: [x, shadeCenterY, z],
    radiusTop: shadeRadius * 0.58,
    radiusBottom: shadeRadius,
    height: shadeHeight,
    segments: 28,
  }, component.shadeMaterial ?? component.material)
  return [bulb, base, stem, shade]
}

function withOptionalMaterial<T extends GeometryElement>(element: T, material?: string): T {
  if (material) (element as T & { material?: string }).material = material
  return element
}
