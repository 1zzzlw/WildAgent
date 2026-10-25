import { defineStore } from 'pinia'
import { shallowRef } from 'vue'
import { generateId } from '../utils/common'
import type { BlockPlacementChoice, BlockPlacementRequest } from '../wild/blockPlacement'

/** 只保存待放置选择；预览不写入蓝图与撤销历史。 */
export const useBlockPlacementStore = defineStore('blockPlacement', () => {
  const request = shallowRef<BlockPlacementRequest | null>(null)
  function begin(choice: BlockPlacementChoice) {
    request.value = { ...choice, id: generateId(choice.kind === 'element' ? choice.defaults.type || 'element' : choice.type) }
  }
  function cancel() { request.value = null }
  return { request, begin, cancel }
})
