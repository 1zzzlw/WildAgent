/**
 * 编辑器布局状态。
 *
 * AI 工作区支持三种模式：
 * - bottom：底部抽屉，适合简短对话；
 * - side：右侧工作区，适合一边观察三维视口一边跟踪 Agent；
 * - focus：专注模式，适合阅读长计划、审核结果和校验日志。
 *
 * AI 面板的显示状态、模式和尺寸保存在当前浏览器的 localStorage 中。
 * 这些是每个用户自己的界面偏好，不会写入服务端 .env。
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type PanelType = 'sceneTree' | 'blockLibrary' | 'properties' | 'validation' | 'assets' | 'look' | 'aiChat'
export type AIPanelMode = 'bottom' | 'side' | 'focus'

const AI_LAYOUT_STORAGE_KEY = 'wild_ai_workspace_layout_v1'
const DEFAULT_BOTTOM_HEIGHT = 300
const DEFAULT_SIDE_WIDTH = 520

interface StoredAILayout {
  visible?: boolean
  mode?: AIPanelMode
  restoreMode?: Exclude<AIPanelMode, 'focus'>
  bottomHeight?: number
  sideWidth?: number
}

function isAIPanelMode(value: unknown): value is AIPanelMode {
  return value === 'bottom' || value === 'side' || value === 'focus'
}

function clamp(value: unknown, min: number, max: number, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(Math.max(parsed, min), max)
}

function loadAILayout(): StoredAILayout {
  if (typeof window === 'undefined') return {}
  try {
    const stored = JSON.parse(window.localStorage.getItem(AI_LAYOUT_STORAGE_KEY) || '{}')
    return stored && typeof stored === 'object' ? stored as StoredAILayout : {}
  } catch {
    return {}
  }
}

export const useUIStore = defineStore('ui', () => {
  const storedLayout = loadAILayout()
  const storedMode = isAIPanelMode(storedLayout.mode) ? storedLayout.mode : 'bottom'

  const leftPanelVisible = ref(true)
  const rightPanelVisible = ref(true)
  const aiPanelVisible = ref(storedLayout.visible ?? true)

  const leftActivePanel = ref<'sceneTree' | 'blockLibrary'>('sceneTree')
  const rightActivePanel = ref<'properties' | 'validation' | 'assets' | 'look'>('properties')

  const leftPanelWidth = ref(280)
  const rightPanelWidth = ref(320)
  const aiPanelMode = ref<AIPanelMode>(storedMode)
  const aiPanelRestoreMode = ref<Exclude<AIPanelMode, 'focus'>>(
    storedLayout.restoreMode === 'side' ? 'side' : 'bottom',
  )
  const aiPanelBottomHeight = ref(clamp(storedLayout.bottomHeight, 180, 1200, DEFAULT_BOTTOM_HEIGHT))
  const aiPanelSideWidth = ref(clamp(storedLayout.sideWidth, 360, 900, DEFAULT_SIDE_WIDTH))

  function toggleLeftPanel() {
    leftPanelVisible.value = !leftPanelVisible.value
  }

  function toggleRightPanel() {
    rightPanelVisible.value = !rightPanelVisible.value
  }

  function toggleAIPanel() {
    aiPanelVisible.value = !aiPanelVisible.value
  }

  function setAIPanelMode(mode: AIPanelMode) {
    if (mode === 'focus' && aiPanelMode.value !== 'focus') {
      aiPanelRestoreMode.value = aiPanelMode.value
    } else if (mode !== 'focus') {
      aiPanelRestoreMode.value = mode
    }
    aiPanelMode.value = mode
    aiPanelVisible.value = true
  }

  function exitAIFocusMode() {
    if (aiPanelMode.value === 'focus') {
      aiPanelMode.value = aiPanelRestoreMode.value
    }
  }

  function setAIPanelBottomHeight(height: number) {
    const viewportHeight = typeof window === 'undefined' ? 900 : window.innerHeight
    const maxHeight = Math.max(180, viewportHeight - 48 - 72)
    aiPanelBottomHeight.value = clamp(height, 180, maxHeight, DEFAULT_BOTTOM_HEIGHT)
  }

  function setAIPanelSideWidth(width: number) {
    const viewportWidth = typeof window === 'undefined' ? 1440 : window.innerWidth
    const maxWidth = Math.max(360, Math.min(900, viewportWidth - 420))
    aiPanelSideWidth.value = clamp(width, 360, maxWidth, DEFAULT_SIDE_WIDTH)
  }

  function setLeftActivePanel(panel: 'sceneTree' | 'blockLibrary') {
    leftActivePanel.value = panel
    leftPanelVisible.value = true
  }

  function setRightActivePanel(panel: 'properties' | 'validation' | 'assets' | 'look') {
    rightActivePanel.value = panel
    rightPanelVisible.value = true
  }

  watch(
    [aiPanelVisible, aiPanelMode, aiPanelRestoreMode, aiPanelBottomHeight, aiPanelSideWidth],
    ([visible, mode, restoreMode, bottomHeight, sideWidth]) => {
      if (typeof window === 'undefined') return
      const value: StoredAILayout = { visible, mode, restoreMode, bottomHeight, sideWidth }
      try {
        window.localStorage.setItem(AI_LAYOUT_STORAGE_KEY, JSON.stringify(value))
      } catch {
        // 隐私模式或浏览器禁用存储时，布局仍在当前页面内正常工作。
      }
    },
  )

  return {
    leftPanelVisible,
    rightPanelVisible,
    aiPanelVisible,
    leftActivePanel,
    rightActivePanel,
    leftPanelWidth,
    rightPanelWidth,
    aiPanelMode,
    aiPanelBottomHeight,
    aiPanelSideWidth,
    toggleLeftPanel,
    toggleRightPanel,
    toggleAIPanel,
    setAIPanelMode,
    exitAIFocusMode,
    setAIPanelBottomHeight,
    setAIPanelSideWidth,
    setLeftActivePanel,
    setRightActivePanel,
  }
})
