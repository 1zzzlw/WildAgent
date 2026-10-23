import type { Blueprint, MaterialDef } from '../types/blueprint'
import type { SceneOperation } from '../types/scenePatch'
import { acceptsComponentMaterial, isGlassMaterial } from './materialCompatibility'

/** 为当前多选集合生成统一材质绑定操作。 */
export function createSelectedMaterialBindings(
  blueprint: Blueprint,
  selectedIds: readonly string[],
  materialName: string,
  materialOverride?: MaterialDef,
): SceneOperation[] {
  const material = materialOverride || blueprint.materials?.[materialName]
  if (!material) return []
  const selected = new Set(selectedIds)
  const operations: SceneOperation[] = []
  for (const element of blueprint.geometry.elements) {
    if (selected.has(element.id)) {
      operations.push({ op: 'update_element', id: element.id, changes: { material: materialName } })
    }
  }
  for (const component of blueprint.geometry.components || []) {
    if (!selected.has(component.id)) continue
    let materialField = 'material'
    if (component.type === 'door') materialField = 'leafMaterial'
    else if (component.type === 'window' || component.type === 'bay_window') {
      materialField = isGlassMaterial(materialName, material) ? 'glassMaterial' : 'frameMaterial'
    } else if (component.type === 'railing' && component.infillType === 'glass' && isGlassMaterial(materialName, material)) {
      materialField = 'infillMaterial'
    } else if (component.type === 'light') materialField = 'shadeMaterial'
    if (!acceptsComponentMaterial(component, materialField, materialName, material)) continue
    operations.push({
      op: 'update_component',
      id: component.id,
      changes: { [materialField]: materialName },
    })
  }
  return operations
}
