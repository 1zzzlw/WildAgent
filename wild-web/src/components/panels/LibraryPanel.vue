<template>
  <div class="library-panel">
    <div class="library-header">
      <div class="tabs">
        <button type="button" :class="['tab', { active: tab === 'component' }]" @click="tab = 'component'">
          构件<span class="count">{{ componentEntries.length + basicBlocks.length }}</span>
        </button>
        <button type="button" :class="['tab', { active: tab === 'item' }]" @click="switchToItems">
          物品<span class="count">{{ catalog.items.length }}</span>
        </button>
      </div>
      <div v-if="tab === 'item'" class="header-actions">
        <button class="ghost" :disabled="catalog.loading" title="重新读取目录" @click="catalog.load(true)">刷新</button>
        <button class="ghost" title="导入 .wild 物品" @click="pickFile">导入</button>
      </div>
    </div>

    <p class="placement-help">{{ tab === 'component'
      ? '选择构件后在视口单击放置；挂墙 / 挂屋面构件需先指向宿主。Esc 或右键取消。'
      : '物品是一组基础几何，点击后在视口单击落地；Esc 取消。' }}</p>

    <!-- ── 构件 ── -->
    <div v-if="tab === 'component'" class="scroll">
      <div class="category">
        <div class="category-title">基础构件</div>
        <div class="block-grid">
          <div v-for="block in basicBlocks" :key="block.label" class="block-item"
            :class="{ active: placement.request?.label === block.label }"
            :title="block.description" @click="placeBlock(block)">
            <span class="block-icon">{{ block.icon }}</span>
            <span class="block-label">{{ block.label }}</span>
          </div>
        </div>
      </div>
      <div class="category">
        <div class="category-title">
          组合构件
          <span class="hint">列表由引擎能力自动生成；配方构件（数据定义）新增后无需改这里</span>
        </div>
        <div class="block-grid">
          <div v-for="entry in componentEntries" :key="`${entry.type}:${entry.fixtureType || 'default'}`"
            class="block-item" :class="{ active: placement.request?.label === entry.label }"
            :title="entry.description" @click="placeComponent(entry)">
            <span class="block-icon">{{ entry.icon }}</span>
            <span class="block-label">{{ entry.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 物品 ── -->
    <template v-else>
      <input v-model="keyword" class="search" placeholder="搜索物品…" spellcheck="false" />

      <div class="sources" aria-label="物品来源">
        <button v-for="source in sourceOptions" :key="source.key" type="button" class="source-filter"
          :class="{ active: activeSource === source.key }" @click="activeSource = source.key">
          {{ source.label }}
        </button>
      </div>

      <div class="cats">
        <button v-for="entry in categoryList" :key="entry.key" type="button" class="cat"
          :class="{ active: activeCategory === entry.key }" @click="toggleCategory(entry.key)">
          {{ entry.label }}<span class="count">{{ entry.count }}</span>
        </button>
      </div>

      <div class="grid" v-if="visibleItems.length">
        <div v-for="item in visibleItems" :key="item.id" class="card"
          :class="{ active: pendingItemId === item.id, review: item.needsReview }"
          :title="cardTitle(item)" @click="placeItem(item)">
          <button v-if="item.source === 'imported'" type="button" class="remove-item"
            title="从我的物品中删除" aria-label="删除导入物品" @click.stop="removeItem(item)">×</button>
          <svg class="thumb" viewBox="0 0 64 52" aria-hidden="true">
            <polygon :points="shape(item).top" fill="var(--studio-surface-strong, #d9d9dc)" opacity="0.95" />
            <polygon :points="shape(item).side" fill="var(--studio-surface, #c9c9cd)" opacity="0.8" />
            <polygon :points="shape(item).front" fill="var(--studio-surface-strong, #e6e6e8)" />
          </svg>
          <div class="card-title">
            <div class="name">{{ item.name }}</div>
            <span v-if="item.source === 'imported'" class="mine">我的</span>
          </div>
          <div class="dim">{{ formatSize(item) }}</div>
        </div>
      </div>

      <p v-else-if="catalog.loading" class="empty">正在读取物品库…</p>
      <p v-else-if="catalog.error" class="empty">物品库不可用：{{ catalog.error }}</p>
      <p v-else class="empty">没有匹配的物品</p>
    </template>

    <input ref="fileInput" type="file" accept=".wild" hidden @change="onImport" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { GeometryElement } from 'wild-core/types'
import { useSceneStore } from '../../stores/sceneStore'
import { useBlockPlacementStore } from '../../stores/blockPlacementStore'
import { useItemCatalogStore, type CatalogEntry } from '../../stores/itemCatalogStore'
import { buildComponentEntries, entryComponentType, type ComponentEntry } from '../../wild/componentDisplay'

const sceneStore = useSceneStore()
const placement = useBlockPlacementStore()
const catalog = useItemCatalogStore()

const tab = ref<'component' | 'item'>('component')

/* ────────────────────────── 构件 ────────────────────────── */

interface BlockTemplate {
  type: string
  label: string
  icon: string
  description: string
  defaults: Partial<GeometryElement>
}

/**
 * 基础构件：直接对应引擎的 element builder（12 类闭集）。
 * 这些不是「组合构件」，加一种就要动 `primitive/registry.ts`，所以保持静态。
 */
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

/** 引擎里注册了什么就列什么；装配逻辑在 `wild/componentDisplay.ts`，可被测试直接调用。 */
const componentEntries = computed<ComponentEntry[]>(() => buildComponentEntries())

function placeBlock(block: BlockTemplate) {
  if (!sceneStore.document || sceneStore.isReconstructing) return
  placement.begin({ kind: 'element', label: block.label, defaults: block.defaults })
}

function placeComponent(entry: ComponentEntry) {
  if (!sceneStore.document || sceneStore.isReconstructing) return
  // 配方构件的 type 不在 ComponentSpec 联合类型里（那是编译期闭集，运行期是字符串查表）。
  placement.begin({
    kind: 'component',
    type: entryComponentType(entry),
    fixtureType: entry.fixtureType,
    label: entry.label,
  })
}

/* ────────────────────────── 物品 ────────────────────────── */

const keyword = ref('')
const activeCategory = ref('')
const activeSource = ref<'all' | 'builtin' | 'imported'>('all')
const pendingItemId = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
let catalogLoaded = false

const categoryList = computed(() => catalog.categoryList)
const sourceOptions = [
  { key: 'all' as const, label: '全部' },
  { key: 'builtin' as const, label: '内置' },
  { key: 'imported' as const, label: '我的导入' },
]

const visibleItems = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return catalog.items.filter(item => {
    if (activeSource.value !== 'all' && item.source !== activeSource.value) return false
    if (activeCategory.value && item.category !== activeCategory.value) return false
    if (!query) return true
    return (
      item.name.toLowerCase().includes(query) ||
      item.id.includes(query) ||
      (item.tags ?? []).some(tag => String(tag).toLowerCase().includes(query))
    )
  })
})

