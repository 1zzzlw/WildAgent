import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type PanelType = 'tools' | 'sceneTree' | 'blockLibrary' | 'properties' | 'validation' | 'assets' | 'look' | 'aiChat'
export const PANEL_IDS: PanelType[] = ['tools', 'sceneTree', 'blockLibrary', 'properties', 'validation', 'assets', 'look', 'aiChat']
const STORAGE_KEY = 'wild_editor_layout_v2'
function readPreferences() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {} } catch { return {} }
}
export const useUIStore = defineStore('ui', () => {
  const preferences = readPreferences()
  const activePanel = ref<PanelType>(PANEL_IDS.includes(preferences.panel) ? preferences.panel : 'tools')
  const panelOpen = ref(preferences.open !== false)
  const panelWidth = ref(Number.isFinite(preferences.width) ? Math.min(760, Math.max(300, preferences.width)) : 360)
  const viewportFocused = ref(false)
  const shortcutsVisible = ref(false)
  const animationsEnabled = ref(preferences.animations !== false)
  const soundsEnabled = ref(false)
  try { soundsEnabled.value = localStorage.getItem('wild_editor_sound') === 'true' } catch { /* 内存偏好仍可用。 */ }
  function openPanel(panel: PanelType) {
    activePanel.value = panel
    panelOpen.value = true
    viewportFocused.value = false
  }
  function selectPanel(panel: PanelType) {
    if (panel === activePanel.value) panelOpen.value = !panelOpen.value
    else openPanel(panel)
  }
  function setPanelWidth(width: number) { panelWidth.value = Math.max(300, Math.min(760, width)) }
  watch([activePanel, panelOpen, panelWidth, animationsEnabled], ([panel, open, width, animations]) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ panel, open, width, animations })) } catch { /* 偏好存储不可用。 */ }
  })
  watch(soundsEnabled, value => {
    try { localStorage.setItem('wild_editor_sound', String(value)) } catch { /* 静音不影响编辑。 */ }
  })
  return { activePanel, panelOpen, panelWidth, viewportFocused, shortcutsVisible,
    animationsEnabled, soundsEnabled, openPanel, selectPanel, setPanelWidth }
})
