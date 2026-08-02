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
      <div class="category">
        <div class="category-title">组合构件</div>
        <div class="block-grid">
          <div v-for="block in componentBlocks" :key="`${block.type}:${block.fixtureType || 'default'}`" class="block-item"
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
import { useSelectionStore } from '../../stores/selectionStore'
import { useUIStore } from '../../stores/uiStore'
import { createPatch } from '../../wild/scenePatch'
import { generateId } from '../../utils/common'
import type { ComponentSpec, GeometryElement } from '../../types/blueprint'
import type { RoofParams, WallParams } from '../../wild-core/types'
import { ElMessage } from 'element-plus'

const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const uiStore = useUIStore()

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
  { type: 'door', label: '门', icon: '▯', description: '在第一面直线墙上创建静态门' },
  { type: 'window', label: '窗', icon: '▦', description: '在第一面直线墙上创建静态窗' },
  { type: 'railing', label: '栏杆', icon: '╪', description: '创建一段路径栏杆' },
  { type: 'canopy', label: '雨棚', icon: '⌐', description: '创建依附墙体的雨棚' },
  { type: 'balcony', label: '阳台', icon: '▱', description: '创建带栏杆的悬挑阳台' },
  { type: 'ramp', label: '坡道', icon: '╱', description: '创建带可选栏杆的直线坡道' },
  { type: 'bay_window', label: '凸窗', icon: '▤', description: '创建向墙外投影的凸窗' },
  { type: 'cornice', label: '檐口', icon: '⌒', description: '沿第一座屋顶边界创建分层檐口线脚' },
  { type: 'chimney', label: '烟囱', icon: '▥', description: '创建参数化薄壁烟囱' },
  { type: 'light', fixtureType: 'bulb', label: '灯泡', icon: '💡', description: '创建可拖动、可右键调光的裸灯泡' },
  { type: 'light', fixtureType: 'table_lamp', label: '台灯', icon: '♟', description: '创建带灯座、灯杆和灯罩的发光台灯' },
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

async function handleAddComponent(
  type: ComponentSpec['type'],
  fixtureType?: 'bulb' | 'table_lamp',
  label?: string,
) {
  if (!sceneStore.document) return

  const component = createDefaultComponent(type, fixtureType)
  if (!component) return
  const patch = createPatch(
    sceneStore.document.revision,
    [{ op: 'add_component', component }],
    'user',
    false,
    `添加${label || componentBlocks.find(block => block.type === type)?.label || '组合构件'}`,
  )
  if (await sceneStore.applyPatch(patch)) {
    selectionStore.select(component.id)
    uiStore.setRightActivePanel('properties')
  }
}

