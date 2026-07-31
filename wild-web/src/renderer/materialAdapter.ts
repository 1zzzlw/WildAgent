/**
 * 材质适配器：wild-core MaterialParams -> Three.js Material
 * 
 * 将 wild-core 输出的材质参数转换为 Three.js 材质：
 * - baseColor -> color
 * - roughness, metallic -> MeshStandardMaterial 参数
 * - opacity -> transparent + opacity
 * - emissive -> emissive + emissiveIntensity
 * 
 * 使用方式：
 * ```ts
 * const material = createMaterialFromParams(materialParams, hasVertexColors)
 * const mesh = new THREE.Mesh(geometry, material)
 * ```
 */

import * as THREE from 'three'

/**
 * wild-core 材质参数（简化版）
 */
export interface MaterialParams {
  baseColor: [number, number, number]
  roughness: number
  metallic: number
  albedo: number
  emissive?: [number, number, number]
  opacity?: number
  effects?: unknown[]
  lightingCondition?: string
  embeddedImage?: EmbeddedImageData
  textures?: {
    baseColor?: EmbeddedImageData
    normal?: EmbeddedImageData
    roughness?: EmbeddedImageData
    metalness?: EmbeddedImageData
    ambientOcclusion?: EmbeddedImageData
  }
  normalScale?: number
  uvScale?: [number, number]
}

interface EmbeddedImageData {
  encoding: 'base64'
  mimeType: string
  data: string
}

/**
 * 从 MaterialParams 创建 Three.js 材质
 * 
 * @param params - wild-core 的材质参数
 * @param hasVertexColors - 网格是否包含顶点颜色
 * @returns THREE.MeshStandardMaterial
 */
export function createMaterialFromParams(
  params: MaterialParams,
  hasVertexColors: boolean = false
): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial()
  const baseTexture = params.textures?.baseColor || params.embeddedImage
  
  // 1. 基础颜色
  const [r, g, b] = params.baseColor
  // 顶点色由 core 烘焙为绝对颜色；纹理也携带自身颜色。两种情况下
  // material.color 使用白色，避免 baseColor 被重复相乘导致画面偏暗。
  material.color = hasVertexColors || baseTexture
    ? new THREE.Color(1, 1, 1)
    : new THREE.Color()
        .setRGB(r, g, b, THREE.SRGBColorSpace)
        .multiplyScalar(params.albedo ?? 1)
  
  // 2. 粗糙度和金属度
  material.roughness = params.roughness
  material.metalness = params.metallic
  
  // 3. 透明度（只有明确半透明时才开启，避免影响深度排序）
  const isTransparent = params.opacity !== undefined && params.opacity < 0.99
  if (isTransparent) {
    material.transparent = true
    material.opacity = params.opacity!
    material.depthWrite = false  // 半透明物体不写深度，避免遮挡后面的半透明物体
  } else {
    material.transparent = false
    material.depthWrite = true   // 不透明物体必须写深度，保证正确遮挡
  }

  // 4. 自发光
  if (params.emissive) {
    const [er, eg, eb] = params.emissive
    material.emissive = new THREE.Color().setRGB(
      er,
      eg,
      eb,
      THREE.SRGBColorSpace,
    )
    material.emissiveIntensity = 1.0
  }

  // 5. 顶点颜色
  if (hasVertexColors) {
    material.vertexColors = true
  }

  // 6. 内嵌 PBR 纹理。TextureLoader 可直接读取 data URL，加载完成后
  // Three.js 会自动触发材质更新，不阻塞场景重建。
  if (baseTexture) material.map = createEmbeddedTexture(baseTexture, true, params.uvScale)
  if (params.textures?.normal) {
    material.normalMap = createEmbeddedTexture(params.textures.normal, false, params.uvScale)
    const normalScale = params.normalScale ?? 1
    material.normalScale.set(normalScale, normalScale)
  }
  if (params.textures?.roughness) {
    material.roughnessMap = createEmbeddedTexture(params.textures.roughness, false, params.uvScale)
  }
  if (params.textures?.metalness) {
    material.metalnessMap = createEmbeddedTexture(params.textures.metalness, false, params.uvScale)
  }
  if (params.textures?.ambientOcclusion) {
    material.aoMap = createEmbeddedTexture(params.textures.ambientOcclusion, false, params.uvScale)
  }

  // 7. 双面渲染：兼容当前仍包含单面网格的旧构建器。
  material.side = THREE.DoubleSide
  
  return material
}

/**
 * 创建材质缓存
 * 相同参数的材质可以复用，节省内存
 */
export class MaterialCache {
  private cache = new Map<string, THREE.MeshStandardMaterial>()
  private currentKeyBySlot = new Map<string, string>()
  
  /**
   * 获取或创建材质
   * @param materialName - 材质名称
   * @param params - 材质参数
   * @param hasVertexColors - 是否有顶点颜色
   */
  getOrCreate(
    materialName: string,
    params: MaterialParams,
    hasVertexColors: boolean
  ): THREE.MeshStandardMaterial {
    const slot = `${materialName}_${hasVertexColors}`
    const key = `${slot}_${materialSignature(params)}`
    const oldKey = this.currentKeyBySlot.get(slot)

    if (oldKey && oldKey !== key) {
      const stale = this.cache.get(oldKey)
      if (stale) disposeMaterial(stale)
      this.cache.delete(oldKey)
    }
    
    if (!this.cache.has(key)) {
      const material = createMaterialFromParams(params, hasVertexColors)
      material.name = materialName
      this.cache.set(key, material)
    }
    this.currentKeyBySlot.set(slot, key)
    
    return this.cache.get(key)!
  }
  
  /**
   * 清空缓存（场景切换时调用）
   */
  clear() {
    this.cache.forEach(disposeMaterial)
    this.cache.clear()
    this.currentKeyBySlot.clear()
  }
  
  /**
   * 获取缓存的材质数量
   */
  get size() {
    return this.cache.size
  }
}

function createEmbeddedTexture(
  image: EmbeddedImageData,
  isColorTexture: boolean,
  uvScale: [number, number] = [1, 1],
): THREE.Texture {
  const url = `data:${image.mimeType};base64,${image.data}`
  const texture = new THREE.TextureLoader().load(url)
  texture.colorSpace = isColorTexture ? THREE.SRGBColorSpace : THREE.NoColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(uvScale[0], uvScale[1])
  texture.anisotropy = 4
  return texture
}

function materialSignature(params: MaterialParams): string {
  const imageSignature = (image?: EmbeddedImageData) =>
    image ? `${image.mimeType}:${hashString(image.data)}` : ''
  return JSON.stringify({
    baseColor: params.baseColor,
    roughness: params.roughness,
    metallic: params.metallic,
    albedo: params.albedo,
    emissive: params.emissive,
    opacity: params.opacity,
    normalScale: params.normalScale,
    uvScale: params.uvScale,
    embeddedImage: imageSignature(params.embeddedImage),
    textures: params.textures && {
      baseColor: imageSignature(params.textures.baseColor),
      normal: imageSignature(params.textures.normal),
      roughness: imageSignature(params.textures.roughness),
      metalness: imageSignature(params.textures.metalness),
      ambientOcclusion: imageSignature(params.textures.ambientOcclusion),
    },
  })
}

function hashString(value: string): string {
  let hash = 2166136261
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16)
}

function disposeMaterial(material: THREE.MeshStandardMaterial): void {
  material.map?.dispose()
  material.normalMap?.dispose()
  material.roughnessMap?.dispose()
  material.metalnessMap?.dispose()
  material.aoMap?.dispose()
  material.dispose()
}
