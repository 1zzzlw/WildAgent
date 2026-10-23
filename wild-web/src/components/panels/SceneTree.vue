<template>
  <div class="scene-tree">
    <div class="tree-header">
      <span>场景结构</span>
    </div>
    <div class="tree-content" @click.self="selectionStore.clearSelection()">
      <div v-if="rows.length" class="group-title">按几何宿主显示依附关系</div>
      <div v-for="row in rows" :key="row.item.id" :data-source-id="row.item.id"
        :style="{ paddingLeft: `${8 + row.depth * 14}px` }"
        :class="['tree-item', { selected: selectionStore.isSelected(row.item.id) }]" @click="handleSelect(row.item.id, $event)">
        <button v-if="row.hasChildren" class="tree-expand" :aria-expanded="!collapsed.has(row.item.id)"
          :aria-label="`${collapsed.has(row.item.id) ? '展开' : '收起'} ${row.item.id} 的依附构件`"
          @click.stop="toggleCollapsed(row.item.id)">{{ collapsed.has(row.item.id) ? '▸' : '▾' }}</button>
        <span v-else class="tree-spacer"></span>
        <span class="element-icon">{{ getIcon(row.item.type) }}</span>
        <span class="element-name">{{ row.item.id }}</span>
        <span class="element-type">{{ row.item.type }}</span>
      </div>
      <div v-if="rows.length === 0" class="empty-state">
        场景为空
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { useUIStore } from '../../stores/uiStore'
import { selectionAfterClick, type SelectionMode } from '../../wild/componentSelection'

const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const uiStore = useUIStore()

const collapsed = ref(new Set<string>())
watch(() => sceneStore.document?.id, () => { collapsed.value = new Set() })
const rows = computed(() => {
  const index = sceneStore.relationIndex
  const items = new Map([...index.items].filter((entry): entry is [string, {id: string; type: string}] => !!entry[1].type))
  const children = new Map<string, string[]>(), parents = new Map<string, string>()
  for (const id of items.keys()) {
    const host = index.references.get(id)?.find(ref => items.has(ref.targetId) && ref.targetId !== id)
    if (!host) continue
    parents.set(id, host.targetId)
    if (!children.has(host.targetId)) children.set(host.targetId, [])
    children.get(host.targetId)!.push(id)
  }
  const result: Array<{ item: {id: string; type: string}; depth: number; hasChildren: boolean }> = []
  const visited = new Set<string>()
  const visit = (id: string, depth: number, hidden = false) => {
    if (visited.has(id)) return
    visited.add(id)
    const descendants = children.get(id) || []
    if (!hidden) result.push({ item: items.get(id)!, depth, hasChildren: descendants.length > 0 })
    for (const child of descendants) visit(child, depth + 1, hidden || collapsed.value.has(id))
  }
  for (const id of items.keys()) if (!parents.has(id)) visit(id, 0)
  // Invalid cycles remain visible and selectable; validation explains the defect.
  for (const id of items.keys()) if (!visited.has(id)) visit(id, 0)
  return result
})

function toggleCollapsed(id: string) {
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  collapsed.value = next
}

function getIcon(type: string): string {
  const icons: Record<string, string> = {
    wall: '▭',
    floor: '□',
    column: '║',
    beam: '─',
    roof: '▲',
    opening: '◫',
    stair: '≡',
    furniture: '◆',
    door: '▯',
    window: '▦',
    railing: '╪',
    canopy: '⌐',
    balcony: '▱',
    ramp: '╱',
    bay_window: '▤',
    cornice: '⌒',
    chimney: '▥'
  }
  return icons[type] || '●'
}

function handleSelect(id: string, event: MouseEvent) {
  const mode: SelectionMode = event.ctrlKey || event.metaKey
    ? 'toggle'
    : event.shiftKey
      ? 'add'
      : 'replace'
  selectionStore.setSelection(selectionAfterClick(selectionStore.selectedIds, id, mode))
  uiStore.openPanel('properties')
}
</script>

<style scoped>
.scene-tree {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.tree-header {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid #3e3e42;
}

.tree-content {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 3px;
  font-size: 13px;
  transition: all 0.15s;
}

.tree-item:hover {
  background: #2a2d2e;
}

.tree-item.selected {
  background: #094771;
}
.tree-expand, .tree-spacer { width: 16px; flex: 0 0 16px; }
.tree-expand { border: 0; padding: 0; background: transparent; color: inherit; cursor: pointer; }

.group-title {
  padding: 8px 8px 4px;
  color: #777777;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.component-item {
  border-left: 2px solid #3b82a0;
}

.element-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}

.element-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.element-type {
  font-size: 11px;
  color: #888888;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: #666666;
  font-size: 13px;
}
</style>
