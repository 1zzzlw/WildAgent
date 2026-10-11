import type {
  GeometryElement,
  LightBodyPart,
  LightComponent,
  LightElementBehavior,
  PrimitiveParams,
} from '../../../types'
import type { ComponentCompileContext } from '../types'
import { COMPONENT_MATERIAL } from '../componentMaterials'
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
  // 参数化通路优先：body 一旦给了，fixtureType 的预设几何不再参与。
  // 这是"灯型不该写死在枚举里"的落点——新增形态只写数据，不改编译器。
  if (component.body?.length) {
    return compileBody(component, interaction)
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
  const emitter = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__emitter`,
    shape: 'sphere',
    position: [...component.position],
    radius: radius * 0.55,
    segments: 20,
  }, COMPONENT_MATERIAL.bulbEmitter)
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
  return [bulb, emitter, base]
}

/**
 * 展开参数化灯体。
 *
 * `_interaction` 只挂在标了`interactive: true` 的那一段上 —— 右键点灯需要**唯一命中体**，
 * 挂到多段会让一次点击循环多次、或点到灯壳上却点不到光源。
 * 一段都没标时默认挂最后一段（灯体通常是"外壳 + 发光面"两段，发光面在后）。
 * 没有 `interactive` 段的灯仍然发光，但不可点击 —— 允许，只是不给交互入口。
 */
function compileBody(
  component: LightComponent,
  interaction: LightElementBehavior,
): GeometryElement[] {
  const parts = component.body as LightBodyPart[]
  if (!Array.isArray(parts) || parts.length === 0) {
    throw new Error('body 必须是非空数组')
  }
  const interactiveIndex = resolveInteractiveIndex(parts)
  return parts.map((part, index): PrimitiveParams => {
    const { interactive: _interactive, position, ...shape } = part
    const element: PrimitiveParams = {
      type: 'primitive',
      id: `${component.id}__body_${String(index + 1).padStart(2, '0')}`,
      shape: shape.shape,
      // profile_sweep 的顶点已经把 path 的绝对坐标烘进去了（primitive.ts 的 sweptPoint
      // 直接用 origin + 偏移），而 buildPrimitive 还会把 transform.position 再加一遍
      // （primitive.ts:16）。不置零就会整体平移一次 —— 表现为灯跑到房间外面。
      // 其它形状（box/sphere/cylinder）顶点在局部原点，必须给 position。
      position: shape.shape === 'profile_sweep'
        ? [0, 0, 0]
        : position ?? [...component.position],
    }
    // 只搬shape 上真实存在的字段：undefined 会让 jsonschema 的 oneOf 分支匹配失败。
    // 经 unknown 中转是因为 PrimitiveParams 没有索引签名。
    for (const [key, value] of Object.entries(shape)) {
      if (value !== undefined && key !== 'shape') {
        (element as unknown as Record<string, unknown>)[key] = value
      }
    }
    if (component.body?.[index]?.material === undefined
      && (component.material || component.shadeMaterial)) {
      element.material = component.material ?? component.shadeMaterial
    }
    if (index === interactiveIndex) {
      element._interaction = interaction
    }
    return element
  })
}

/** 命中体下标：显式 interactive 优先，否则取最后一段；多于一段显式标记时只认第一段。 */
function resolveInteractiveIndex(parts: LightBodyPart[]): number {
  const marked = parts.findIndex(part => part.interactive === true)
  return marked >= 0 ? marked : parts.length - 1
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
  const emitter = withOptionalMaterial<PrimitiveParams>({
    type: 'primitive',
    id: `${component.id}__emitter`,
    shape: 'sphere',
    position: [x, bulbCenterY, z],
    radius: bulbRadius * 0.55,
    segments: 20,
  }, COMPONENT_MATERIAL.bulbEmitter)
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
  return [bulb, emitter, base, stem, shade]
}

function withOptionalMaterial<T extends GeometryElement>(element: T, material?: string): T {
  if (material) (element as T & { material?: string }).material = material
  return element
}
