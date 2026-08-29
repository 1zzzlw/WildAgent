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
import { KTX2Loader } from 'three/examples/jsm/loaders/KTX2Loader.js'
import type { EmbeddedImageData, TextureImageData } from '../types/blueprint'
import type { ProceduralMaterial } from '../wild-core/types'
import type { RenderMaterialDescriptor } from '../wild-core/src/materials'
import { recordTextureLoad } from './textureLoadMonitor'
import { applyRegisteredSurfaceMaterial } from './materialFeatures'
import { worldMaterialRuntime } from './worldMaterialRuntime'

let textureAnisotropy = 4
let requestMaterialRender: () => void = () => { }
let ktx2Loader: KTX2Loader | null = null

export type PBRMaterial = THREE.MeshStandardMaterial | THREE.MeshPhysicalMaterial

type TextureFactory = (
  image: TextureImageData,
  channel: string,
  isColorTexture: boolean,
  uvScale?: [number, number],
) => THREE.Texture

/** 使用当前 GPU 能力设置纹理过滤上限，避免在低端设备上硬编码高采样。 */
export function configureMaterialRendering(
  maxAnisotropy: number,
  invalidate: () => void = () => { },
): void {
  textureAnisotropy = Math.max(1, Math.min(16, Math.floor(maxAnisotropy || 1)))
  requestMaterialRender = invalidate
}

export function configureKtx2Rendering(
  renderer: THREE.WebGLRenderer,
  transcoderPath = '/basis/',
): void {
  ktx2Loader?.dispose()
  ktx2Loader = new KTX2Loader()
    .setTranscoderPath(transcoderPath)
    .detectSupport(renderer)
}