/** 目录按需加载：不打开物品页就不发请求。 */
function switchToItems() {
  tab.value = 'item'
  if (catalogLoaded) return
  catalogLoaded = true
  void catalog.load()
}

function toggleCategory(key: string) {
  activeCategory.value = activeCategory.value === key ? '' : key
}

function formatSize(item: CatalogEntry) {
  const [width = 0, height = 0, depth = 0] = item.footprint ?? []
  return `${width.toFixed(2)}×${height.toFixed(2)}×${depth.toFixed(2)}m`
}

function cardTitle(item: CatalogEntry) {
  const lines = [item.name, formatSize(item), `${item.parts} 个零件`]
  if (item.needsReview) lines.push(`待检查：${(item.issues ?? []).slice(0, 3).join('；') || '导入时校验未通过'}`)
  return lines.join('\n')
}

/**
 * 等距体块图标：用实测 footprint 画三个面。
 * 没有二进制缩略图时，这比纯文字卡片更容易在网格里一眼分辨。
 */
function shape(item: CatalogEntry) {
  const [width = 0.5, height = 0.5, depth = 0.5] = item.footprint ?? []
  const span = Math.max(width, height, depth, 0.01)
  const scale = 30 / span
  const w = Math.max(width * scale, 4)
  const h = Math.max(height * scale, 3)
  const d = Math.max(depth * scale, 3) * 0.62
  const left = 8
  const bottom = 46
  const dx = d * 0.75
  const dy = d * 0.55
  const front = `${left},${bottom} ${left + w},${bottom} ${left + w},${bottom - h} ${left},${bottom - h}`
  const top = `${left},${bottom - h} ${left + w},${bottom - h} ${left + w + dx},${bottom - h - dy} ${left + dx},${bottom - h - dy}`
  const side = `${left + w},${bottom} ${left + w + dx},${bottom - dy} ${left + w + dx},${bottom - h - dy} ${left + w},${bottom - h}`
  return { front, top, side }
}

async function placeItem(item: CatalogEntry) {
  if (!sceneStore.document || sceneStore.isReconstructing) return
  try {
    const asset = await catalog.assetOf(item.id)
    pendingItemId.value = item.id
    placement.begin({ kind: 'item', label: item.name, asset })
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : '物品读取失败')
  }
}

function pickFile() {
  fileInput.value?.click()
}

async function onImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const result = await catalog.importFile(file)
    if (result.ok) {
      ElMessage.success(`已导入「${result.name}」`)
    } else {
      ElMessage.warning(`「${result.name}」未通过校验：${result.issues[0] || '请检查文件'}`)
    }
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : '导入失败')
  }
}

