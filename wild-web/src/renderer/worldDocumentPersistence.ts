import type { SceneDocument } from '../types/scene'
import type { WorldDocument } from '../wild-core/src/world'
import type { WorldEnvironmentState } from '../wild-core/src/materials'
import { validateWorldDocument } from '../wild-core/src/world'

const STORAGE_PREFIX = 'wild_world_document_v1:'

export function createEditorWorldDocument(
  scene: SceneDocument,
  options: {
    materialLibraries?: string[]
    renderProfile?: string
    environment?: Partial<WorldEnvironmentState>
  } = {},
): WorldDocument {
  return {
    format: 'wild.world',
    version: '1.0',
    worldId: `world:${scene.id}`,
    name: scene.name,
    revision: scene.revision,
    blueprints: {
      active: { blueprintId: 'active' },
    },
    chunks: [{ chunkId: 'editor-active', priority: 0 }],
    instances: [{
      instanceId: 'editor:active-blueprint',
      blueprintId: 'active',
      chunkId: 'editor-active',
      transform: { position: [0, 0, 0] },
    }],
    materialLibraries: options.materialLibraries,
    renderProfile: options.renderProfile,
    environment: options.environment,
  }
}

export function serializeWorldDocument(document: WorldDocument): string {
  assertWorldDocument(document)
  return JSON.stringify(document, null, 2)
}

export function parseWorldDocument(input: string | unknown): WorldDocument {
  const value = typeof input === 'string' ? JSON.parse(input) : structuredClone(input)
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('世界文档必须是对象')
  rejectExecutableFields(value, '$')
  const document = value as WorldDocument
  assertWorldDocument(document)
  return document
}

export function saveWorldDocument(document: WorldDocument): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${document.worldId}`, serializeWorldDocument(document))
  } catch {
    // 当前会话继续运行；持久化配额或隐私模式不应中断渲染。
  }
}

export function loadWorldDocument(worldId: string): WorldDocument | undefined {
  if (typeof localStorage === 'undefined') return undefined
  try {
    const value = localStorage.getItem(`${STORAGE_PREFIX}${worldId}`)
    return value ? parseWorldDocument(value) : undefined
  } catch {
    return undefined
  }
}

export function removeWorldDocument(worldId: string): void {
  if (typeof localStorage === 'undefined') return
  try { localStorage.removeItem(`${STORAGE_PREFIX}${worldId}`) } catch { /* ignore */ }
}

function assertWorldDocument(document: WorldDocument): void {
  const issues = validateWorldDocument(document)
  if (issues.length) throw new Error(`Invalid world document: ${issues.join('; ')}`)
}

function rejectExecutableFields(value: unknown, path: string): void {
  if (Array.isArray(value)) {
    value.forEach((child, index) => rejectExecutableFields(child, `${path}[${index}]`))
    return
  }
  if (!value || typeof value !== 'object') return
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (/^(shader(source|code)?|vertexshader|fragmentshader|glsl|wgsl|script|javascript|code)$/i.test(key)) {
      throw new Error(`${path}.${key} 不允许携带可执行代码`)
    }
    rejectExecutableFields(child, `${path}.${key}`)
  }
}
