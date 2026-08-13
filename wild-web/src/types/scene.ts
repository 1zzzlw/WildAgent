/**
 * 场景文档类型定义
 * 
 * 定义前端场景状态相关的类型：
 * - SceneDocument: 场景文档（Blueprint + revision + dirty 状态）
 * - ReconstructedEntity: wild-core 重建后的几何数据
 * - MeshData: 网格数据（位置、法线、UV、索引）
 * - SceneSummary: 场景摘要（用于 Agent 快速了解场景状态）
 */

import type { Blueprint, EmbeddedImageData, TextureImageData } from './blueprint'
import type { ComponentCompilationMapping } from '../wild-compiler'
import type { InteractiveElementBehavior } from '../wild-core/types'

export interface SceneDocument {
  id: string
  name: string
  revision: number
  blueprint: Blueprint
  dirty: boolean
  savedAt?: number
}

/**
 * wild-core 重建后的完整实体
 *
 * 注意：这里的类型定义匹配 wild-core/src/primitive/types.ts 的 ReconstructedEntity
 * materialParams 和 boundingBox 在 wild-core 中始终存在
 */
export interface ReconstructionBounds {
  min: [number, number, number]
  max: [number, number, number]
}

export interface ReconstructionObservation {
  sourceId: string
  sourceType: string
  renderedElementIds: string[]
  meshCount: number
  status: 'ok' | 'warning' | 'error'
  expectedRelation: 'self' | 'attached_to_parent' | 'covers_walls'
  targetId?: string
  expectedBounds?: ReconstructionBounds
  actualBounds?: ReconstructionBounds
  separation?: number
  message?: string
}

export interface ReconstructionReport {
  observations: ReconstructionObservation[]
  errorCount: number
  warningCount: number
}

export interface ReconstructedEntity {
  meshes: MeshData[]
  materialParams: MaterialParams[]
  boundingBox: BoundingBox
  physics?: unknown
  scripts?: unknown[]
  animation?: unknown
  diagnostics: EngineDiagnostic[]
  reconstructionReport: ReconstructionReport
  /** 组合构件与临时 Core 元素的双向映射，不会写回 Blueprint。 */
  componentMapping: ComponentCompilationMapping
}

/**
 * 网格数据
 *
 * 字段名与 wild-core/src/primitive/types.ts 的 MeshData 保持一致
 */
export interface MeshData {
  id?: string
  elementId?: string
  geometry: Float32Array
  normals?: Float32Array
  uvs?: Float32Array
  indices?: Uint32Array
  vertexColors?: Float32Array
  materialRef: string
  transform: {
    position: [number, number, number]
    rotation: [number, number, number]
    scale: [number, number, number]
  }
  patternMortarColor?: [number, number, number]
  interactive?: boolean
  interaction?: InteractiveElementBehavior
  draggable?: boolean
}

/**
 * 材质参数
 * 匹配 wild-core 的 MaterialParams
 */
export interface MaterialParams {
  baseColor: [number, number, number]
  roughness: number
  metallic: number
  albedo: number
  emissive: [number, number, number]
  opacity: number
  effects?: unknown[]
  lightingCondition?: string
  embeddedImage?: EmbeddedImageData
  textures?: {
    baseColor?: TextureImageData
    normal?: TextureImageData
    roughness?: TextureImageData
    metalness?: TextureImageData
    ambientOcclusion?: TextureImageData
  }
  normalScale?: number
  uvScale?: [number, number]
  materialClass?: 'standard' | 'glass' | 'clearcoat' | 'fabric'
  side?: 'front' | 'double'
  transmission?: number
  ior?: number
  thickness?: number
  attenuationColor?: [number, number, number]
  attenuationDistance?: number
  clearcoat?: number
  clearcoatRoughness?: number
  sheen?: number
  sheenColor?: [number, number, number]
  emissiveIntensity?: number
}

export interface EngineDiagnostic {
  level: 'info' | 'warning' | 'error'
  code: string
  message: string
  category?: 'schema_contract' | 'coordinate_frame' | 'level_continuity'
    | 'host_relation' | 'coverage_geometry' | 'compiler_geometry'
    | 'core_geometry' | 'renderer_only' | 'model_instruction'
  repairLayer?: 'validator' | 'compiler' | 'core' | 'renderer'
  elementId?: string
  elementType?: string
  expectedBounds?: ReconstructionBounds
  actualBounds?: ReconstructionBounds
}

export interface BoundingBox {
  min: [number, number, number]
  max: [number, number, number]
}

export interface SceneSummary {
  elements_count: number
  types: string[]
  bbox?: BoundingBox
  materials?: string[]
}
