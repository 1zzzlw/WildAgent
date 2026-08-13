import type { Blueprint } from '../types/blueprint'
import type { SceneOperation } from '../types/scenePatch'

/** 为当前多选集合生成统一材质绑定操作。 */
export function createSelectedMaterialBindings(
  blueprint: Blueprint,
  selectedIds: readonly string[],
  materialName: string,
): SceneOperation[] {
  const selected = new Set(selectedIds)
  const operations: SceneOperation[] = []
  for (const element of blueprint.geometry.elements) {
    if (selected.has(element.id)) {
      operations.push({ op: 'update_element', id: element.id, changes: { material: materialName } })
    }
  }
  for (const component of blueprint.geometry.components || []) {
    if (!selected.has(component.id)) continue
    const materialField = component.type === 'door'
      ? 'leafMaterial'
      : component.type === 'window' || component.type === 'bay_window'
        ? 'frameMaterial'
        : component.type === 'light'
          ? 'shadeMaterial'
          : 'material'
    operations.push({
      op: 'update_component',
      id: component.id,
      changes: { [materialField]: materialName },
    })
  }
  return operations
}