async function removeItem(item: CatalogEntry) {
  try {
    await ElMessageBox.confirm(`确定从物品库删除「${item.name}」？已经放入场景的实例不会受影响。`, '删除导入物品', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await catalog.removeImported(item.id)
    if (pendingItemId.value === item.id) {
      pendingItemId.value = ''
      placement.cancel()
    }
    ElMessage.success(`已删除「${item.name}」`)
  } catch (cause) {
    if (cause === 'cancel' || cause === 'close') return
    ElMessage.error(cause instanceof Error ? cause.message : '删除失败')
  }
}
</script>

<style scoped>
.library-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--studio-border);
}

.tabs {
  display: flex;
  gap: 4px;
}

.tab {
  font-size: 12px;
  padding: 3px 10px;
  color: var(--studio-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
}

.tab.active {
  color: var(--studio-text);
  background: var(--studio-hover);
  border-color: var(--studio-accent-border);
}

.header-actions {
  display: flex;
  gap: 4px;
}

.ghost {
  font-size: 11px;
  padding: 2px 6px;
  color: var(--studio-muted);
  background: transparent;
  border: 1px solid var(--studio-border);
  border-radius: 3px;
  cursor: pointer;
}

.ghost:hover {
  color: var(--studio-text);
  background: var(--studio-hover);
}

.placement-help {
  margin: 6px 12px 0;
  color: var(--studio-muted);
  font-size: 11px;
  line-height: 1.5;
}

.scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 10px 12px;
}

.category {
  margin-bottom: 16px;
}

.category-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.4px;
  color: var(--studio-muted);
  margin-bottom: 8px;
}

.category-title .hint {
  font-size: 10px;
  font-weight: 400;
  opacity: 0.7;
  letter-spacing: 0;
  line-height: 1.4;
}

.block-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.block-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 6px;
  background: var(--studio-surface);
  border: 1px solid var(--studio-border);
  border-radius: 4px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.block-item:hover {
  background: var(--studio-hover);
}

.block-item.active {
  border-color: var(--studio-accent-border);
  background: var(--studio-hover);
}

.block-icon {
  font-size: 20px;
  line-height: 1;
}

.block-label {
  font-size: 11px;
  text-align: center;
  color: var(--studio-text);
}

.count {
  margin-left: 3px;
  opacity: 0.65;
}

.search {
  margin: 8px 12px 6px;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--studio-text);
  background: var(--studio-surface);
  border: 1px solid var(--studio-border);
  border-radius: 3px;
  outline: none;
}

.search:focus {
  border-color: var(--studio-accent-border);
}

.cats {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 0 12px 8px;
}

.sources {
  display: flex;
  gap: 4px;
  padding: 0 12px 6px;
}

.source-filter {
  padding: 3px 8px;
  color: var(--studio-muted);
  font-size: 11px;
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  cursor: pointer;
}

.source-filter.active {
  color: var(--studio-text);
  border-bottom-color: var(--studio-accent-border);
}

.cat {
  font-size: 11px;
  padding: 2px 7px;
  color: var(--studio-muted);
  background: transparent;
  border: 1px solid var(--studio-border);
  border-radius: 10px;
  cursor: pointer;
}

.cat.active {
  color: var(--studio-text);
  background: var(--studio-hover);
  border-color: var(--studio-accent-border);
}

.grid {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  padding: 0 10px 12px;
  align-content: start;
}

.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 6px 7px;
  background: var(--studio-surface);
  border: 1px solid var(--studio-border);
  border-radius: 4px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.remove-item {
  position: absolute;
  top: 3px;
  right: 3px;
  z-index: 1;
  width: 18px;
  height: 18px;
  padding: 0;
  color: var(--studio-muted);
  line-height: 16px;
  background: var(--studio-bg);
  border: 1px solid var(--studio-border);
  border-radius: 50%;
  cursor: pointer;
}

.remove-item:hover {
  color: var(--studio-red, #d65c5c);
}

.card:hover {
  background: var(--studio-hover);
}

.card.active {
  border-color: var(--studio-accent-border);
  background: var(--studio-hover);
}

.card.review {
  border-style: dashed;
  border-color: #b4802a;
}

.thumb {
  width: 100%;
  height: 46px;
}

.name {
  font-size: 11px;
  line-height: 1.3;
  color: var(--studio-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.card-title .name {
  flex: 1;
  min-width: 0;
}

.mine {
  flex: 0 0 auto;
  padding: 1px 4px;
  color: var(--studio-accent);
  font-size: 9px;
  border: 1px solid var(--studio-accent-border);
  border-radius: 8px;
}

.dim {
  font-size: 10px;
  color: var(--studio-muted);
  font-variant-numeric: tabular-nums;
}

.empty {
  margin: 16px 12px;
  color: var(--studio-muted);
  font-size: 12px;
}
</style>