function createDefaultComponent(
  type: ComponentSpec['type'],
  fixtureType?: 'bulb' | 'table_lamp',
): ComponentSpec | null {
  if (type === 'light') {
    if (fixtureType === 'table_lamp') {
      return {
        type,
        id: generateId('table_lamp'),
        fixtureType,
        position: [0, 0, 0],
        lightType: 'point',
        color: [1, 0.78, 0.52],
        lowIntensity: 18,
        highIntensity: 65,
        distance: 8,
        height: 0.72,
        shadeRadius: 0.28,
        baseHeight: 0.07,
        draggable: true,
      }
    }
    return {
      type,
      id: generateId(type),
      fixtureType: 'bulb',
      position: [0, 2.4, 0],
      lightType: 'point',
      color: [1, 0.82, 0.58],
      lowIntensity: 25,
      highIntensity: 90,
      distance: 12,
      draggable: true,
    }
  }

  if (type === 'railing') {
    return {
      type,
      id: generateId(type),
      path: [[0, 0, 0], [3, 0, 0]],
      height: 1.1,
      postSpacing: 0.9,
      railLevels: [0.5, 1],
    }
  }

  if (type === 'ramp') {
    return {
      type,
      id: generateId(type),
      from: [0, 0, 0],
      to: [5.4, 0.45, 0],
      width: 1.5,
      thickness: 0.18,
      railingSides: 'both',
      railingHeight: 1.1,
    }
  }

  if (type === 'cornice') {
    const roof = sceneStore.document!.blueprint.geometry.elements.find(
      element => element.type === 'roof',
    ) as RoofParams | undefined
    if (!roof) {
      ElMessage.warning('檐口必须依附建筑屋顶，请先创建屋顶')
      return null
    }
    const halfSpan = roof.span / 2
    const halfDepth = roof.depth / 2
    const path: [number, number, number][] = roof.roofType === 'gable'
      ? [
          [-halfSpan, 0, -halfDepth],
          [-halfSpan, 0, halfDepth],
          [0, 0, halfDepth],
          [halfSpan, 0, halfDepth],
          [halfSpan, 0, -halfDepth],
          [0, 0, -halfDepth],
          [-halfSpan, 0, -halfDepth],
        ]
      : [
          [-halfSpan, 0, -halfDepth],
          [-halfSpan, 0, halfDepth],
          [halfSpan, 0, halfDepth],
          [halfSpan, 0, -halfDepth],
          [-halfSpan, 0, -halfDepth],
        ]
    return {
      type,
      id: generateId(type),
      parentRoof: roof.id,
      path,
      profile: [
        [-0.16, -0.14],
        [0.16, -0.14],
        [0.16, -0.07],
        [0.1, -0.07],
        [0.1, 0],
        [0.05, 0],
        [0.05, 0.08],
        [-0.16, 0.08],
      ],
      closedProfile: true,
    }
  }

  if (type === 'chimney') {
    return {
      type,
      id: generateId(type),
      position: [0, 0, 0],
      width: 0.7,
      depth: 0.7,
      height: 2,
      wallThickness: 0.1,
    }
  }

  const wall = sceneStore.document?.blueprint.geometry.elements.find(
    element => element.type === 'wall',
  ) as WallParams | undefined
  if (!wall) {
    ElMessage.warning('请先创建一面墙，再添加墙体依附组件')
    return null
  }
  const length = Math.hypot(wall.to[0] - wall.from[0], wall.to[2] - wall.from[2])
  const bottom = Math.min(wall.from[1], wall.to[1])
  const top = Math.max(wall.from[1], wall.to[1])
  const wallHeight = top - bottom
  if (length < 0.6 || wallHeight < 0.8) {
    ElMessage.warning('父墙尺寸过小，无法放置默认门窗')
    return null
  }

  if (type === 'door') {
    const width = Math.min(0.9, length - 0.1)
    return {
      type,
      id: generateId(type),
      parentWall: wall.id,
      from: [(length - width) / 2, bottom, 0],
      width,
      height: Math.min(2.1, wallHeight - 0.05),
      interaction: { mode: 'swing', hingeSide: 'left', openAngle: 90 },
    }
  }


  if (type === 'canopy') {
    const width = Math.min(2.4, length - 0.1)
    return {
      type,
      id: generateId(type),
      parentWall: wall.id,
      from: [(length - width) / 2, bottom + Math.min(2.4, wallHeight - 0.1), 0],
      width,
      depth: 1.1,
      thickness: 0.12,
    }
  }

  if (type === 'balcony') {
    const width = Math.min(2.8, length - 0.1)
    return {
      type,
      id: generateId(type),
      parentWall: wall.id,
      from: [(length - width) / 2, bottom + Math.min(1.2, wallHeight - 0.1), 0],
      width,
      depth: 1.2,
      slabThickness: 0.18,
      railingHeight: 1.1,
      postSpacing: 0.9,
    }
  }

  if (type === 'bay_window') {
    const sillHeight = Math.min(0.9, wallHeight * 0.3)
    const width = Math.min(1.8, length - 0.1)
    return {
      type,
      id: generateId(type),
      parentWall: wall.id,
      from: [(length - width) / 2, bottom + sillHeight, 0],
      width,
      height: Math.max(0.3, Math.min(1.2, wallHeight - sillHeight - 0.05)),
      projectionDepth: 0.45,
    }
  }

  const sillHeight = Math.min(0.9, wallHeight * 0.3)
  const width = Math.min(1.5, length - 0.1)
  if (type === 'window') return {
    type,
    id: generateId(type),
    parentWall: wall.id,
    from: [(length - width) / 2, bottom + sillHeight, 0],
    width,
    height: Math.max(0.3, Math.min(1.2, wallHeight - sillHeight - 0.05)),
    verticalMullions: 1,
    interaction: { mode: 'swing', openAngle: 70 },
  }
  return null
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
