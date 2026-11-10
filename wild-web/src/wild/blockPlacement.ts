import type { ComponentSpec, GeometryElement as CoreElement, RoofParams, WallParams, Vec3 } from 'wild-core/types'
import type { Blueprint, GeometryElement, MaterialDef, PBRTextureSetAsset } from '../types/blueprint'
import type { AddElementOperation, AddComponentOperation, SceneOperation } from '../types/scenePatch'
import { createComponentTranslationChanges } from './componentDrag'
import { getRecipeDefaults } from 'wild-core/compiler'

export type BlockPlacementChoice =
  | { kind: 'element'; label: string; defaults: Partial<GeometryElement> }
  | { kind: 'component'; label: string; type: ComponentSpec['type']; fixtureType?: 'bulb' | 'table_lamp' }
  /** 物品库条目：一次放下多个几何元素及其材质。物品不是新的引擎类型。 */
  | { kind: 'item'; label: string; asset: ItemPlacementAsset }

export interface ItemPlacementAsset {
  itemId: string
  parts: GeometryElement[]
  materials: Record<string, MaterialDef>
  assets: Record<string, PBRTextureSetAsset>
}

export type BlockPlacementRequest = BlockPlacementChoice & { id: string }
export interface BlockPlacementDraft {
  /** 提交用：一次放置产出的全部操作（物品会有多条 add_element）。 */
  operations: SceneOperation[]
  /** 放置完成后应作为一个整体选中的源元素。 */
  selectionIds: string[]
  /** 蓝图坐标下的预览平移锚点，预览与提交共用同一份参数。 */
  anchor: Vec3
  hostId?: string
}

export function createBlockPlacement(
  request: BlockPlacementRequest,
  blueprint: Blueprint,
  point: Vec3,
  hostId?: string,
): BlockPlacementDraft {
  const host = blueprint.geometry.elements.find(item => item.id === hostId)
  if (request.kind === 'item') {
    const item = instantiateItem(request, blueprint, point)
    return {
      operations: item.operations,
      selectionIds: item.elementOperations.map(operation => operation.element.id),
      anchor: point,
    }
  }
  if (request.kind === 'element') {
    const element = JSON.parse(JSON.stringify({ ...request.defaults, id: request.id })) as CoreElement
    if (element.type === 'primitive' && element.label) element.label.text = blueprint.meta.name
    if (element.type === 'roof') element.position = [0, 0, 0]
    const origin: Vec3 = element.type === 'wall' || element.type === 'floor'
      ? [(element.from[0] + element.to![0]) / 2, element.from[1], (element.from[2] + element.to![2]) / 2]
      : [0, 0, 0]
    const delta = point.map((value, i) => value - origin[i]!) as Vec3
    const placed = { ...element, ...createComponentTranslationChanges(element, delta, [element]) }
    const operation: AddElementOperation = { op: 'add_element', element: placed }
    return { operations: [operation], selectionIds: [element.id], anchor: point }
  }
  const component = createDefaultComponent(request.type, request.fixtureType, host)
  component.id = request.id
  if ('parentWall' in component && component.parentWall && 'from' in component) {
    const wall = host as unknown as WallParams
    const dx = wall.to[0] - wall.from[0], dz = wall.to[2] - wall.from[2]
    const length = Math.hypot(dx, dz)
    const width = component.width
    const along = ((point[0] - wall.from[0]) * dx + (point[2] - wall.from[2]) * dz) / length
    const bottom = Math.min(wall.from[1], wall.to[1]), top = Math.max(wall.from[1], wall.to[1])
    const height = 'height' in component ? component.height : 0.15
    component.from = [
      Math.max(0.05, Math.min(length - width - 0.05, along - width / 2)),
      component.type === 'door' ? bottom : Math.max(bottom, Math.min(top - height - 0.05, point[1] - height / 2)),
      0,
    ]
    const anchor: Vec3 = [wall.from[0] + component.from[0] * dx / length, component.from[1], wall.from[2] + component.from[0] * dz / length]
    const operation: AddComponentOperation = { op: 'add_component', component }
    return { operations: [operation], selectionIds: [component.id], anchor, hostId: wall.id }
  }
  if (component.type === 'cornice') {
    const operation: AddComponentOperation = { op: 'add_component', component }
    return { operations: [operation], selectionIds: [component.id], anchor: [0, 0, 0], hostId: component.parentRoof }
  }
  Object.assign(component, createComponentTranslationChanges(component, point, blueprint.geometry.elements))
  const operation: AddComponentOperation = { op: 'add_component', component }
  return { operations: [operation], selectionIds: [component.id], anchor: point }
}

