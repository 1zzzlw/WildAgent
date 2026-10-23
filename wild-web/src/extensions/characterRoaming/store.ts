import { defineStore } from 'pinia'
import { ref } from 'vue'

export type CharacterView = 'first' | 'third'

// 临时体验状态；不进入文档、撤销栈或持久化设置。
export const useCharacterRoamingStore = defineStore('characterRoaming', () => {
  const active = ref(false)
  const locked = ref(false)
  const view = ref<CharacterView>('third')
  const interactionLabel = ref('')
  const message = ref('')
  const captureNonce = ref(0)

  function start() { message.value = ''; active.value = true }
  function stop() { active.value = false; locked.value = false; interactionLabel.value = '' }
  function toggleView() { view.value = view.value === 'third' ? 'first' : 'third' }
  function capture() { captureNonce.value += 1 }

  return { active, locked, view, interactionLabel, message, captureNonce, start, stop, toggleView, capture }
})