export function disposeKtx2Rendering(): void {
  ktx2Loader?.dispose()
  ktx2Loader = null
}

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
    baseColor?: TextureImageData
    normal?: TextureImageData
    roughness?: TextureImageData
    metalness?: TextureImageData
    ambientOcclusion?: TextureImageData
  }
  normalScale?: number
  uvScale?: [number, number]
  materialClass?: 'standard' | 'glass' | 'clearcoat' | 'fabric'
  side?: 'front' | 'double'
  transmission?: number
  ior?: number
  thickness?: number
  attenuationColor?: [number, number, number]
  attenuationDistance?: number
  clearcoat?: number
  clearcoatRoughness?: number
  sheen?: number
  sheenColor?: [number, number, number]
  emissiveIntensity?: number
  procedural?: ProceduralMaterial
  renderDescriptor?: RenderMaterialDescriptor
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
  hasVertexColors: boolean = false,
  textureFactory: TextureFactory = createTexture,
  materialName: string = 'material',
): PBRMaterial {
  // 只要是玻璃 / 清漆 / 布料材质，或者开启了透光、清漆涂层、sheen 光泽，就启用 PBR 物理材质；其他简单材质（普通哑光金属、基础漫反射等）就不走这个材质管线。
  const usePhysicalMaterial = params.materialClass === 'glass'
    || params.materialClass === 'clearcoat'
    || params.materialClass === 'fabric'
    || (params.transmission ?? 0) > 0
    || (params.clearcoat ?? 0) > 0
    || (params.sheen ?? 0) > 0
  const material: PBRMaterial = usePhysicalMaterial
    ? new THREE.MeshPhysicalMaterial()
    : new THREE.MeshStandardMaterial()
  const baseTexture = params.textures?.baseColor || params.embeddedImage

  // 1. 基础颜色
  const [r, g, b] = params.baseColor
  // 顶点色由 core 烘焙为绝对颜色；颜色贴图则允许与 baseColor 相乘，
  // 用作非破坏性的材质染色。默认 [1,1,1] 保持图片原色。
  material.color = hasVertexColors
    ? new THREE.Color(1, 1, 1)
    : new THREE.Color()
      .setRGB(r, g, b, THREE.SRGBColorSpace)
      .multiplyScalar(params.albedo ?? 1)

  // 2. 粗糙度和金属度
  material.roughness = params.roughness
  material.metalness = params.metallic
  // IBL 反射基准提高：非金属也有环境反射，金属/光滑面反射更亮；配合 scene.environmentIntensity。
  material.envMapIntensity = Math.min(1.8, 1.0 + params.metallic * 0.5)

  // 3. 透明度（只有明确半透明时才开启，避免影响深度排序）
  if (material instanceof THREE.MeshPhysicalMaterial) {
    const isGlass = params.materialClass === 'glass'
    material.transmission = params.transmission ?? (isGlass ? 0.92 : 0)
    material.ior = params.ior ?? (isGlass ? 1.5 : 1.5)
    material.thickness = params.thickness ?? (isGlass ? 0.012 : 0)
    material.attenuationDistance = params.attenuationDistance ?? (isGlass ? 6 : Infinity)
    if (params.attenuationColor || isGlass) {
      material.attenuationColor = new THREE.Color().setRGB(
        ...(params.attenuationColor ?? [0.82, 0.94, 1]),
        THREE.SRGBColorSpace,
      )
    }
    material.clearcoat = params.clearcoat ?? (isGlass ? 0.08 : 0)
    material.clearcoatRoughness = params.clearcoatRoughness ?? 0.12
    material.sheen = params.sheen ?? (params.materialClass === 'fabric' ? 0.35 : 0)
    if (params.sheenColor) {
      material.sheenColor = new THREE.Color().setRGB(
        ...params.sheenColor,
        THREE.SRGBColorSpace,
      )
    }
  }

  const usesTransmission = material instanceof THREE.MeshPhysicalMaterial
    && material.transmission > 0
  const isTransparent = !usesTransmission
    && params.opacity !== undefined
    && params.opacity < 0.99
  if (isTransparent) {
    material.transparent = true
    material.opacity = params.opacity!
    material.depthWrite = false  // 半透明物体不写深度，避免遮挡后面的半透明物体
    material.envMapIntensity = Math.max(material.envMapIntensity, 1.05)
  } else {
    material.transparent = false
    material.opacity = 1
    material.depthWrite = true   // 不透明/透射物体写深度，保证正确遮挡
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
    material.emissiveIntensity = params.emissiveIntensity ?? 1.0
  }

  // 5. 顶点颜色
  if (hasVertexColors) {
    material.vertexColors = true
  }

  // 6. 内嵌 PBR 纹理。TextureLoader 可直接读取 data URL，加载完成后
  // Three.js 会自动触发材质更新，不阻塞场景重建。
  if (baseTexture) material.map = textureFactory(baseTexture, 'baseColor', true, params.uvScale)
  if (params.textures?.normal) {
    material.normalMap = textureFactory(params.textures.normal, 'normal', false, params.uvScale)
    const normalScale = params.normalScale ?? 1
    material.normalScale.set(normalScale, normalScale)
  }
  if (params.textures?.roughness) {
    material.roughnessMap = textureFactory(params.textures.roughness, 'roughness', false, params.uvScale)
  }
  if (params.textures?.metalness) {
    material.metalnessMap = textureFactory(params.textures.metalness, 'metalness', false, params.uvScale)
  }
  if (params.textures?.ambientOcclusion) {
    material.aoMap = textureFactory(params.textures.ambientOcclusion, 'ambientOcclusion', false, params.uvScale)
  }

  // 7. core 只输出实现 ID 和参数，实际 Shader 通过 renderer 注册表选择。
  applyRegisteredSurfaceMaterial(material, materialName, params)

  // 8. 兼容既有开放网格与历史构件中不一致的面绕序，默认双面渲染。
  // 只有已经验证为封闭实体的材质才通过 side: 'front' 显式开启背面剔除。
  material.side = params.side === 'front' ? THREE.FrontSide : THREE.DoubleSide

  return material
}

/**
 * 创建材质缓存
 * 相同参数的材质可以复用，节省内存
 */
export class MaterialCache {
  private heldKeys = new Set<string>()
  private pendingKeys: Set<string> | null = null
  readonly scopeId: string

  constructor(scopeId: string = `material-scope-${cryptoRandomId()}`) {
    this.scopeId = scopeId
  }

  /** 开始一次蓝图重建；结束时只释放该蓝图已不再使用的材质。 */
  beginUpdate(): void {
    if (this.pendingKeys) throw new Error(`Material scope ${this.scopeId} is already updating`)
    this.pendingKeys = new Set<string>()
  }

