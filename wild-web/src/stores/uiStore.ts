import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type PanelType = 'sceneTree' | 'blockLibrary' | 'properties' | 'validation' | 'assets' | 'look' | 'aiChat'
export const PANEL_IDS: PanelType[] = ['sceneTree', 'blockLibrary', 'properties', 'validation', 'assets', 'look', 'aiChat']
const STORAGE_KEY = 'wild_editor_layout_v2'
function readPreferences() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {} } catch { return {} }
}
export const useUIStore = defineStore('ui', () => {
  const preferences = readPreferences()
  const activePanel = ref<PanelType>(PANEL_IDS.includes(preferences.panel) ? preferences.panel : 'sceneTree')
  const panelOpen = ref(preferences.open !== false)
  const panelWidth = ref(Number.isFinite(preferences.width) ? Math.min(760, Math.max(300, preferences.width)) : 360)
  const viewportFocused = ref(false)
  const shortcutsVisible = ref(false)
  const modelConfigVisible = ref(false)
  const sessionPickerVisible = ref(false)
  const animationsEnabled = true
  const soundsEnabled = true
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
  watch([activePanel, panelOpen, panelWidth], ([panel, open, width]) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ panel, open, width })) } catch { /* 偏好存储不可用。 */ }
  })
  return { activePanel, panelOpen, panelWidth, viewportFocused, shortcutsVisible, modelConfigVisible, sessionPickerVisible,
    animationsEnabled, soundsEnabled, openPanel, selectPanel, setPanelWidth }
})
