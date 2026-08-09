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
import type { LightElementBehavior } from '../wild-core/types'
import { MaterialCache } from './materialAdapter'
import { meshDataToGeometry } from './meshDataToGeometry'

const MAX_VERTICES = 50000

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
  // ── 顶点数保护：异常几何直接用占位 mesh 替代，防止浏览器卡死 ──
  if (meshData.geometry.length / 3 > MAX_VERTICES) {
    console.warn(
      `[renderEntity] ${meshData.elementId} 顶点数 ${meshData.geometry.length / 3} 超过上限 ${MAX_VERTICES}，` +
      `已替换为占位网格（可能是 opening 坐标错误导致几何爆炸）`
    )
    // 用一个小的红色线框 box 作为占位，让用户知道该构件有问题
    const placeholder = new THREE.Mesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshStandardMaterial({ color: 0xff4444, wireframe: true, transparent: true, opacity: 0.6 })
    )
    placeholder.name = meshData.elementId || 'unnamed'
    placeholder.userData.elementId  = meshData.elementId
    placeholder.userData.isError    = true
    placeholder.userData.errorReason = 'vertex_overflow'
    placeholder.userData.ownsMaterial = true
    const { position, rotation, scale } = meshData.transform
    placeholder.position.set(position[0], position[1], position[2])
    placeholder.rotation.set(rotation[0], rotation[1], rotation[2])
    return placeholder
  }

  // 1. 转换几何数据
  const geometry = meshDataToGeometry(meshData)
  
  // 2. 获取或创建材质
  const matParams = materialParams[materialIndex]
  const hasVertexColors = !!meshData.vertexColors
  let material = matParams
    ? materialCache.getOrCreate(meshData.materialRef, matParams, hasVertexColors)
    : new THREE.MeshStandardMaterial({ color: 0x808080 }) // 默认灰色
  if (meshData.interaction?.kind === 'light') material = material.clone()
  
  // 3. 创建 Mesh
  const mesh = new THREE.Mesh(geometry, material)
  
  // 4. 应用 transform
  const { position, rotation, scale } = meshData.transform
  mesh.position.set(position[0], position[1], position[2])
  mesh.rotation.set(rotation[0], rotation[1], rotation[2])
  mesh.scale.set(scale[0], scale[1], scale[2])
  
  // 5. 设置阴影
  mesh.castShadow = true
  mesh.receiveShadow = true
  
  // 6. 存储元数据
  mesh.userData.elementId = meshData.elementId
  mesh.userData.materialRef = meshData.materialRef
  mesh.userData.interactive = meshData.interactive || false
  mesh.userData.draggable = meshData.draggable || false
  if (meshData.interaction) {
    mesh.userData.interaction = {
      ...meshData.interaction,
      closedPosition: [...meshData.transform.position],
      closedRotation: [...meshData.transform.rotation],
    }
    if (meshData.interaction.kind === 'opening') {
      mesh.userData.interactionOpen = false
      if (meshData.interaction.initiallyOpen) setOpeningInteractionProgress(mesh, 1)
    } else {
      mesh.userData.ownsMaterial = true
      initializeLightInteraction(mesh, meshData.interaction)
    }
  }
  
  // 7. 设置名称（用于调试和选择）
  mesh.name = meshData.elementId || 'unnamed'
  
  return mesh
}

/** 右键命中门窗覆盖面时切换开合；动画每帧通知按需渲染器重绘。 */
export function toggleOpeningInteraction(
  object: THREE.Object3D,
  requestRender: () => void = () => {},
): boolean {
  if (
    !(object instanceof THREE.Mesh)
    || object.userData.interaction?.kind !== 'opening'
  ) return false
  const opening = object as THREE.Mesh
  const currentTarget = opening.userData.interactionTargetOpen
    ?? opening.userData.interactionOpen
    ?? false
  const targetOpen = !currentTarget
  const token = (opening.userData.interactionAnimationToken || 0) + 1
  opening.userData.interactionAnimationToken = token
  opening.userData.interactionTargetOpen = targetOpen
  const startedAt = performance.now()
  const from = opening.userData.interactionProgress || 0
  const to = targetOpen ? 1 : 0
  // 按剩余路程缩放时长，反向切换不会突然变慢；完整开合约 300ms。
  const duration = 300 * Math.max(0.15, Math.abs(to - from))

  const tick = (now: number) => {
    if (opening.userData.interactionAnimationToken !== token) return
    const linear = Math.min(1, (now - startedAt) / duration)
    const eased = linear * linear * (3 - 2 * linear)
    setOpeningInteractionProgress(opening, from + (to - from) * eased)
    requestRender()
    if (linear < 1) requestAnimationFrame(tick)
    else {
      opening.userData.interactionOpen = targetOpen
      opening.userData.interactionTargetOpen = targetOpen
    }
  }
  requestRender()
  requestAnimationFrame(tick)
  return true
}

