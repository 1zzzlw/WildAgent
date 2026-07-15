/**
 * 选择状态管理 Store
 * 
 * 管理构件选择和悬停状态：
 * - selectedIds: 选中的构件 ID 列表（支持多选）
 * - hoveredId: 当前悬停的构件 ID
 * 
 * 核心方法：
 * - select(): 选中构件（支持 addToSelection 参数多选）
 * - deselect(): 取消选中
 * - toggleSelection(): 切换选中状态
 * - setHovered(): 设置悬停状态
 * 
 * 用于：
 * - 场景树点击选中
 * - 3D 视口点击选中
 * - 属性面板显示选中构件的参数
 * - Agent 处理"修改这个"等指代时获取选中元素
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useSelectionStore = defineStore('selection', () => {
  const selectedIds = ref<string[]>([])
  const hoveredId = ref<string | null>(null)

  const hasSelection = computed(() => selectedIds.value.length > 0)
  const isSingleSelection = computed(() => selectedIds.value.length === 1)
  const isMultiSelection = computed(() => selectedIds.value.length > 1)

  function select(id: string, addToSelection = false) {
    if (addToSelection) {
      if (!selectedIds.value.includes(id)) {
        selectedIds.value.push(id)
      }
    } else {
      selectedIds.value = [id]
    }
  }

  function deselect(id: string) {
    selectedIds.value = selectedIds.value.filter(i => i !== id)
  }

  function clearSelection() {
    selectedIds.value = []
  }

  function toggleSelection(id: string) {
    if (selectedIds.value.includes(id)) {
      deselect(id)
    } else {
      select(id, true)
    }
  }

  function setHovered(id: string | null) {
    hoveredId.value = id
  }

  function isSelected(id: string): boolean {
    return selectedIds.value.includes(id)
  }

  function isHovered(id: string): boolean {
    return hoveredId.value === id
  }

  return {
    selectedIds,
    hoveredId,
    hasSelection,
    isSingleSelection,
    isMultiSelection,
    select,
    deselect,
    clearSelection,
    toggleSelection,
    setHovered,
    isSelected,
    isHovered
  }
})
