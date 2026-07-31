/**
 * 场景文档类型定义
 * 
 * 定义前端场景状态相关的类型：
 * - SceneDocument: 场景文档（Blueprint + revision + dirty 状态）
 * - ReconstructedEntity: wild-core 重建后的几何数据
 * - MeshData: 网格数据（位置、法线、UV、索引）
 * - SceneSummary: 场景摘要（用于 Agent 快速了解场景状态）
 */

import type { Blueprint } from './blueprint'

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
export interface ReconstructedEntity {
  meshes: MeshData[]
  materialParams: MaterialParams[]
  boundingBox: BoundingBox
  physics?: unknown
  scripts?: unknown[]
  animation?: unknown
  diagnostics: EngineDiagnostic[]
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
    baseColor?: EmbeddedImageData
    normal?: EmbeddedImageData
    roughness?: EmbeddedImageData
    metalness?: EmbeddedImageData
    ambientOcclusion?: EmbeddedImageData
  }
  normalScale?: number
  uvScale?: [number, number]
}

export interface EmbeddedImageData {
  encoding: 'base64'
  mimeType: string
  data: string
}

export interface EngineDiagnostic {
  level: 'info' | 'warning' | 'error'
  code: string
  message: string
  elementId?: string
  elementType?: string
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
