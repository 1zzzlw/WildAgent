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

export type MaterialRoleName =
  | 'facade_primary' | 'structure' | 'floor' | 'frame' | 'door'
  | 'glass' | 'roof' | 'ground' | 'accent'

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
  decisions: {
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
