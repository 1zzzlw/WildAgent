<template>
  <div class="property-panel">
    <div class="panel-header">
      <span>属性面板</span>
    </div>
    <div class="panel-body">
      <div v-if="!selectedElement" class="empty-state">
        未选中任何构件
      </div>
      <div v-else class="properties">
        <div class="property-section">
          <div class="section-title">基本信息</div>
          <div class="property-row">
            <label>ID</label>
            <el-input :model-value="selectedElement.id" readonly />
          </div>
          <div class="property-row">
            <label>类型</label>
            <el-input :model-value="selectedElement.type" readonly />
          </div>
        </div>

        <div class="property-section" v-if="selectedElement.type === 'column'">
          <div class="section-title">柱子参数</div>
          <div class="property-row">
            <label>高度</label>
            <el-input-number :model-value="(selectedElement as any).height" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('height', value)" />
          </div>
          <div class="property-row">
            <label>底部半径</label>
            <el-input-number :model-value="(selectedElement as any).bottomRadius" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('bottomRadius', value)" />
          </div>
          <div class="property-row">
            <label>顶部半径</label>
            <el-input-number :model-value="(selectedElement as any).topRadius" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('topRadius', value)" />
          </div>
        </div>

        <div class="property-section" v-if="selectedElement.type === 'wall'">
          <div class="section-title">墙体参数</div>
          <div class="property-row">
            <label>高度</label>
            <el-input-number :model-value="(selectedElement as any).height" :step="0.1"
              @update:model-value="(value: string | number | null | undefined) => handleChange('height', value)" />
          </div>
          <div class="property-row">
            <label>厚度</label>
            <el-input-number :model-value="(selectedElement as any).thickness" :step="0.01"
              @update:model-value="(value: string | number | null | undefined) => handleChange('thickness', value)" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { createPatch } from '../../wild/scenePatch'

const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()

const selectedElement = computed(() => {
  const id = selectionStore.selectedIds[0]
  if (!id || !sceneStore.document) return null
  return sceneStore.document.blueprint.geometry.elements.find(e => e.id === id)
})

function handleChange(key: string, value: string | number | null | undefined) {
  const numericValue = typeof value === 'number' ? value : parseFloat(String(value ?? ''))

  if (!Number.isFinite(numericValue) || !selectedElement.value || !sceneStore.document) return

  const patch = createPatch(
    sceneStore.document.revision,
    [{
      op: 'update_element',
      id: selectedElement.value.id,
      changes: { [key]: numericValue }
    }],
    'user'
  )

  sceneStore.applyPatch(patch)
}
</script>

<style scoped>
.property-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid #3e3e42;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: #666666;
  font-size: 13px;
}

.properties {
  padding: 8px;
}

.property-section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: #888888;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.property-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.property-row label {
  flex: 0 0 80px;
  font-size: 12px;
}

.property-row :deep(.el-input),
.property-row :deep(.el-input-number) {
  flex: 1;
}

.property-row :deep(.el-input__wrapper) {
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  color: #cccccc;
  font-size: 12px;
  border-radius: 2px;
  box-shadow: none;
  height: 28px;
}

.property-row :deep(.el-input__wrapper:hover),
.property-row :deep(.el-input__wrapper.is-focus) {
  border-color: #007acc;
  box-shadow: 0 0 0 1px #007acc inset;
}

.property-row :deep(.el-input__inner) {
  color: #cccccc;
  background: transparent;
}

.property-row :deep(.el-input-number .el-input__wrapper) {
  padding-right: 8px;
}
</style>
