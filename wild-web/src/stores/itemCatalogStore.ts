import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { GeometryElement, MaterialDef, PBRTextureSetAsset } from '../types/blueprint'

/** 目录条目。字段与后端 `/api/item-catalog` 返回一致。 */
export interface CatalogEntry {
  id: string
  name: string
  category: string
  tags: string[]
  /** [宽, 高, 深]，米。来自生成时的几何实测。 */
  footprint: number[]
  parts: number
  file: string
  source?: 'builtin' | 'imported'
  needsReview?: boolean
  issues?: string[]
}

export interface CatalogAsset {
  itemId: string
  parts: GeometryElement[]
  materials: Record<string, MaterialDef>
  assets: Record<string, PBRTextureSetAsset>
}

/**
 * 物品目录。
 *
 * 物品是数据不是引擎能力：这里拿到的 `parts` 就是一组 primitive/solid，
 * 放置时直接写进 `geometry.elements`，不经过任何构件注册表。
 */
export const useItemCatalogStore = defineStore('itemCatalog', () => {
  const items = ref<CatalogEntry[]>([])
  const categories = ref<Record<string, number>>({})
  const loading = ref(false)
  const error = ref('')
  const loaded = ref(false)
  const assetCache = new Map<string, CatalogAsset>()

  async function load(force = false) {
    if (loading.value) return
    if (loaded.value && !force) return
    loading.value = true
    error.value = ''
    try {
      const response = await fetch('/api/item-catalog', { cache: 'no-store' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json()
      items.value = Array.isArray(payload.items) ? payload.items : []
      categories.value = payload.categories ?? {}
      loaded.value = true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '物品库加载失败'
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function assetOf(itemId: string): Promise<CatalogAsset> {
    const cached = assetCache.get(itemId)
    if (cached) return cached
    const response = await fetch(`/api/item-catalog/${encodeURIComponent(itemId)}`, { cache: 'no-store' })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload?.detail || `物品 ${itemId} 读取失败 (HTTP ${response.status})`)
    }
    const blueprint = await response.json()
    const elements = blueprint?.geometry?.elements
    if (!Array.isArray(elements) || elements.length === 0) throw new Error(`物品 ${itemId} 没有几何`)
    const asset = {
      itemId,
      parts: elements as GeometryElement[],
      materials: blueprint?.materials && typeof blueprint.materials === 'object'
        ? blueprint.materials as Record<string, MaterialDef>
        : {},
      assets: blueprint?.assets && typeof blueprint.assets === 'object'
        ? blueprint.assets as Record<string, PBRTextureSetAsset>
        : {},
    }
    assetCache.set(itemId, asset)
    return asset
  }

  async function importFile(file: File): Promise<{ ok: boolean; issues: string[]; name: string }> {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch('/api/item-catalog/import', { method: 'POST', body: form })
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}))
      const problem = detail?.detail
      const message = typeof problem === 'string'
        ? problem
        : typeof problem?.message === 'string'
          ? `${problem.message}${Array.isArray(problem.issues) && problem.issues.length ? `：${problem.issues[0]}` : ''}`
          : `导入失败 (HTTP ${response.status})`
      throw new Error(message)
    }
    const payload = await response.json()
    assetCache.delete(String(payload.item?.id ?? ''))
    await load(true)
    return {
      ok: Boolean(payload.ok),
      issues: Array.isArray(payload.item?.issues) ? payload.item.issues : [],
      name: String(payload.item?.name ?? file.name),
    }
  }

  async function removeImported(itemId: string): Promise<void> {
    const response = await fetch(`/api/item-catalog/${encodeURIComponent(itemId)}`, { method: 'DELETE' })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload?.detail || `删除失败 (HTTP ${response.status})`)
    }
    assetCache.delete(itemId)
    await load(true)
  }

  const categoryLabels: Record<string, string> = {
    furniture: '家具',
    appliance: '电器',
    kitchen: '厨房',
    bathroom: '卫浴',
    outdoor: '户外',
    lighting: '灯具',
    decor: '陈设',
    imported: '导入',
  }

  const categoryList = computed(() =>
    Object.entries(categories.value)
      .map(([key, count]) => ({ key, count, label: categoryLabels[key] ?? key }))
      .sort((a, b) => b.count - a.count),
  )

  return { items, categories, categoryList, categoryLabels, loading, error, loaded, load, assetOf, importFile, removeImported }
})
