<template>
  <div class="block-library">
    <div class="library-header">
      <span>构件库</span>
    </div>
    <p class="placement-help">选择构件后，在视口移动预览，单击放置；Esc 或右键取消。</p>
    <div class="library-content">
      <div class="category">
        <div class="category-title">基础构件</div>
        <div class="block-grid">
          <div v-for="block in basicBlocks" :key="block.label" class="block-item"
            :class="{ active: placement.request?.label === block.label }" @click="handleAddBlock(block)"
            :title="block.description">
            <span class="block-icon">{{ block.icon }}</span>
            <span class="block-label">{{ block.label }}</span>
          </div>
        </div>
      </div>
      <div class="category">
        <div class="category-title">组合构件</div>
        <div class="block-grid">
          <div v-for="block in componentBlocks" :key="`${block.type}:${block.fixtureType || 'default'}`" class="block-item" :class="{ active: placement.request?.label === block.label }"
            @click="handleAddComponent(block.type, block.fixtureType, block.label)" :title="block.description">
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
import { useBlockPlacementStore } from '../../stores/blockPlacementStore'
import type { ComponentSpec, GeometryElement } from '../../types/blueprint'

const sceneStore = useSceneStore()
const placement = useBlockPlacementStore()

interface BlockTemplate {
  type: string
  label: string
  icon: string
  description: string
  defaults: Partial<GeometryElement>
}

interface ComponentBlock {
  type: ComponentSpec['type']
  fixtureType?: 'bulb' | 'table_lamp'
  label: string
  icon: string
  description: string
}

const basicBlocks: BlockTemplate[] = [
  {
    type: 'primitive',
    label: '招牌',
    icon: '文',
    description: '创建建筑招牌',
    defaults: { type: 'primitive', shape: 'box', position: [0, 2, 0], dimensions: [3, 0.7, 0.12], material: 'default', label: { text: '建筑名称' } }
  },
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
    defaults: { type: 'column', base: [0, 0, 0], height: 3, bottomRadius: 0.2, topRadius: 0.2, style: 'modern', material: 'default' }
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
    defaults: { type: 'roof', roofType: 'gable', span: 8, depth: 6, height: 3, thickness: 0.18, material: 'default' }
  },
  {
    type: 'primitive',
    label: '通用球体',
    icon: '●',
    description: '创建可扩展的通用参数化球体',
    defaults: { type: 'primitive', shape: 'sphere', position: [0, 0.5, 0], radius: 0.5, segments: 32, material: 'default' }
  }
]

const componentBlocks: readonly ComponentBlock[] = [
  { type: 'door', label: '门', icon: '▯', description: '选择墙面放置门' },
  { type: 'window', label: '窗', icon: '▦', description: '选择墙面放置窗' },
  { type: 'railing', label: '栏杆', icon: '╪', description: '创建一段路径栏杆' },
  { type: 'canopy', label: '雨棚', icon: '⌐', description: '创建依附墙体的雨棚' },
  { type: 'balcony', label: '阳台', icon: '▱', description: '创建带栏杆的悬挑阳台' },
  { type: 'ramp', label: '坡道', icon: '╱', description: '创建带可选栏杆的直线坡道' },
  { type: 'bay_window', label: '凸窗', icon: '▤', description: '创建向墙外投影的凸窗' },
  { type: 'cornice', label: '檐口', icon: '⌒', description: '选择屋顶放置分层檐口线脚' },
  { type: 'chimney', label: '烟囱', icon: '▥', description: '创建参数化薄壁烟囱' },
  { type: 'light', fixtureType: 'bulb', label: '灯泡', icon: '💡', description: '创建可拖动、可右键调光的裸灯泡' },
  { type: 'light', fixtureType: 'table_lamp', label: '台灯', icon: '♟', description: '创建带灯座、灯杆和灯罩的发光台灯' },
  { type: 'fan', label: '吊扇', icon: '✣', description: '创建带独立调速开关的吊扇' },
  { type: 'elevator', label: '电梯', icon: '↕', description: '创建轿厢、层门与楼层按钮；放入井道并为上层楼板留洞' },
]

function handleAddBlock(block: BlockTemplate) {
  if (!sceneStore.document || sceneStore.isReconstructing) return
  placement.begin({ kind: 'element', label: block.label, defaults: block.defaults })
}

function handleAddComponent(type: ComponentSpec['type'], fixtureType?: 'bulb' | 'table_lamp', label = '') {
  if (!sceneStore.document || sceneStore.isReconstructing) return
  placement.begin({ kind: 'component', type, fixtureType, label })
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
  border-bottom: 1px solid var(--studio-border);
}

.placement-help {
  margin: 8px 12px;
  color: var(--studio-muted);
  font-size: 12px;
  line-height: 1.6;
}

.block-item.active {
  border-color: var(--studio-accent-border);
  background: var(--studio-hover);
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
  color: var(--studio-muted);
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
  background: var(--studio-surface);
  border: 1px solid var(--studio-border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.block-item:hover {
  background: var(--studio-hover);
  border-color: var(--studio-border);
}

.block-icon {
  font-size: 24px;
}

.block-label {
  font-size: 12px;
  text-align: center;
}
</style>
