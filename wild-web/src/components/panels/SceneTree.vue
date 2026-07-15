<template>
  <div class="scene-tree">
    <div class="tree-header">
      <span>场景结构</span>
    </div>
    <div class="tree-content">
      <div v-for="element in elements" :key="element.id"
        :class="['tree-item', { selected: selectionStore.isSelected(element.id) }]" @click="handleSelect(element.id)">
        <span class="element-icon">{{ getIcon(element.type) }}</span>
        <span class="element-name">{{ element.id }}</span>
        <span class="element-type">{{ element.type }}</span>
      </div>
      <div v-if="elements.length === 0" class="empty-state">
        场景为空
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'

const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()

const elements = computed(() => {
  return sceneStore.document?.blueprint.geometry.elements || []
})

function getIcon(type: string): string {
  const icons: Record<string, string> = {
    wall: '▭',
    floor: '□',
    column: '║',
    beam: '─',
    roof: '▲',
    opening: '◫',
    stair: '≡',
    furniture: '◆'
  }
  return icons[type] || '●'
}

function handleSelect(id: string) {
  selectionStore.select(id)
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
