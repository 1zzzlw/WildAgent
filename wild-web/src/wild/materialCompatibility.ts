import type { ComponentSpec } from 'wild-core/types'
import { isWaterMaterial } from 'wild-core/materials'
import type { MaterialDef } from '../types/blueprint'

/** Read physical intent first; legacy names only fill missing material metadata. */
export function isGlassMaterial(name: string, material: MaterialDef): boolean {
  if (isWaterMaterial(material, name)) return false
  if (material.materialClass === 'glass' || material.surfaceFamily === 'glass') return true
  if ((material.transmission ?? 0) > 0.05) return true
  return !material.materialClass && !material.surfaceFamily
    && /glass|glazing|玻璃/i.test(name) && (material.opacity ?? 1) < 1
}

export function acceptsComponentMaterial(
  component: ComponentSpec, field: string, name: string, material: MaterialDef,
): boolean {
  const glass = isGlassMaterial(name, material)
  if (field === 'glassMaterial' || (field === 'infillMaterial'
    && component.type === 'railing' && component.infillType === 'glass')) return glass
  if (field === 'frameMaterial' || (field === 'infillMaterial'
    && component.type === 'railing' && component.infillType === 'panel')) {
    return !glass && !isWaterMaterial(material, name)
  }
  return true
}
