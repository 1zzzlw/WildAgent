import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

type Theme = 'light' | 'dark'
const STORAGE_KEY = 'wild_editor_theme'

export const useThemeStore = defineStore('theme', () => {
  let saved: string | null = null
  try { saved = localStorage.getItem(STORAGE_KEY) } catch { /* 使用默认主题。 */ }
  const theme = ref<Theme>(saved === 'dark' ? 'dark' : 'light')
  const isDark = computed(() => theme.value === 'dark')
  watch(theme, value => {
    document.documentElement.dataset.theme = value
    try { localStorage.setItem(STORAGE_KEY, value) } catch { /* 当前页面仍然可以切换。 */ }
  }, { immediate: true, flush: 'sync' })
  function toggle() { theme.value = isDark.value ? 'light' : 'dark' }
  return { theme, isDark, toggle }
})
