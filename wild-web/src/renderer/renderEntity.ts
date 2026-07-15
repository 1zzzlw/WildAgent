/**
 * 渲染实体转换器
 * 
 * 将 wild-core 的 ReconstructedEntity 转换为 Three.js 场景对象：
 * - 每个 MeshData -> THREE.Mesh
 * - MaterialParams -> THREE.MeshStandardMaterial
 * - 组合成 THREE.Group
 * 
 * 使用方式：
 * ```ts
 * const sceneGroup = createSceneGroupFromEntity(entity)
 * threeScene.add(sceneGroup)
 * ```
 */

import * as THREE from 'three'
import type { ReconstructedEntity, MeshData } from '../types/scene'
import { MaterialCache } from './materialAdapter'

/**
 * 将 wild-core 的 MeshData 转换为 Three.js Mesh
 * 
 * @param meshData - wild-core 输出的网格数据
 * @param materialCache - 材质缓存
 * @param materialParams - 材质参数数组
 * @param materialIndex - 当前网格对应的材质索引
 */
function createMeshFromMeshData(
  meshData: MeshData,
  materialCache: MaterialCache,
  materialParams: any[],
  materialIndex: number
): THREE.Mesh {
  // 1. 转换几何数据
  // 注意：wild-core 的 MeshData.geometry 实际上是顶点位置
  const geometry = new THREE.BufferGeometry()
  
  // wild-core实际输出的字段是geometry(不是positions)
  const positions = (meshData as any).geometry || meshData.positions
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  
  if (meshData.indices) {
    geometry.setIndex(new THREE.BufferAttribute(meshData.indices, 1))
  }
  
  if (meshData.normals) {
    geometry.setAttribute('normal', new THREE.BufferAttribute(meshData.normals, 3))
  } else {
    geometry.computeVertexNormals()
  }
  
  // wild-core实际输出的字段是vertexColors(不是colors)
  const colors = (meshData as any).vertexColors || meshData.colors
  if (colors) {
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  }
  
  geometry.computeBoundingSphere()
  
  // 2. 获取或创建材质
  const matParams = materialParams[materialIndex]
  const hasVertexColors = !!colors
  const material = matParams
    ? materialCache.getOrCreate(meshData.materialRef, matParams, hasVertexColors)
    : new THREE.MeshStandardMaterial({ color: 0x808080 }) // 默认灰色
  
  // 3. 创建 Mesh
  const mesh = new THREE.Mesh(geometry, material)
  
  // 4. 应用 transform
  if (meshData.transform) {
    const { position, rotation, scale } = meshData.transform
    mesh.position.set(position[0], position[1], position[2])
    mesh.rotation.set(rotation[0], rotation[1], rotation[2])
    mesh.scale.set(scale[0], scale[1], scale[2])
  }
  
  // 5. 设置阴影
  mesh.castShadow = true
  mesh.receiveShadow = true
  
  // 6. 存储元数据
  mesh.userData.elementId = meshData.elementId
  mesh.userData.materialRef = meshData.materialRef
  mesh.userData.interactive = meshData.interactive || false
  
  // 7. 设置名称（用于调试和选择）
  mesh.name = meshData.elementId || 'unnamed'
  
  return mesh
}

/**
 * 从 ReconstructedEntity 创建 Three.js Group
 * 
 * @param entity - wild-core 重建的实体
 * @param materialCache - 材质缓存（可选，不传则创建新的）
 * @returns THREE.Group 包含所有网格的场景组
 */
export function createSceneGroupFromEntity(
  entity: ReconstructedEntity,
  materialCache?: MaterialCache
): THREE.Group {
  const group = new THREE.Group()
  group.name = 'WildScene'
  
  const cache = materialCache || new MaterialCache()
  
  // 转换所有网格
  entity.meshes.forEach((meshData, index) => {
    try {
      const mesh = createMeshFromMeshData(
        meshData,
        cache,
        entity.materialParams || [],
        index
      )
      group.add(mesh)
    } catch (error) {
      console.error('创建 mesh 失败', meshData, error)
    }
  })
  
  // 存储边界盒信息
  if (entity.boundingBox) {
    group.userData.boundingBox = entity.boundingBox
  }
  
  console.log(`场景组创建成功: ${entity.meshes.length} 个网格, ${cache.size} 个材质`)
  
  return group
}

/**
 * 更新现有场景组
 * 
 * 清空旧对象并添加新对象
 * 
 * @param group - 要更新的 THREE.Group
 * @param entity - 新的 ReconstructedEntity
 * @param materialCache - 材质缓存
 */
export function updateSceneGroup(
  group: THREE.Group,
  entity: ReconstructedEntity,
  materialCache: MaterialCache
): void {
  // 清空旧对象
  while (group.children.length > 0) {
    const child = group.children[0]
    group.remove(child)
    
    // 释放资源
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose()
      // 注意：材质由 materialCache 管理，不在这里释放
    }
  }
  
  // 添加新对象
  entity.meshes.forEach((meshData, index) => {
    try {
      const mesh = createMeshFromMeshData(
        meshData,
        materialCache,
        entity.materialParams || [],
        index
      )
      group.add(mesh)
    } catch (error) {
      console.error('创建 mesh 失败', meshData, error)
    }
  })
  
  // 更新边界盒
  if (entity.boundingBox) {
    group.userData.boundingBox = entity.boundingBox
  }
  
  console.log(`场景组更新成功: ${entity.meshes.length} 个网格`)
}
