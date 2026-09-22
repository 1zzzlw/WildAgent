import type { WorldEnvironmentState } from '../materials'

export interface WorldTransform {
  position: [number, number, number]
  rotation?: [number, number, number]
  scale?: [number, number, number]
}

export interface WorldBlueprintResource {
  blueprintId: string
  uri?: string
  contentHash?: string
}

export interface WorldBlueprintInstance {
  instanceId: string
  blueprintId: string
  chunkId: string
  transform: WorldTransform
  visible?: boolean
  /** 世界语义槽位到 Blueprint 材质名的覆盖，不复制几何。 */
  materialSlots?: Record<string, string>
}

export interface WorldChunk {
  chunkId: string
  bounds?: { min: [number, number, number]; max: [number, number, number] }
  priority?: number
}

export interface WorldTheme {
  themeId: string
  materialSlots: Record<string, string>
  renderProfile?: string
}

/** renderer 无关的世界事实源；一份 Blueprint 可被多个实例引用。 */
export interface WorldDocument {
  format: 'wild.world'
  version: '1.0'
  worldId: string
  name: string
  revision: number
  blueprints: Record<string, WorldBlueprintResource>
  instances: WorldBlueprintInstance[]
  chunks: WorldChunk[]
  theme?: WorldTheme
  materialLibraries?: string[]
  renderProfile?: string
  environment?: Partial<WorldEnvironmentState>
}

export function validateWorldDocument(document: WorldDocument): string[] {
  const issues: string[] = []
  if (document.format !== 'wild.world' || document.version !== '1.0') issues.push('世界文档版本不受支持')
  if (!document.worldId.trim()) issues.push('worldId 不能为空')
  const instanceIds = new Set<string>()
  const chunkIds = new Set(document.chunks.map(chunk => chunk.chunkId))
  for (const instance of document.instances) {
    if (instanceIds.has(instance.instanceId)) issues.push(`实例 ID 重复: ${instance.instanceId}`)
    instanceIds.add(instance.instanceId)
    if (!document.blueprints[instance.blueprintId]) issues.push(`实例引用未知 Blueprint: ${instance.blueprintId}`)
    if (!chunkIds.has(instance.chunkId)) issues.push(`实例引用未知区块: ${instance.chunkId}`)
    if (![...instance.transform.position, ...(instance.transform.rotation || []), ...(instance.transform.scale || [])]
      .every(Number.isFinite)) issues.push(`实例变换包含非法数值: ${instance.instanceId}`)
  }
  return issues
}
