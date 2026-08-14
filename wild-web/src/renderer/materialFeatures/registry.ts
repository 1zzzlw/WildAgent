import type * as THREE from 'three'
import type { RenderMaterialDescriptor } from '../../wild-core/src/materials'
import type { MaterialParams } from '../materialAdapter'
import { applyProceduralMaterial } from '../proceduralMaterials'
import { applyDefaultSurfaceMaterial } from './defaultSurfaceMaterial'
import { applyPbrEnvironmentMaterial } from './pbrEnvironmentMaterial'

export interface SurfaceMaterialFeatureContext {
  material: THREE.MeshStandardMaterial
  materialName: string
  params: MaterialParams
  descriptor: RenderMaterialDescriptor
}

export interface SurfaceMaterialFeature {
  id: string
  apply(context: SurfaceMaterialFeatureContext): void
}

const implementations = new Map<string, SurfaceMaterialFeature>()

export function registerSurfaceMaterialFeature(feature: SurfaceMaterialFeature): () => void {
  if (!feature.id.trim()) throw new Error('Surface material feature id cannot be empty')
  if (implementations.has(feature.id)) {
    throw new Error(`Surface material feature already registered: ${feature.id}`)
  }
  implementations.set(feature.id, feature)
  return () => {
    if (implementations.get(feature.id) === feature) implementations.delete(feature.id)
  }
}

export function hasSurfaceMaterialFeature(id: string): boolean {
  return implementations.has(id)
}

export function getSurfaceMaterialFeatureIds(): string[] {
  return [...implementations.keys()].sort()
}

export function applyRegisteredSurfaceMaterial(
  material: THREE.MeshStandardMaterial,
  materialName: string,
  params: MaterialParams,
): void {
  const descriptor = params.renderDescriptor
  if (!descriptor) {
    // 兼容旧调用：历史代码会直接把受控 procedural 参数交给 renderer。
    applyProceduralMaterial(material, params.procedural, params.baseColor)
    return
  }
  const feature = implementations.get(descriptor.implementation)
  if (!feature) return
  feature.apply({ material, materialName, params, descriptor })
}

registerSurfaceMaterialFeature({
  id: 'masonry.brick.v1',
  apply: ({ material, params }) => {
    applyProceduralMaterial(material, params.procedural, params.baseColor)
  },
})

registerSurfaceMaterialFeature({
  id: 'surface.default.v1',
  apply: ({ material, params, descriptor }) => {
    const stableSeed = JSON.stringify({
      baseColor: params.baseColor,
      roughness: params.roughness,
      metallic: params.metallic,
      descriptor,
    })
    applyDefaultSurfaceMaterial(material, descriptor, stableSeed)
  },
})

registerSurfaceMaterialFeature({
  id: 'surface.pbr.v1',
  apply: ({ material, params, descriptor }) => {
    applyPbrEnvironmentMaterial(material, descriptor, JSON.stringify({
      baseColor: params.baseColor,
      textures: params.textures,
      descriptor,
    }))
  },
})
