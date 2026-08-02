import type { Blueprint } from '../types/blueprint'
import type { ReconstructedEntity } from '../types/scene'
import { deepClone } from '../utils/common'
import { reconstructWildEntity } from './wildCoreAdapter'

interface PendingRequest {
  resolve: (entity: ReconstructedEntity) => void
  reject: (error: Error) => void
}

let worker: Worker | null = null
let nextRequestId = 1
const pending = new Map<number, PendingRequest>()

/** 大场景在 Web Worker 中重建；测试或不支持 Worker 的环境自动使用同步 Core。 */
export async function reconstructScene(
  blueprint: Blueprint,
): Promise<ReconstructedEntity> {
  if (typeof Worker === 'undefined') {
    return reconstructWildEntity(blueprint)
  }
  // Pinia/Vue 会把 Blueprint 及其嵌套对象转换为 Proxy；Proxy 不能通过
  // Worker.postMessage 的结构化克隆。WILD 本身是 JSON 格式，因此在 Worker
  // 边界生成一次纯 JSON 快照，既解除响应式包装，也冻结本次重建的输入。
  const workerBlueprint = deepClone(blueprint)
  const activeWorker = getWorker()
  const requestId = nextRequestId++
  return new Promise<ReconstructedEntity>((resolve, reject) => {
    pending.set(requestId, { resolve, reject })
    try {
      activeWorker.postMessage({ requestId, blueprint: workerBlueprint })
    } catch (error) {
      // postMessage 是同步抛错；及时清理请求，避免 pending 永久残留。
      pending.delete(requestId)
      reject(error instanceof Error ? error : new Error(String(error)))
    }
  })
}

function getWorker(): Worker {
  if (worker) return worker
  worker = new Worker(new URL('../workers/reconstruction.worker.ts', import.meta.url), { type: 'module' })
  worker.addEventListener('message', (event: MessageEvent<{
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
  worker.addEventListener('error', event => {
    const error = new Error(event.message || '场景重建 Worker 失败')
    for (const request of pending.values()) request.reject(error)
    pending.clear()
    worker?.terminate()
    worker = null
  })
  return worker
}