/** 根据运行时交互类型分派右键操作。 */
export function toggleRuntimeInteraction(
  object: THREE.Object3D,
  requestRender: () => void = () => {},
): boolean {
  if (!(object instanceof THREE.Mesh)) return false
  if (object.userData.interaction?.kind === 'opening') {
    return toggleOpeningInteraction(object, requestRender)
  }
  if (object.userData.interaction?.kind === 'light') {
    return toggleLightInteraction(object, requestRender)
  }
  return false
}

/** 右键让灯具按“关闭 → 弱光 → 强光 → 关闭”循环，并平滑过渡亮度。 */
export function toggleLightInteraction(
  object: THREE.Object3D,
  requestRender: () => void = () => {},
): boolean {
  if (
    !(object instanceof THREE.Mesh)
    || object.userData.interaction?.kind !== 'light'
  ) return false
  const mesh = object as THREE.Mesh
  const interaction = mesh.userData.interaction as LightElementBehavior
  const currentTarget = mesh.userData.lightTargetLevel
    ?? mesh.userData.lightLevel
    ?? (interaction.initiallyOn ? 1 : 0)
  const targetLevel = (currentTarget + 1) % 3
  const from = currentLightIntensity(mesh)
  const to = lightIntensityAt(interaction, targetLevel)
  const token = (mesh.userData.lightAnimationToken || 0) + 1
  mesh.userData.lightAnimationToken = token
  mesh.userData.lightTargetLevel = targetLevel
  const startedAt = performance.now()
  const duration = 220

  const tick = (now: number) => {
    if (mesh.userData.lightAnimationToken !== token) return
    const linear = Math.min(1, (now - startedAt) / duration)
    const eased = linear * linear * (3 - 2 * linear)
    setLightIntensity(mesh, from + (to - from) * eased)
    requestRender()
    if (linear < 1) requestAnimationFrame(tick)
    else {
      mesh.userData.lightLevel = targetLevel
      mesh.userData.lightTargetLevel = targetLevel
    }
  }
  requestRender()
  requestAnimationFrame(tick)
  return true
}

function initializeLightInteraction(
  mesh: THREE.Mesh,
  interaction: LightElementBehavior,
): void {
  const color = new THREE.Color().setRGB(...interaction.color)
  const light = interaction.lightType === 'spot'
    ? new THREE.SpotLight(
        color,
        0,
        interaction.distance,
        THREE.MathUtils.degToRad(interaction.angle),
        0.35,
        1.5,
      )
    : new THREE.PointLight(color, 0, interaction.distance, 1.5)
  light.name = `${mesh.name || mesh.userData.elementId}:LightSource`
  light.userData.fixtureLight = true
  light.castShadow = false
  if (light instanceof THREE.SpotLight) {
    light.target.position.set(0, -1, 0)
    mesh.add(light.target)
  }
  mesh.add(light)
  const initialLevel = interaction.initiallyOn ? 1 : 0
  mesh.userData.lightLevel = initialLevel
  mesh.userData.lightTargetLevel = initialLevel
  setLightIntensity(mesh, lightIntensityAt(interaction, initialLevel))
}

function lightIntensityAt(interaction: LightElementBehavior, level: number): number {
  if (level === 1) return interaction.lowIntensity
  if (level === 2) return interaction.highIntensity
  return 0
}

function currentLightIntensity(mesh: THREE.Mesh): number {
  return findFixtureLight(mesh)?.intensity || 0
}

function setLightIntensity(mesh: THREE.Mesh, intensity: number): void {
  const light = findFixtureLight(mesh)
  if (light) light.intensity = Math.max(0, intensity)
  const interaction = mesh.userData.interaction as LightElementBehavior
  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
  for (const material of materials) {
    if (!(material instanceof THREE.MeshStandardMaterial)) continue
    material.emissive.setRGB(...interaction.color)
    material.emissiveIntensity = intensity <= 0
      ? 0.03
      : Math.min(2, 0.3 + intensity / Math.max(interaction.highIntensity, 1) * 1.4)
    material.needsUpdate = true
  }
}

function findFixtureLight(mesh: THREE.Mesh): THREE.Light | undefined {
  return mesh.children.find(child => child.userData.fixtureLight) as THREE.Light | undefined
}

