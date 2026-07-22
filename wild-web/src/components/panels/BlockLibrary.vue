<template>
  <div class="block-library">
    <div class="library-header">
      <span>构件库</span>
    </div>
    <div class="library-content">
      <div class="category">
        <div class="category-title">基础构件</div>
        <div class="block-grid">
          <div v-for="block in basicBlocks" :key="block.type" class="block-item" @click="handleAddBlock(block)"
            :title="block.description">
            <span class="block-icon">{{ block.icon }}</span>
            <span class="block-label">{{ block.label }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSceneStore } from '../../stores/sceneStore'
import { createPatch } from '../../wild/scenePatch'
import { generateId } from '../../utils/common'
import type { GeometryElement } from '../../types/blueprint'

const sceneStore = useSceneStore()

interface BlockTemplate {
  type: string
  label: string
  icon: string
  description: string
  defaults: Partial<GeometryElement>
}

const basicBlocks: BlockTemplate[] = [
  {
    type: 'wall',
    label: '墙体',
    icon: '▭',
    description: '创建墙体',
    defaults: { type: 'wall', from: [0, 0, 0], to: [4, 3, 0], thickness: 0.24, material: 'default' }
  },
  {
    type: 'column',
    label: '柱子',
    icon: '║',
    description: '创建柱子',
    defaults: { type: 'column', base: [0, 0, 0], height: 3, bottomRadius: 0.2, topRadius: 0.2, material: 'default' }
  },
  {
    type: 'floor',
    label: '地板',
    icon: '□',
    description: '创建地板',
    defaults: { type: 'floor', from: [0, 0, 0], to: [4, 0, 4], thickness: 0.2, material: 'default' }
  },
  {
    type: 'roof',
    label: '屋顶',
    icon: '▲',
    description: '创建屋顶',
    defaults: { type: 'roof', roofType: 'gable', span: 8, depth: 6, height: 3, material: 'default' }
  }
]

function handleAddBlock(block: BlockTemplate) {
  if (!sceneStore.document) return

  const element: GeometryElement = {
    id: generateId(block.type),
    ...block.defaults
  } as GeometryElement

  const patch = createPatch(
    sceneStore.document.revision,
    [{ op: 'add_element', element }],
    'user',
    false,
    `添加${block.label}`
  )

  sceneStore.applyPatch(patch)
}
</script>

<style scoped>
.block-library {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.library-header {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid #3e3e42;
}

.library-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.category {
  margin-bottom: 16px;
}

.category-title {
  font-size: 12px;
  font-weight: 500;
  color: #888888;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.block-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.block-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  background: #2d2d30;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.block-item:hover {
  background: #3e3e42;
  border-color: #4e4e52;
}

.block-icon {
  font-size: 24px;
}

.block-label {
  font-size: 12px;
  text-align: center;
}
</style>