function instantiateItem(
  request: Extract<BlockPlacementRequest, { kind: 'item' }>,
  blueprint: Blueprint,
  point: Vec3,
): { operations: SceneOperation[]; elementOperations: AddElementOperation[] } {
  if (!request.asset.parts.length) throw new Error('该物品没有几何')

  const idMap = new Map<string, string>()
  request.asset.parts.forEach((part, index) => {
    const sourceId = typeof part.id === 'string' && part.id ? part.id : `part_${index}`
    if (idMap.has(sourceId)) throw new Error(`物品包含重复零件 id: ${sourceId}`)
    idMap.set(sourceId, `${request.id}_${sourceId}`)
  })

  const usedMaterials = new Set<string>()
  request.asset.parts.forEach(part => collectMaterialReferences(part as Record<string, unknown>, usedMaterials))
  const usedAssets = new Set([...usedMaterials].flatMap(name => {
    const textureSet = request.asset.materials[name]?.textureSet
    return textureSet ? [textureSet] : []
  }))
  const materialNames = new Map<string, string>()
  const assetNames = new Map<string, string>()
  const assetOperations: SceneOperation[] = []
  for (const [name, asset] of Object.entries(request.asset.assets)) {
    if (!usedAssets.has(name)) continue
    const baseName = `item_${safeToken(request.asset.itemId)}_${safeToken(name)}`
    const baseCopy = { ...clone(asset), assetId: baseName }
    const existing = blueprint.assets?.[baseName]
    const targetName = !existing || sameJson(existing, baseCopy)
      ? baseName
      : `${baseName}_${safeToken(request.id)}`
    assetNames.set(name, targetName)
    if (!blueprint.assets?.[targetName]) {
      assetOperations.push({
        op: 'upsert_asset',
        asset_id: targetName,
        asset: { ...clone(asset), assetId: targetName },
      })
    }
  }
  const materialOperations: SceneOperation[] = []
  for (const [name, material] of Object.entries(request.asset.materials)) {
    if (!usedMaterials.has(name)) continue
    const baseName = `item_${safeToken(request.asset.itemId)}_${safeToken(name)}`
    const materialCopy = clone(material)
    if (materialCopy.textureSet) materialCopy.textureSet = assetNames.get(materialCopy.textureSet) || materialCopy.textureSet
    const existing = blueprint.materials?.[baseName]
    const targetName = !existing || sameJson(existing, materialCopy)
      ? baseName
      : `${baseName}_${safeToken(request.id)}`
    materialNames.set(name, targetName)
    if (!blueprint.materials?.[targetName]) {
      materialOperations.push({ op: 'upsert_material', name: targetName, material: materialCopy })
    }
  }

  const elementOperations: AddElementOperation[] = request.asset.parts.map(part => {
    const element = rewriteItemPart(clone(part), idMap, materialNames, point)
    return { op: 'add_element', element }
  })
  const elementIds = elementOperations.map(operation => operation.element.id)
  const groups = clone(blueprint.editor?.groups || {})
  groups[request.id] = {
    name: request.label,
    kind: 'item',
    sourceItemId: request.asset.itemId,
    elements: elementIds,
  }
  return {
    operations: [
      ...assetOperations,
      ...materialOperations,
      ...elementOperations,
      { op: 'set_editor_meta', changes: { groups } },
    ],
    elementOperations,
  }
}

function collectMaterialReferences(value: Record<string, unknown>, output: Set<string>): void {
  for (const [key, child] of Object.entries(value)) {
    if ((key === 'material' || key.endsWith('Material')) && typeof child === 'string') {
      output.add(child)
    } else if (child && typeof child === 'object' && !Array.isArray(child)) {
      collectMaterialReferences(child as Record<string, unknown>, output)
    }
  }
}

