/**
 * 撤销重做历史管理 Store
 * 
 * 管理操作历史，支持撤销和重做：
 * - entries: 历史记录列表（最多保存 50 条）
 * - currentIndex: 当前位置指针
 * 
 * HistoryEntry 包含：
 * - label: 操作描述
 * - before/after: 修改前后的 Blueprint
 * - patch: 应用的 ScenePatch
 * 
 * 核心方法：
 * - push(): 添加历史记录
 * - undo(): 撤销到上一个状态
 * - redo(): 重做到下一个状态
 * 
 * 用于：
 * - 顶部工具栏的撤销/重做按钮
 * - 快捷键 Ctrl+Z / Ctrl+Y
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Blueprint } from '../types/blueprint'
import type { ScenePatch } from '../types/scenePatch'

export interface HistoryEntry {
  label: string
  before: Blueprint
  after: Blueprint
  patch: ScenePatch
  timestamp: number
}

export const useHistoryStore = defineStore('history', () => {
  const entries = ref<HistoryEntry[]>([])
  const currentIndex = ref(-1)

  const canUndo = computed(() => currentIndex.value >= 0)
  const canRedo = computed(() => currentIndex.value < entries.value.length - 1)

  function push(entry: HistoryEntry) {
    // 清除当前位置之后的历史
    if (currentIndex.value < entries.value.length - 1) {
      entries.value = entries.value.slice(0, currentIndex.value + 1)
    }

    entries.value.push(entry)
    currentIndex.value++

    // 限制历史长度
    const MAX_HISTORY = 50
    if (entries.value.length > MAX_HISTORY) {
      entries.value.shift()
      currentIndex.value--
    }
  }

  function undo(): HistoryEntry | null {
    if (!canUndo.value) return null
    const entry = entries.value[currentIndex.value]
    currentIndex.value--
    return entry
  }

  function redo(): HistoryEntry | null {
    if (!canRedo.value) return null
    currentIndex.value++
    const entry = entries.value[currentIndex.value]
    return entry
  }

  function clear() {
    entries.value = []
    currentIndex.value = -1
  }

  function getCurrentState(): HistoryEntry | null {
    if (currentIndex.value < 0) return null
    return entries.value[currentIndex.value]
  }

  return {
    entries,
    currentIndex,
    canUndo,
    canRedo,
    push,
    undo,
    redo,
    clear,
    getCurrentState
  }
})
