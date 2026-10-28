import * as THREE from 'three'
import { bakeGlbMaterials, canBakeGlbMaterial, type GlbMaterialBakeItem } from './glbMaterialBake'

/** 导出建筑的静态快照；不带入视口居中偏移、辅助对象和运行时引用。 */
export async function exportBuildingGlb(root: THREE.Group, name: string, renderer?: THREE.WebGLRenderer) {
  const snapshot = new THREE.Group()
  snapshot.name = name
  const geometries = new Map<THREE.BufferGeometry, THREE.BufferGeometry>()
  const materials = new Map<THREE.Material, THREE.Material>()
  const tintedMaterials = new Set<THREE.MeshStandardMaterial | THREE.MeshBasicMaterial>()
  const unavailableTextures = new Set<THREE.Material>()
  const warnings: string[] = []
  let simplifiedMaterials = false
  let meshCount = 0
  const bakeItems: GlbMaterialBakeItem[] = []
  let baked: ReturnType<typeof bakeGlbMaterials> | undefined
  let ownedRenderer: THREE.WebGLRenderer | undefined

  function copyMaterial(source: THREE.Material): THREE.Material {
    const cached = materials.get(source)
    if (cached) return cached
    // 水面等 userData 中持有渲染目标和运行时对象，不参与材质复制或序列化。
    let material: THREE.Material
    if (source instanceof THREE.MeshStandardMaterial || source instanceof THREE.MeshBasicMaterial) {
      const Constructor = source.constructor as new () => THREE.Material
      const cleanSource = Object.create(source) as THREE.Material
      cleanSource.userData = {}
      material = new Constructor().copy(cleanSource)
    } else {
      const surface = source as THREE.MeshStandardMaterial
      material = new THREE.MeshStandardMaterial({
        name: source.name,
        color: surface.color?.isColor ? surface.color : 0x808080,
        map: surface.map?.isTexture ? surface.map : null,
        emissive: surface.emissive?.isColor ? surface.emissive : 0,
        emissiveIntensity: surface.emissiveIntensity ?? 1,
        roughness: surface.roughness ?? .8, metalness: surface.metalness ?? 0,
        opacity: source.opacity, transparent: source.transparent, side: source.side,
        alphaTest: source.alphaTest, vertexColors: surface.vertexColors ?? false,
      })
      simplifiedMaterials = true
      warnings.push(`${source.name || source.type} 已转换为标准 PBR 材质`)
    }
    materials.set(source, material)
    simplifiedMaterials ||= !!source.userData.wildWaterSurface
      || source.onBeforeCompile !== THREE.Material.prototype.onBeforeCompile && !canBakeGlbMaterial(source)
    for (const [key, value] of Object.entries(material)) {
      if (key === 'envMap' || !(value instanceof THREE.Texture)) continue
      if (!value.image || value.image.width === 0 || value.image.height === 0
        || value.image.complete === false || value instanceof THREE.CompressedTexture && !value.mipmaps.length) {
        ;(material as unknown as Record<string, unknown>)[key] = null
        unavailableTextures.add(source)
        simplifiedMaterials = true
        warnings.push(`${source.name || source.type} 的 ${key} 贴图尚未就绪，已保留基础材质`)
      }
    }
    return material
  }

  function copyObject(source: THREE.Object3D): THREE.Object3D | null {
    if (!source.visible || source instanceof THREE.Light) return null
    let target: THREE.Object3D
    if (source instanceof THREE.Mesh) {
      if (!source.geometry.getAttribute('position')?.count) return null
      const geometry = geometries.get(source.geometry) || source.geometry.clone() as THREE.BufferGeometry
      geometries.set(source.geometry, geometry)
      const material = Array.isArray(source.material)
        ? source.material.map(copyMaterial)
        : copyMaterial(source.material)
      const bakeSource = canBakeGlbMaterial(source.material) && !unavailableTextures.has(source.material)
        ? source.material : null
      if (Array.isArray(source.material) && source.material.some(canBakeGlbMaterial)) simplifiedMaterials = true
      if (source instanceof THREE.InstancedMesh) {
        target = new THREE.Group()
        for (let index = 0; index < source.count; index++) {
          // 用共享几何的普通节点兼容更多查看器，不依赖实例化扩展。
          const tint = source.instanceColor ? new THREE.Color() : undefined
          if (tint) source.getColorAt(index, tint)
          const tintMaterial = (entry: THREE.Material) => {
            const result = entry.clone() as THREE.MeshStandardMaterial | THREE.MeshBasicMaterial
            result.color.multiply(tint!)
            tintedMaterials.add(result)
            return result
          }
          const instanceMaterial = tint ? (Array.isArray(material) ? material.map(tintMaterial) : tintMaterial(material)) : material
          const mesh = new THREE.Mesh(geometry, instanceMaterial)
          source.getMatrixAt(index, mesh.matrix)
          mesh.matrixAutoUpdate = false
          mesh.name = source.userData.instanceElementIds?.[index] || `${source.name}:${index}`
          mesh.userData.elementId = source.userData.instanceElementIds?.[index]
          mesh.userData.materialRef = source.userData.materialRef
          target.add(mesh)
          if (bakeSource) bakeItems.push({
            mesh: mesh as GlbMaterialBakeItem['mesh'], source: bakeSource,
            worldMatrix: source.matrixWorld.clone().multiply(mesh.matrix), tint,
          })
        }
        meshCount += source.count
      } else {
        const mesh = new THREE.Mesh(geometry, material)
        target = mesh
        if (bakeSource) {
          bakeItems.push({ mesh: mesh as GlbMaterialBakeItem['mesh'], source: bakeSource, worldMatrix: source.matrixWorld.clone() })
        }
        meshCount++
      }
      target.userData.elementId = source.userData.elementId
      target.userData.materialRef = source.userData.materialRef
    } else if (source instanceof THREE.Group) {
      target = new THREE.Group()
    } else {
      return null
    }
    target.name = source.name
    if (source.matrixAutoUpdate) source.updateMatrix()
    target.matrix.copy(source.matrix)
    target.matrixAutoUpdate = false
    for (const child of source.children) {
      const copy = copyObject(child)
      if (copy) target.add(copy)
    }
    return target
  }

  try {
    root.updateWorldMatrix(true, true)
    // 根节点的隐藏/平移属于视口展示状态；子节点仍按蓝图局部坐标导出。
    for (const child of root.children) {
      const copy = copyObject(child)
      if (copy) snapshot.add(copy)
    }
    if (!meshCount) throw new Error('当前没有可导出的建筑模型')
    if (bakeItems.length) {
      try {
        if (!renderer || renderer.getContext().isContextLost()) {
          ownedRenderer = new THREE.WebGLRenderer({ antialias: false, alpha: true })
          ownedRenderer.setSize(1, 1, false)
          renderer = ownedRenderer
        }
        baked = bakeGlbMaterials(bakeItems, renderer)
        if (baked.failures.length) {
          simplifiedMaterials = true
          warnings.push(`${baked.failures.length} 类材质未能烘焙，已保留基础 PBR 材质`)
          console.warn('[glb-export] 材质烘焙回退', baked.failures)
        }
      } catch (error) {
        simplifiedMaterials = true
        warnings.push('当前设备无法完成材质烘焙，已保留建筑模型与基础 PBR 材质')
        console.warn('[glb-export] 材质烘焙不可用', error)
      }
    }
    const { GLTFExporter } = await import('three/examples/jsm/exporters/GLTFExporter.js')
    const data = await new GLTFExporter().parseAsync(snapshot, { binary: true })
    if (!(data instanceof ArrayBuffer)) throw new Error('未能生成 GLB 文件')
    return { data, simplifiedMaterials, bakedMaterials: baked?.count || 0, warnings }
  } finally {
    baked?.dispose()
    // 仅释放快照自己的几何与材质；贴图仍由原场景持有。
    for (const geometry of geometries.values()) geometry.dispose()
    for (const material of materials.values()) material.dispose()
    for (const material of tintedMaterials) material.dispose()
    ownedRenderer?.dispose()
    ownedRenderer?.forceContextLoss()
  }
}
