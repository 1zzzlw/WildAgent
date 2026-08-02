/// <reference lib="webworker" />

import type { Blueprint } from '../types/blueprint'
import { reconstructWildEntity } from '../renderer/wildCoreAdapter'

interface ReconstructionRequest {
  requestId: number
  blueprint: Blueprint
}

self.addEventListener('message', async (event: MessageEvent<ReconstructionRequest>) => {
  const { requestId, blueprint } = event.data
  try {
    const entity = await reconstructWildEntity(blueprint)
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