function setOpeningInteractionProgress(mesh: THREE.Mesh, progress: number): void {
  const interaction = mesh.userData.interaction
  if (!interaction) return
  const value = Math.max(0, Math.min(1, progress))
  const closedPosition = interaction.closedPosition as [number, number, number]
  const closedRotation = interaction.closedRotation as [number, number, number]

  if (interaction.mode === 'swing' && interaction.openRotation) {
    const deltaY = (interaction.openRotation[1] - closedRotation[1]) * value
    const dx = closedPosition[0] - interaction.pivot[0]
    const dz = closedPosition[2] - interaction.pivot[2]
    const cosine = Math.cos(deltaY)
    const sine = Math.sin(deltaY)
    mesh.position.set(
      interaction.pivot[0] + dx * cosine + dz * sine,
      closedPosition[1],
      interaction.pivot[2] - dx * sine + dz * cosine,
    )
    mesh.rotation.set(
      closedRotation[0],
      closedRotation[1] + deltaY,
      closedRotation[2],
    )
  } else {
    const offset = interaction.openOffset || [0, 0, 0]
    mesh.position.set(
      closedPosition[0] + offset[0] * value,
      closedPosition[1] + offset[1] * value,
      closedPosition[2] + offset[2] * value,
    )
    mesh.rotation.fromArray(closedRotation)
  }
  mesh.userData.interactionProgress = value
  mesh.userData.interactionOpen = value >= 0.999
}

function createInstancedMesh(
  entries: Array<{ meshData: MeshData; materialIndex: number }>,
  materialCache: MaterialCache,
  materialParams: any[],
): THREE.InstancedMesh {
  const first = entries[0]
  const geometry = meshDataToGeometry(first.meshData)
  const params = materialParams[first.materialIndex]
  const material = params
    ? materialCache.getOrCreate(first.meshData.materialRef, params, !!first.meshData.vertexColors)
    : new THREE.MeshStandardMaterial({ color: 0x808080 })
  const instanced = new THREE.InstancedMesh(geometry, material, entries.length)
  const matrix = new THREE.Matrix4()
  const position = new THREE.Vector3()
  const quaternion = new THREE.Quaternion()
  const scale = new THREE.Vector3()
  const euler = new THREE.Euler()

  entries.forEach(({ meshData }, index) => {
    position.fromArray(meshData.transform.position)
    euler.set(
      meshData.transform.rotation[0],
      meshData.transform.rotation[1],
      meshData.transform.rotation[2],
      'XYZ',
    )
    quaternion.setFromEuler(euler)
    scale.fromArray(meshData.transform.scale)
    matrix.compose(position, quaternion, scale)
    instanced.setMatrixAt(index, matrix)
  })
  instanced.instanceMatrix.needsUpdate = true
  instanced.castShadow = true
  instanced.receiveShadow = true
  instanced.name = `Instanced:${first.meshData.materialRef}`
  instanced.userData.instanceElementIds = entries.map(entry => entry.meshData.elementId)
  instanced.userData.materialRef = first.meshData.materialRef
  return instanced
}

function populateSceneGroup(
  group: THREE.Group,
  entity: ReconstructedEntity,
  materialCache: MaterialCache,
): void {
  const buckets = new Map<string, Array<{ meshData: MeshData; materialIndex: number }>>()

  entity.meshes.forEach((meshData, materialIndex) => {
    const canInstance = !meshData.interactive && meshData.geometry.length / 3 <= MAX_VERTICES
    const key = canInstance
      ? meshSignature(meshData, entity.materialParams[materialIndex])
      : `single:${materialIndex}`
    const bucket = buckets.get(key) || []
    bucket.push({ meshData, materialIndex })
    buckets.set(key, bucket)
  })

  for (const entries of buckets.values()) {
    if (entries.length >= 3 && !entries[0].meshData.interactive) {
      try {
        group.add(createInstancedMesh(entries, materialCache, entity.materialParams))
        continue
      } catch (error) {
        console.warn('创建 InstancedMesh 失败，回退为普通 Mesh', error)
      }
    }
    for (const entry of entries) {
      try {
        group.add(createMeshFromMeshData(
          entry.meshData,
          materialCache,
          entity.materialParams,
          entry.materialIndex,
        ))
      } catch (error) {
        console.error('创建 mesh 失败', entry.meshData, error)
      }
    }
  }
}

function meshSignature(meshData: MeshData, params: any): string {
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
    JSON.stringify([
      params?.baseColor,
      params?.roughness,
      params?.metallic,
      params?.opacity,
    ]),
  ].join(':')
}

function hashTypedArray(array: Float32Array | Uint32Array): number {
  let hash = 2166136261
  const words = array instanceof Float32Array
    ? new Uint32Array(array.buffer, array.byteOffset, array.length)
    : array
  for (let index = 0; index < words.length; index++) {
    hash ^= words[index]
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
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
  
  populateSceneGroup(group, entity, cache)
  
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
      if (child.userData.ownsMaterial) {
        const materials = Array.isArray(child.material) ? child.material : [child.material]
        materials.forEach(material => material.dispose())
      }
      // 注意：材质由 materialCache 管理，不在这里释放
    }
  }
  
  populateSceneGroup(group, entity, materialCache)
  
  // 更新边界盒
  if (entity.boundingBox) {
    group.userData.boundingBox = entity.boundingBox
  }
  
  console.log(`场景组更新成功: ${entity.meshes.length} 个网格`)
}
