import type { MeshData } from '../types/scene'

const typedArrayHashCache = new WeakMap<Float32Array | Uint32Array, number>()

/** 重建后的几何只读；Worker 和同步渲染入口使用相同的复用规则。 */
export function meshSignature(meshData: MeshData): string {
  if (meshData.renderSignature !== undefined) return meshData.renderSignature
  return [
    meshData.materialRef,
    meshData.geometry.length,
    meshData.indices?.length || 0,
    meshData.vertexColors ? 1 : 0,
    hashTypedArray(meshData.geometry),
    meshData.indices ? hashTypedArray(meshData.indices) : 0,
    meshData.normals ? hashTypedArray(meshData.normals) : 0,
    meshData.uvs ? hashTypedArray(meshData.uvs) : 0,
    meshData.vertexColors ? hashTypedArray(meshData.vertexColors) : 0,
  ].join(':')
}

function hashTypedArray(array: Float32Array | Uint32Array): number {
  const cached = typedArrayHashCache.get(array)
  if (cached !== undefined) return cached
  let hash = 2166136261
  const words = array instanceof Float32Array
    ? new Uint32Array(array.buffer, array.byteOffset, array.length)
    : array
  for (let index = 0; index < words.length; index++) {
    hash ^= words[index]!
    hash = Math.imul(hash, 16777619)
  }
  const result = hash >>> 0
  typedArrayHashCache.set(array, result)
  return result
}