function rewriteItemPart(
  part: GeometryElement,
  ids: ReadonlyMap<string, string>,
  materials: ReadonlyMap<string, string>,
  offset: Vec3,
): GeometryElement {
  const sourceId = part.id
  part.id = ids.get(sourceId) || sourceId
  rewriteReferences(part as Record<string, unknown>, ids, materials)
  const positioned = part as GeometryElement & { position?: Vec3; path?: Vec3[] }
  if (isVec3(positioned.position)) {
    positioned.position = add(positioned.position, offset)
  } else if (Array.isArray(positioned.path) && positioned.path.every(isVec3)) {
    positioned.path = positioned.path.map(point => add(point, offset))
  }
  return positioned
}

const REFERENCE_FIELDS = new Set([
  'parentWall', 'parentFloor', 'parentRoof', 'parent', 'target',
])

function rewriteReferences(
  value: Record<string, unknown>,
  ids: ReadonlyMap<string, string>,
  materials: ReadonlyMap<string, string>,
): void {
  for (const [key, child] of Object.entries(value)) {
    if ((key === 'material' || key.endsWith('Material')) && typeof child === 'string') {
      value[key] = materials.get(child) || child
      continue
    }
    if (key === 'operands' && Array.isArray(child)) {
      value[key] = child.map(id => typeof id === 'string' ? ids.get(id) || id : id)
      continue
    }
    if (REFERENCE_FIELDS.has(key) && typeof child === 'string' && ids.has(child)) {
      value[key] = ids.get(child)!
      continue
    }
    if (child && typeof child === 'object' && !Array.isArray(child)) {
      rewriteReferences(child as Record<string, unknown>, ids, materials)
    }
  }
}

function safeToken(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'item'
}

function sameJson(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function isVec3(value: unknown): value is Vec3 {
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite)
}

function add(left: Vec3, right: Vec3): Vec3 {
  return [left[0] + right[0], left[1] + right[1], left[2] + right[2]]
}

