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
 * 注意：这里的类型定义要匹配 wild-core/src/primitive/types.ts 的 ReconstructedEntity
 */
export interface ReconstructedEntity {
  meshes: MeshData[]
  materialParams?: MaterialParams[]
  boundingBox?: BoundingBox
  physics?: unknown
  scripts?: unknown[]
  animations?: unknown
}

/**
 * 网格数据
 * 
 * 注意：wild-core 输出的 MeshData.geometry 字段名实际上是顶点位置数组
 * 我们在前端重命名为 positions 更清晰
 */
export interface MeshData {
  id?: string
  elementId?: string
  positions: Float32Array          // wild-core 的 geometry 字段
  normals?: Float32Array
  uvs?: Float32Array
  indices?: Uint32Array
  colors?: Float32Array            // wild-core 的 vertexColors 字段
  materialRef: string              // wild-core 的 materialRef 字段
  transform?: {                    // wild-core 的 transform 字段
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
  emissive?: [number, number, number]
  opacity?: number
  effects?: unknown[]
  lightingCondition?: string
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
