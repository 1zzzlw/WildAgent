import type { Blueprint } from '../types/blueprint'
import type { ReconstructedEntity } from '../types/scene'
import { reconstructWildEntity } from './wildCoreAdapter'

interface PendingRequest {
  resolve: (entity: ReconstructedEntity) => void
  reject: (error: Error) => void
}

let worker: Worker | null = null
let nextRequestId = 1
const pending = new Map<number, PendingRequest>()
const inFlight = new Map<string, Promise<ReconstructedEntity>>()
const cache = new Map<string, { entity: ReconstructedEntity; bytes: number }>()
const MAX_CACHE_ENTRIES = 3
const MAX_CACHE_BYTES = 128 * 1024 * 1024
let cacheBytes = 0

export function clearReconstructionCache(): void {
  cache.clear()
  cacheBytes = 0
}

/** 已离开的会话不再占用 Worker；下一次请求按需重建 Worker。 */
export function cancelPendingReconstruction(): void {
  if (!pending.size) return
  worker?.terminate()
  worker = null
  for (const request of pending.values()) {
    request.reject(new DOMException('场景加载已取消', 'AbortError'))
  }
  pending.clear()
  inFlight.clear()
}

/** 大场景在 Web Worker 中重建；测试或不支持 Worker 的环境自动使用同步 Core。 */
export async function reconstructScene(
  blueprint: Blueprint,
): Promise<ReconstructedEntity> {
  if (typeof Worker === 'undefined') {
    return reconstructWildEntity(blueprint)
  }
  // Pinia/Vue 会把 Blueprint 及其嵌套对象转换为 Proxy；Proxy 不能通过
  // Worker.postMessage 的结构化克隆。WILD 本身是 JSON 格式，因此在 Worker
  // 边界生成 JSON 快照；解析留在 Worker，避免主线程解析后再结构化克隆整棵对象树。
  const blueprintJson = JSON.stringify(blueprint)
  const cached = cache.get(blueprintJson)
  if (cached) {
    cache.delete(blueprintJson)
    cache.set(blueprintJson, cached)
    return cached.entity
  }
  const existing = inFlight.get(blueprintJson)
  if (existing) return existing
  const activeWorker = getWorker()
  const requestId = nextRequestId++
  const result = new Promise<ReconstructedEntity>((resolve, reject) => {
    pending.set(requestId, { resolve, reject })
    try {
      activeWorker.postMessage({ requestId, blueprintJson })
    } catch (error) {
      // postMessage 是同步抛错；及时清理请求，避免 pending 永久残留。
      pending.delete(requestId)
      reject(error instanceof Error ? error : new Error(String(error)))
    }
  })
  inFlight.set(blueprintJson, result)
  try {
    const entity = await result
    remember(blueprintJson, entity)
    return entity
  } finally {
    if (inFlight.get(blueprintJson) === result) inFlight.delete(blueprintJson)
  }
}

function remember(blueprintJson: string, entity: ReconstructedEntity): void {
  // 限制蓝图文本和几何缓冲区的占用，同时限制对象数量；超大场景不常驻缓存。
  const buffers = new Set<ArrayBufferLike>()
  let bytes = blueprintJson.length * 2 + JSON.stringify(entity.materialParams).length * 2
  for (const mesh of entity.meshes) {
    bytes += 512
    for (const array of [mesh.geometry, mesh.indices, mesh.normals, mesh.uvs, mesh.vertexColors]) {
      if (!array || buffers.has(array.buffer)) continue
      buffers.add(array.buffer)
      bytes += array.buffer.byteLength
    }
  }
  if (bytes > MAX_CACHE_BYTES) return
  cache.set(blueprintJson, { entity, bytes })
  cacheBytes += bytes
  while (cache.size > MAX_CACHE_ENTRIES || cacheBytes > MAX_CACHE_BYTES) {
    const oldest = cache.keys().next().value!
    cacheBytes -= cache.get(oldest)!.bytes
    cache.delete(oldest)
  }
}

function getWorker(): Worker {
  if (worker) return worker
  const activeWorker = new Worker(new URL('../workers/reconstruction.worker.ts', import.meta.url), { type: 'module' })
  worker = activeWorker
  activeWorker.addEventListener('message', (event: MessageEvent<{
    requestId: number
    entity?: ReconstructedEntity
    error?: string
  }>) => {
    const request = pending.get(event.data.requestId)
    if (!request) return
    pending.delete(event.data.requestId)
    if (event.data.entity) request.resolve(event.data.entity)
    else request.reject(new Error(event.data.error || '场景重建 Worker 返回空结果'))
  })
  activeWorker.addEventListener('error', event => {
    if (worker !== activeWorker) return
    const error = new Error(event.message || '场景重建 Worker 失败')
    for (const request of pending.values()) request.reject(error)
    pending.clear()
    activeWorker.terminate()
    worker = null
  })
  return worker
}
