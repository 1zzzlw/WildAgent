/**
 * MeshData 到 Three.js BufferGeometry 转换器
 * 
 * 将 wild-core 输出的 MeshData 转换为 Three.js 可以渲染的 BufferGeometry：
 * - geometry (Float32Array) -> position attribute
 * - indices (Uint32Array) -> index
 * - normals (Float32Array) -> normal attribute
 * - vertexColors (Float32Array) -> color attribute
 * 
 * 使用方式：
 * ```ts
 * const geometry = meshDataToGeometry(meshData)
 * const material = new THREE.MeshStandardMaterial()
 * const mesh = new THREE.Mesh(geometry, material)
 * ```
 */

import * as THREE from 'three'
import type { MeshData } from '../types/scene'

/**
 * 将 MeshData 转换为 Three.js BufferGeometry
 * 
 * @param meshData - wild-core 输出的网格数据
 * @returns THREE.BufferGeometry
 */
export function meshDataToGeometry(meshData: MeshData): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry()
  
  // 1. 设置顶点位置
  // MeshData.geometry 是 Float32Array [x,y,z, x,y,z, ...]
  geometry.setAttribute('position', new THREE.BufferAttribute(meshData.geometry, 3))
  
  // 2. 设置索引（如果有）
  if (meshData.indices) {
    geometry.setIndex(new THREE.BufferAttribute(meshData.indices, 1))
  }
  
  // 3. 设置法线（如果有）
  if (meshData.normals) {
    geometry.setAttribute('normal', new THREE.BufferAttribute(meshData.normals, 3))
  } else {
    // 如果没有法线，自动计算
    geometry.computeVertexNormals()
  }
  
  // 4. 设置顶点颜色（如果有）
  // wild-core 会生成程序化颜色（木纹、石材纹理、苔藓等）
  if (meshData.vertexColors) {
    // WILD 中所有数值颜色均按 sRGB authored value 表达；Three.js 顶点色
    // 必须处于线性工作空间。转换副本，避免修改 core 的确定性输出。
    const linearColors = new Float32Array(meshData.vertexColors.length)
    const color = new THREE.Color()
    for (let i = 0; i < meshData.vertexColors.length; i += 3) {
      color.setRGB(
        meshData.vertexColors[i],
        meshData.vertexColors[i + 1],
        meshData.vertexColors[i + 2],
        THREE.SRGBColorSpace,
      )
      linearColors[i] = color.r
      linearColors[i + 1] = color.g
      linearColors[i + 2] = color.b
    }
    geometry.setAttribute('color', new THREE.BufferAttribute(linearColors, 3))
  }

  if (meshData.uvs) {
    const uvAttribute = new THREE.BufferAttribute(meshData.uvs, 2)
    geometry.setAttribute('uv', uvAttribute)
    // 不同 Three.js 小版本分别使用 uv1 / uv2 表示第二套 UV；两者都提供，
    // 当前 WILD v1.1 复用主 UV，确保 aoMap 在部署版本中稳定生效。
    geometry.setAttribute('uv1', uvAttribute.clone())
    geometry.setAttribute('uv2', uvAttribute.clone())
  }
  
  // 5. 计算边界球（用于视锥体剔除优化）
  geometry.computeBoundingSphere()
  geometry.computeBoundingBox()
  
  return geometry
}

/**
 * 批量转换多个 MeshData
 * 
 * @param meshDataArray - MeshData 数组
 * @returns BufferGeometry 数组
 */
export function batchMeshDataToGeometry(meshDataArray: MeshData[]): THREE.BufferGeometry[] {
  return meshDataArray.map(meshData => meshDataToGeometry(meshData))
}
