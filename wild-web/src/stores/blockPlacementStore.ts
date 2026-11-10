import { defineStore } from 'pinia'
import { shallowRef } from 'vue'
import { generateId } from '../utils/common'
import type { BlockPlacementChoice, BlockPlacementRequest } from '../wild/blockPlacement'
import { useAuthStore } from './authStore'

/** 只保存待放置选择；预览不写入蓝图与撤销历史。 */
export const useBlockPlacementStore = defineStore('blockPlacement', () => {
  const request = shallowRef<BlockPlacementRequest | null>(null)
  function begin(choice: BlockPlacementChoice) {
    if (!useAuthStore().canEdit) return
    const prefix = choice.kind === 'element'
      ? choice.defaults.type || 'element'
      : choice.kind === 'item'
        ? 'item'
        : choice.type
    request.value = { ...choice, id: generateId(prefix) }
  }
  function cancel() { request.value = null }
  return { request, begin, cancel }
})
