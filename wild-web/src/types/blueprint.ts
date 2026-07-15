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

export interface Blueprint {
  meta: BlueprintMeta
  geometry: GeometrySection
  materials?: Record<string, MaterialDef>
  behaviors?: BehaviorsSection
  editor?: EditorMetadata
}

export interface BlueprintMeta {
  version: string
  type: string
  name: string
  author?: string
  description?: string
}

export interface GeometrySection {
  elements: GeometryElement[]
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

export interface MaterialDef {
  name: string
  baseColor?: [number, number, number]
  metallic?: number
  roughness?: number
  [key: string]: unknown
}

export interface BehaviorsSection {
  physics?: unknown
  scripts?: unknown
  animations?: unknown
  [key: string]: unknown
}

export interface EditorMetadata {
  version?: string
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
  id: string
  template: string
  position?: [number, number, number]
  rotation?: [number, number, number]
  scale?: [number, number, number]
}

export interface Placement {
  id: string
  template: string
  region: unknown
  spacing?: number
  [key: string]: unknown
}
