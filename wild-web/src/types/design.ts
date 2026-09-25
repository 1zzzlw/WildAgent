/** DesignDocument v1。字段与后端 Pydantic JSON Schema 保持一致。 */

export type DesignStatus = 'draft' | 'approved' | 'compiled'
export type OpeningKind = 'door' | 'window' | 'empty'

export interface DesignMassing {
  shape: string
  width: number
  depth: number
  floors: number
  modeled_floors: number
  representation_mode: 'full' | 'schematic'
  floor_height: number
  symmetry: boolean
}

export interface DesignVolume {
  id: string
  role: 'primary' | 'secondary'
  x: number
  z: number
  width: number
  depth: number
  start_floor: number
  end_floor: number
}

export interface DesignFacade {
  bays: number
  entrance_bay: number | null
  ground_pattern: OpeningKind[]
  upper_pattern: OpeningKind[]
}

// 建筑侧角色与物件侧角色的并集——`ResolvedMaterialPlan` 被两支共用。
// 后端唯一事实源：`wild-server/app/design/contracts.py::MaterialRoleName`。
// 物件侧没有 frame，用 metal（见 `material_plan.py::_METALLIC_ROLES`）。
export type ArchitectureMaterialRoleName =
  | 'facade_primary' | 'structure' | 'floor' | 'frame' | 'door'
  | 'glass' | 'roof' | 'ground' | 'accent'

export type ObjectMaterialRoleName =
  | 'wood' | 'metal' | 'glass' | 'stone' | 'fabric' | 'accent'

export type MaterialRoleName =
  | ArchitectureMaterialRoleName
  | ObjectMaterialRoleName

export interface ResolvedMaterialPlan {
  concept: string
  palette: string[]
  roles: Array<{
    role: MaterialRoleName
    materialId: string
    assetId: string | null
    proceduralPresetId: string | null
    material: Record<string, unknown>
  }>
  resolvedAssets: Record<string, Record<string, unknown>>
  rejectedAssetIds: string[]
  rejectedProceduralPresetIds: string[]
  curtainWall: boolean
}

/**
 * 设计决策的**带标签联合**。判别字段是两边都有的 `kind`：
 * 有 `massing` 的那支只能解析成 ArchitectureDecisions，反之亦然。
 *
 * 前端此前无条件读 `decisions.massing.width`，对物件方案（"生成一个桌子"）
 * 会直接在模板里抛异常。所有消费点必须先按 `kind` 收窄。
 */
export type DesignDecisions = ArchitectureDecisions | ObjectDecisions

export interface ArchitectureDecisions {
  kind: 'architecture'
  concept: string
  massing: DesignMassing
  complexity: {
    level: 'minimal' | 'simple' | 'standard' | 'detailed'
    min_volumes: number
    min_detail_packages: number
    target_structural_elements: number
    grid_bays: [number, number]
    reason: string
  }
  volumes: DesignVolume[]
  structural_grid: {
    system: 'wall_bearing' | 'frame' | 'hybrid' | 'long_span' | 'shell'
    x_bays: number
    z_bays: number
  }
  envelope: {
    system: 'solid_wall' | 'curtain_wall'
    curtain_wall: {
      grid_strategy: 'floor_and_bay_aligned'
    } | null
  }
  facades: Record<'front' | 'back' | 'left' | 'right', DesignFacade>
  roof: {
    type: 'flat' | 'gable' | 'hip' | 'dome' | 'chinese_curved' | 'chinese_pagoda'
    ridge_axis: 'x' | 'z'
    overhang: number
  }
  circulation: {
    vertical_strategy: 'none' | 'stair' | 'core' | 'core_and_stair'
  }
  materials: { keywords: string[]; resolved_plan: ResolvedMaterialPlan | null }
  detail_packages: string[]
  component_quota: Record<string, { min: number; max: number; note: string; type: string | null }>
  balcony_access_count: number
  balcony_width: number | null
  required_components: string[]
  unsupported_component_types: string[]
  design_rationale: string[]
}

/**
 * 物件场景里的一个待生成物件：只描述"做几个、多大、怎么摆"，不描述几何。
 *
 * `kind` 是**表达通道**（与后端 `OBJECT_COMPONENT_KINDS` 一致）：
 * `furniture`（图鉴预设，靠 subtype）/ `primitive`（通用几何组合，靠 parts）/
 * `body`（简化人物，靠 params）。`name` 是用户点名的原始名词。
 */
export interface DesignObject {
  kind: string
  subtype: string
  /** 用户点名的原始名词（"桌子"/"小人"/"花瓶"）。预设通道可为空。 */
  name: string
  count: number
  width: number
  depth: number
  height: number
  /** `kind=primitive` 的零件表：每项是一份 WILD primitive 参数（相对物件底面中心）。 */
  parts: Array<Record<string, unknown>>
  /** `kind` 专属参数（目前只有 `body` 使用）。 */
  params: Record<string, unknown>
  /** 摆位说明（自然语言约束）。世界坐标由构件生成节点按行走面标高算出。 */
  placement: string
  material: string
  rationale: string
}

/** 与后端 `ObjectDecisions` 一致：没有体量、立面与屋顶，只有物件清单与材质。 */
export interface ObjectDecisions {
  kind: 'object'
  concept: string
  objects: DesignObject[]
  /** 点名了、但本次表达不出可生成几何的物件（非阻断提示，进交付清单）。 */
  unsupported_objects: string[]
  materials: { keywords: string[]; resolved_plan: ResolvedMaterialPlan | null }
  design_rationale: string[]
}

export interface DesignDocument {
  schema_version: 'design/1.0'
  design_id: string
  session_id: string
  revision: number
  status: DesignStatus
  created_at: string
  updated_at: string
  approved_at: string | null
  requirements: {
    source_request: string
    building_type: string
    profile: string
    style_intent: string[]
  }
  decisions: DesignDecisions
  constraints: Array<{
    id: string
    kind: 'user_hard' | 'engine_hard' | 'system_required' | 'preference' | 'reference'
    target: string
    expression: string
    source: string
  }>
  locks: string[]
  rule_trace: Array<{
    rule_id: string
    classification: 'engine_hard' | 'conditional' | 'preference' | 'reference' | 'unsupported'
    applies_when: string
    schema_targets: string[]
    enforcement: Array<'schema' | 'planner' | 'resolver' | 'compiler' | 'validator' | 'none'>
    source: string
  }>
}

export interface ResolvedDesign {
  schema_version: 'resolved-design/1.0'
  design_id: string
  design_revision: number
  design_hash: string
  bounds: { width: number; depth: number; height: number }
  levels: Array<{ index: number; base_y: number; top_y: number }>
  volumes: DesignVolume[]
  facade_slots: Array<{
    id: string
    facing: 'front' | 'back' | 'left' | 'right'
    floor: number
    bay: number
    type: 'door' | 'window'
    offset: number
    width: number
    bottom: number
    height: number
  }>
  component_quantities: Record<string, number>
  warnings: string[]
}

export interface DesignPatch {
  type: 'design_patch'
  patch_id: string
  base_revision: number
  source: 'user' | 'agent' | 'system'
  operations: Array<{
    op: 'add' | 'replace' | 'remove'
    path: string
    value?: unknown
  }>
  summary?: string
}
