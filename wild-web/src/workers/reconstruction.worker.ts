/// <reference lib="webworker" />

import type { Blueprint } from '../types/blueprint'
import { reconstructWildEntity } from '../renderer/wildCoreAdapter'
import { meshSignature } from '../renderer/meshSignature'

interface ReconstructionRequest {
  requestId: number
  blueprintJson: string
}

self.addEventListener('message', async (event: MessageEvent<ReconstructionRequest>) => {
  const { requestId, blueprintJson } = event.data
  try {
    const blueprint = JSON.parse(blueprintJson) as Blueprint
    const entity = await reconstructWildEntity(blueprint)
    // 几何不变的复用键需要逐个扫描顶点；在传输前计算，避免阻塞视口主线程。
    for (const mesh of entity.meshes) mesh.renderSignature = meshSignature(mesh)
    const transfers = collectTransferables(entity)
    self.postMessage({ requestId, entity }, { transfer: transfers })
  } catch (error) {
    self.postMessage({
      requestId,
      error: error instanceof Error ? error.message : String(error),
    })
  }
})

function collectTransferables(entity: Awaited<ReturnType<typeof reconstructWildEntity>>): ArrayBuffer[] {
  const buffers = new Set<ArrayBuffer>()
  for (const mesh of entity.meshes) {
    for (const array of [mesh.geometry, mesh.indices, mesh.normals, mesh.uvs, mesh.vertexColors]) {
      if (array?.buffer instanceof ArrayBuffer) buffers.add(array.buffer)
    }
  }
  return [...buffers]
}
