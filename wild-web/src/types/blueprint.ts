/**
 * Blueprint 核心类型定义
 * 
 * 定义 WILD 语言的核心数据结构，包括：
 * - Blueprint: .wild 文件的完整结构
 * - GeometryElement: 构件类型（wall, column, roof 等）
 * - MaterialDef: 材质定义
 * - EditorMetadata: 编辑器私有元数据
 * 
 * 这些类型是整个项目的基础，所有场景数据都基于此结构。
 */

import type { ComponentSpec } from '../wild-core/types'
export type { ComponentSpec } from '../wild-core/types'

export interface Blueprint {
  meta: BlueprintMeta
  geometry: GeometrySection
  materials?: Record<string, MaterialDef>
  assets?: Record<string, PBRTextureSetAsset>
  behaviors?: BehaviorsSection
  editor?: EditorMetadata
}

export interface BlueprintMeta {
  version: '1.0' | '1.1'
  type: 'building' | 'avatar' | 'asset' | 'scene'
  name: string
  author?: string
  description?: string
}

export interface GeometrySection {
  elements: GeometryElement[]
  components?: ComponentSpec[]
  templates?: Record<string, GeometryElement>
  instances?: InstanceRef[]
  placements?: Placement[]
}

export interface GeometryElement {
  id: string
  type: GeometryElementType
  [key: string]: unknown
}

export type GeometryElementType =
  | 'wall'
  | 'floor'
  | 'column'
  | 'beam'
  | 'roof'
  | 'opening'
  | 'stair'
  | 'furniture'
  | 'dense_brick'
  | 'body'
  | 'primitive'

export interface MaterialDef {
  baseColor: [number, number, number]
  roughness: number
  metallic: number
  albedo: number
  lightingCondition: 'D65_noon'
  emissive?: [number, number, number]
  opacity?: number
  effects?: Array<Record<string, unknown>>
  embeddedImage?: EmbeddedImageData
  textures?: {
    baseColor?: TextureImageData
    normal?: TextureImageData
    roughness?: TextureImageData
    metalness?: TextureImageData
    ambientOcclusion?: TextureImageData
  }
  textureSet?: string
  normalScale?: number
  uvScale?: [number, number]
  /** 渲染器材质模型；缺省时保持标准 metallic-roughness PBR。 */
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
  [key: string]: unknown
}

export interface EmbeddedImageData {
  encoding: 'base64'
  mimeType: string
  data: string
}

export interface ReferencedImageData {
  encoding: 'url'
  uri: string
  mimeType: 'image/png' | 'image/jpeg' | 'image/webp'
  sha256: string
  byteSize?: number
  colorSpace: 'srgb' | 'linear'
}

export type TextureImageData = EmbeddedImageData | ReferencedImageData

export interface PBRTextureSetAsset {
  schemaVersion: '1.0'
  assetId: string
  kind: 'pbr_texture_set'
  name: string
  contentHash: string
  source: { type: string; uri?: string }
  license: string
  maps: {
    baseColor: ReferencedImageData
    normal?: ReferencedImageData
    roughness?: ReferencedImageData
    metalness?: ReferencedImageData
    ambientOcclusion?: ReferencedImageData
  }
  classification?: {
    materialClass?: string
    tags?: string[]
    recommendedRoles?: string[]
  }
  realWorldSizeMeters?: [number, number]
  defaults?: {
    baseColorTint?: [number, number, number]
    roughness?: number
    metallic?: number
    normalScale?: number
    uvScale?: [number, number]
  }
  createdAt: string
}

export interface BehaviorsSection {
  physics?: unknown
  scripts?: unknown
  animation?: unknown
  [key: string]: unknown
}

export interface EditorMetadata {
  version?: string
  /** 场景版本号，随 save/load 持久化，供 AI 生成/加载后保持 revision 连续性 */
  revision?: number
  groups?: Record<string, EditorGroup>
  view?: EditorView
  agent?: AgentMetadata
}

export interface EditorGroup {
  name: string
  elements: string[]
}

export interface EditorView {
  camera?: {
    position: [number, number, number]
    target: [number, number, number]
  }
}

export interface AgentMetadata {
  generatedBy?: string
  lastPrompt?: string
}

export interface InstanceRef {
  id?: string
  ref: string
  position: [number, number, number]
  rotation?: [number, number, number]
  scale?: [number, number, number]
  materialOverride?: Record<string, string>
}

export interface Placement {
  id: string
  template: string
  region: unknown
  spacing?: number
  [key: string]: unknown
}