  endUpdate(): void {
    if (!this.pendingKeys) return
    for (const key of this.heldKeys) {
      if (!this.pendingKeys.has(key)) globalMaterialResources.releaseMaterial(key)
    }
    this.heldKeys = this.pendingKeys
    this.pendingKeys = null
  }

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
  ): PBRMaterial {
    const key = `${hasVertexColors ? 'vertex-color' : 'uniform-color'}:${materialSignature(params)}`
    const target = this.pendingKeys || this.heldKeys
    const alreadyHeld = this.heldKeys.has(key) || this.pendingKeys?.has(key) === true
    if (!alreadyHeld) {
      globalMaterialResources.acquireMaterial(key, materialName, params, hasVertexColors)
    }
    target.add(key)
    return globalMaterialResources.getMaterial(key)
  }

  /**
   * 清空缓存（场景切换时调用）
   */
  clear() {
    for (const key of this.heldKeys) globalMaterialResources.releaseMaterial(key)
    if (this.pendingKeys) {
      for (const key of this.pendingKeys) {
        if (!this.heldKeys.has(key)) globalMaterialResources.releaseMaterial(key)
      }
    }
    this.heldKeys.clear()
    this.pendingKeys = null
  }

  /**
   * 获取缓存的材质数量
   */
  get size() {
    return this.heldKeys.size
  }
}

interface MaterialResourceEntry {
  material: PBRMaterial
  references: number
  textureKeys: string[]
}

interface TextureResourceEntry {
  texture: THREE.Texture
  references: number
}

class GlobalMaterialResourceRegistry {
  private materials = new Map<string, MaterialResourceEntry>()
  private textures = new Map<string, TextureResourceEntry>()

  acquireMaterial(
    key: string,
    materialName: string,
    params: MaterialParams,
    hasVertexColors: boolean,
  ): PBRMaterial {
    const existing = this.materials.get(key)
    if (existing) {
      existing.references++
      return existing.material
    }

    const textureKeys: string[] = []
    try {
      const material = createMaterialFromParams(
        params,
        hasVertexColors,
        (image, channel, isColorTexture, uvScale) => {
          const acquired = this.acquireTexture(image, channel, isColorTexture, uvScale)
          textureKeys.push(acquired.key)
          return acquired.texture
        },
        materialName,
      )
      material.name = materialName
      this.materials.set(key, { material, references: 1, textureKeys })
      return material
    } catch (error) {
      textureKeys.forEach(textureKey => this.releaseTexture(textureKey))
      throw error
    }
  }

  getMaterial(key: string): PBRMaterial {
    const entry = this.materials.get(key)
    if (!entry) throw new Error(`Global material resource is missing: ${key}`)
    return entry.material
  }

  releaseMaterial(key: string): void {
    const entry = this.materials.get(key)
    if (!entry) return
    entry.references--
    if (entry.references > 0) return
    disposeMaterial(entry.material, false)
    entry.textureKeys.forEach(textureKey => this.releaseTexture(textureKey))
    this.materials.delete(key)
  }

  getStats(): GlobalMaterialResourceStats {
    return {
      materials: this.materials.size,
      textures: this.textures.size,
      materialReferences: [...this.materials.values()]
        .reduce((sum, entry) => sum + entry.references, 0),
      textureReferences: [...this.textures.values()]
        .reduce((sum, entry) => sum + entry.references, 0),
    }
  }

  private acquireTexture(
    image: TextureImageData,
    channel: string,
    isColorTexture: boolean,
    uvScale: [number, number] = [1, 1],
  ): { key: string; texture: THREE.Texture } {
    const source = image.encoding === 'url'
      ? `${image.uri}:${image.sha256}`
      : `${image.mimeType}:${hashString(image.data)}`
    const key = `${source}:${channel}:${isColorTexture ? 'srgb' : 'linear'}:${uvScale.join(',')}`
    const existing = this.textures.get(key)
    if (existing) {
      existing.references++
      return { key, texture: existing.texture }
    }
    const texture = createTexture(image, channel, isColorTexture, uvScale)
    this.textures.set(key, { texture, references: 1 })
    return { key, texture }
  }

  private releaseTexture(key: string): void {
    const entry = this.textures.get(key)
    if (!entry) return
    entry.references--
    if (entry.references > 0) return
    entry.texture.dispose()
    this.textures.delete(key)
  }
}

