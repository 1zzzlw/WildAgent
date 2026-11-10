import type { Blueprint, EditorGroup } from '../types/blueprint'

export interface ItemEditorGroup extends EditorGroup {
  kind: 'item'
  sourceItemId: string
}

export function isItemGroup(group: EditorGroup | undefined): group is ItemEditorGroup {
  return group?.kind === 'item'
}

export function findItemGroupByElement(
  blueprint: Blueprint,
  elementId: string,
): [string, ItemEditorGroup] | undefined {
  for (const [groupId, group] of Object.entries(blueprint.editor?.groups || {})) {
    if (isItemGroup(group) && group.elements.includes(elementId)) return [groupId, group]
  }
  return undefined
}

/** 将命中的任一零件展开为完整物品；普通构件保持原样。 */
export function expandItemSelection(blueprint: Blueprint, selectedIds: readonly string[]): string[] {
  const expanded = new Set<string>()
  for (const id of selectedIds) {
    const group = findItemGroupByElement(blueprint, id)?.[1]
    if (group) group.elements.forEach(elementId => expanded.add(elementId))
    else expanded.add(id)
  }
  return [...expanded]
}

/** 只有恰好选中一件完整物品时才返回该组。 */
export function selectedItemGroup(
  blueprint: Blueprint,
  selectedIds: readonly string[],
): [string, ItemEditorGroup] | undefined {
  if (!selectedIds.length) return undefined
  const match = findItemGroupByElement(blueprint, selectedIds[0]!)
  if (!match) return undefined
  const selected = new Set(selectedIds)
  return match[1].elements.length === selected.size
    && match[1].elements.every(id => selected.has(id))
    ? match
    : undefined
}