function createDefaultComponent(
  type: ComponentSpec['type'],
  fixtureType: 'bulb' | 'table_lamp' | undefined,
  host: GeometryElement | undefined,
): ComponentSpec {
  // 配方构件：初始字段全部来自数据（params.default + defaults）。
  // 这条分支必须**在**下面那张逐个 type 的 switch 之前 —— 它让「新增构件」
  // 不再需要往本文件里加分支。
  const recipeDefaults = getRecipeDefaults(type)
  if (recipeDefaults) {
    return { ...recipeDefaults, type, id: 'placement' } as unknown as ComponentSpec
  }
  if (type === 'fan') return { type, id: 'placement', position: [0, 2.6, 0], controlPosition: [0.9, 1.1, 0], radius: 0.65, bladeCount: 4, drop: 0.25, rpm: 180 }
  if (type === 'elevator') return { type, id: 'placement', position: [0, 0, 0], dimensions: { width: 1.8, depth: 1.8, height: 2.5 }, floorHeight: 3.3, floorCount: 2 }
  if (type === 'light') {
    if (fixtureType === 'table_lamp') {
      return {
        type,
        id: 'placement',
        fixtureType,
        position: [0, 0, 0],
        lightType: 'point',
        color: [1, 0.78, 0.52],
        lowIntensity: 18,
        highIntensity: 65,
        distance: 8,
        height: 0.72,
        shadeRadius: 0.28,
        baseHeight: 0.07,
        draggable: true,
      }
    }
    return {
      type,
      id: 'placement',
      fixtureType: 'bulb',
      position: [0, 2.4, 0],
      lightType: 'point',
      color: [1, 0.82, 0.58],
      lowIntensity: 25,
      highIntensity: 90,
      distance: 12,
      draggable: true,
    }
  }

  if (type === 'railing') {
    return {
      type,
      id: 'placement',
      path: [[0, 0, 0], [3, 0, 0]],
      height: 1.1,
      postSpacing: 0.9,
      railLevels: [0.5, 1],
    }
  }

  if (type === 'ramp') {
    return {
      type,
      id: 'placement',
      from: [0, 0, 0],
      to: [5.4, 0.45, 0],
      width: 1.5,
      thickness: 0.18,
      railingSides: 'both',
      railingHeight: 1.1,
    }
  }

  if (type === 'cornice') {
    const roof = host?.type === 'roof' ? host as unknown as RoofParams : undefined
    if (!roof) {
      throw new Error('请将鼠标移到要添加檐口的屋顶')
    }
    const halfSpan = roof.span / 2
    const halfDepth = roof.depth / 2
    const path: [number, number, number][] = roof.roofType === 'gable'
      ? [
          [-halfSpan, 0, -halfDepth],
          [-halfSpan, 0, halfDepth],
          [0, 0, halfDepth],
          [halfSpan, 0, halfDepth],
          [halfSpan, 0, -halfDepth],
          [0, 0, -halfDepth],
          [-halfSpan, 0, -halfDepth],
        ]
      : [
          [-halfSpan, 0, -halfDepth],
          [-halfSpan, 0, halfDepth],
          [halfSpan, 0, halfDepth],
          [halfSpan, 0, -halfDepth],
          [-halfSpan, 0, -halfDepth],
        ]
    return {
      type,
      id: 'placement',
      parentRoof: roof.id,
      path,
      profile: [
        [-0.16, -0.14],
        [0.16, -0.14],
        [0.16, -0.07],
        [0.1, -0.07],
        [0.1, 0],
        [0.05, 0],
        [0.05, 0.08],
        [-0.16, 0.08],
      ],
      closedProfile: true,
    }
  }

  if (type === 'chimney') {
    return {
      type,
      id: 'placement',
      position: [0, 0, 0],
      width: 0.7,
      depth: 0.7,
      height: 2,
      wallThickness: 0.1,
    }
  }

  const wall = host?.type === 'wall' ? host as unknown as WallParams : undefined
  if (!wall) {
    throw new Error('请将鼠标移到要依附的直线墙面')
  }
  if (wall.curve && (Array.isArray(wall.curve) ? wall.curve : [wall.curve]).some(curve => curve.type !== 'line')) {
    throw new Error('请在直线墙面上放置该构件')
  }
  const length = Math.hypot(wall.to[0] - wall.from[0], wall.to[2] - wall.from[2])
  const bottom = Math.min(wall.from[1], wall.to[1])
  const top = Math.max(wall.from[1], wall.to[1])
  const wallHeight = top - bottom
  if (length < 0.6 || wallHeight < 0.8) {
    throw new Error('这面墙尺寸过小，请选择另一面墙')
  }

  if (type === 'door') {
    const width = Math.min(0.9, length - 0.1)
    return {
      type,
      id: 'placement',
      parentWall: wall.id,
      from: [(length - width) / 2, bottom, 0],
      width,
      height: Math.min(2.1, wallHeight - 0.05),
      interaction: { mode: 'swing', hingeSide: 'left', openAngle: 90 },
    }
  }


  if (type === 'canopy') {
    const width = Math.min(2.4, length - 0.1)
    return {
      type,
      id: 'placement',
      parentWall: wall.id,
      from: [(length - width) / 2, bottom + Math.min(2.4, wallHeight - 0.1), 0],
      width,
      depth: 1.1,
      thickness: 0.12,
    }
  }

  if (type === 'balcony') {
    const width = Math.min(2.8, length - 0.1)
    return {
      type,
      id: 'placement',
      parentWall: wall.id,
      from: [(length - width) / 2, bottom + Math.min(1.2, wallHeight - 0.1), 0],
      width,
      depth: 1.2,
      slabThickness: 0.18,
      railingHeight: 1.1,
      postSpacing: 0.9,
    }
  }

  if (type === 'bay_window') {
    const sillHeight = Math.min(0.9, wallHeight * 0.3)
    const width = Math.min(1.8, length - 0.1)
    return {
      type,
      id: 'placement',
      parentWall: wall.id,
      from: [(length - width) / 2, bottom + sillHeight, 0],
      width,
      height: Math.max(0.3, Math.min(1.2, wallHeight - sillHeight - 0.05)),
      projectionDepth: 0.45,
    }
  }

  const sillHeight = Math.min(0.9, wallHeight * 0.3)
  const width = Math.min(1.5, length - 0.1)
  if (type === 'window') return {
    type,
    id: 'placement',
    parentWall: wall.id,
    from: [(length - width) / 2, bottom + sillHeight, 0],
    width,
    height: Math.max(0.3, Math.min(1.2, wallHeight - sillHeight - 0.05)),
    verticalMullions: 1,
    interaction: { mode: 'swing', openAngle: 70 },
  }
  throw new Error('该构件暂不支持放置')
}
