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
  
  // 1. 基础颜色
  const [r, g, b] = params.baseColor
  material.color = new THREE.Color(r, g, b)
  
  // 2. 粗糙度和金属度
  material.roughness = params.roughness
  material.metalness = params.metallic
  
  // 3. 透明度
  if (params.opacity !== undefined && params.opacity < 1.0) {
    material.transparent = true
    material.opacity = params.opacity
  }
  
  // 4. 自发光
  if (params.emissive) {
    const [er, eg, eb] = params.emissive
    material.emissive = new THREE.Color(er, eg, eb)
    material.emissiveIntensity = 1.0
  }
  
  // 5. 顶点颜色
  // wild-core 会生成程序化颜色（木纹、石材纹理、苔藓、风化等）
  if (hasVertexColors) {
    material.vertexColors = true
  }
  
  // 6. 双面渲染（用于薄墙、玻璃等）
  if (params.opacity !== undefined && params.opacity < 0.9) {
    material.side = THREE.DoubleSide
  }
  
  return material
}

/**
 * 创建材质缓存
 * 相同参数的材质可以复用，节省内存
 */
export class MaterialCache {
  private cache = new Map<string, THREE.MeshStandardMaterial>()
  
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
    const key = `${materialName}_${hasVertexColors}`
    
    if (!this.cache.has(key)) {
      const material = createMaterialFromParams(params, hasVertexColors)
      material.name = materialName
      this.cache.set(key, material)
    }
    
    return this.cache.get(key)!
  }
  
  /**
   * 清空缓存（场景切换时调用）
   */
  clear() {
    this.cache.forEach(mat => mat.dispose())
    this.cache.clear()
  }
  
  /**
   * 获取缓存的材质数量
   */
  get size() {
    return this.cache.size
  }
}
