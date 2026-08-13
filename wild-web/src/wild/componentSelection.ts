import type { ComponentCompilationMapping } from '../wild-compiler'

/** 将编译后的临时元素 ID 回溯为用户可编辑的源组合构件 ID。 */
export function resolveSelectableId(
  elementId: string,
  mapping: ComponentCompilationMapping,
): string {
  return mapping.componentIdByGeneratedElementId[elementId] || elementId
}

/** 取得某个选中项在渲染场景中对应的所有元素 ID。 */
export function getRenderedElementIds(
  selectedId: string,
  mapping: ComponentCompilationMapping,
): string[] {
  return mapping.generatedElementIdsByComponentId[selectedId] || [selectedId]
}

export type SelectionMode = 'replace' | 'add' | 'toggle'

/** 统一视口和场景树的点击选择语义，避免两个入口的多选行为漂移。 */
export function selectionAfterClick(
  selectedIds: string[],
  id: string,
  mode: SelectionMode,
): string[] {
  if (mode === 'replace') return [id]
  if (mode === 'toggle') {
    return selectedIds.includes(id)
      ? selectedIds.filter(selectedId => selectedId !== id)
      : [...selectedIds, id]
  }
  return selectedIds.includes(id) ? selectedIds : [...selectedIds, id]
}