export interface GlobalMaterialResourceStats {
  materials: number
  textures: number
  materialReferences: number
  textureReferences: number
}

const globalMaterialResources = new GlobalMaterialResourceRegistry()

export function getGlobalMaterialResourceStats(): GlobalMaterialResourceStats {
  return globalMaterialResources.getStats()
}

function cryptoRandomId(): string {
  return typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : Math.random().toString(36).slice(2)
}

function createTexture(
  image: TextureImageData,
  channel: string,
  isColorTexture: boolean,
  uvScale: [number, number] = [1, 1],
): THREE.Texture {
  const stableUrl = image.encoding === 'url' ? image.uri : undefined
  const url = image.encoding === 'url'
    ? worldMaterialRuntime.resolvePackageUri(image.uri) || image.uri
    : `data:${image.mimeType};base64,${image.data}`
  if (image.encoding === 'url') recordTextureLoad(stableUrl!, channel, 'loading')
  if (image.mimeType === 'image/ktx2') {
    const placeholder = new THREE.CompressedTexture([], 1, 1, THREE.RGBA_S3TC_DXT5_Format)
    configureTextureSampling(placeholder, isColorTexture, uvScale)
    if (!ktx2Loader) {
      if (image.encoding === 'url') recordTextureLoad(stableUrl!, channel, 'error', 'KTX2 转码器尚未初始化')
      return placeholder
    }
    ktx2Loader.load(
      url,
      loaded => {
        placeholder.copy(loaded)
        configureTextureSampling(placeholder, isColorTexture, uvScale)
        placeholder.needsUpdate = true
        if (image.encoding === 'url') recordTextureLoad(stableUrl!, channel, 'loaded')
        requestMaterialRender()
      },
      undefined,
      error => {
        if (image.encoding === 'url') {
          const detail = error instanceof Error ? error.message : 'KTX2 解码失败'
          recordTextureLoad(stableUrl!, channel, 'error', detail)
        }
        requestMaterialRender()
      },
    )
    return placeholder
  }
  const texture = new THREE.TextureLoader().load(
    url,
    () => {
      if (image.encoding === 'url') recordTextureLoad(stableUrl!, channel, 'loaded')
      requestMaterialRender()
    },
    undefined,
    error => {
      if (image.encoding === 'url') {
        const detail = error instanceof Error ? error.message : 'HTTP 或图片解码失败'
        recordTextureLoad(stableUrl!, channel, 'error', detail)
      }
      requestMaterialRender()
    },
  )
  configureTextureSampling(texture, isColorTexture, uvScale)
  return texture
}

function configureTextureSampling(
  texture: THREE.Texture,
  isColorTexture: boolean,
  uvScale: [number, number],
): void {
  texture.colorSpace = isColorTexture ? THREE.SRGBColorSpace : THREE.NoColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(uvScale[0], uvScale[1])
  texture.anisotropy = textureAnisotropy
}

function materialSignature(params: MaterialParams): string {
  const imageSignature = (image?: TextureImageData) => {
    if (!image) return ''
    return image.encoding === 'url'
      ? `${image.uri}:${image.sha256}`
      : `${image.mimeType}:${hashString(image.data)}`
  }
  return JSON.stringify({
    baseColor: params.baseColor,
    roughness: params.roughness,
    metallic: params.metallic,
    albedo: params.albedo,
    emissive: params.emissive,
    emissiveIntensity: params.emissiveIntensity,
    opacity: params.opacity,
    normalScale: params.normalScale,
    uvScale: params.uvScale,
    materialClass: params.materialClass,
    side: params.side,
    transmission: params.transmission,
    ior: params.ior,
    thickness: params.thickness,
    attenuationColor: params.attenuationColor,
    attenuationDistance: params.attenuationDistance,
    clearcoat: params.clearcoat,
    clearcoatRoughness: params.clearcoatRoughness,
    sheen: params.sheen,
    sheenColor: params.sheenColor,
    procedural: params.procedural,
    renderDescriptor: params.renderDescriptor,
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

function disposeMaterial(material: PBRMaterial, disposeTextures = true): void {
  if (disposeTextures) {
    material.map?.dispose()
    material.normalMap?.dispose()
    material.roughnessMap?.dispose()
    material.metalnessMap?.dispose()
    material.aoMap?.dispose()
  }
  material.dispose()
}
