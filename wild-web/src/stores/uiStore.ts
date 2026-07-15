/**
 * UI 布局状态管理 Store
 * 
 * 管理编辑器界面布局和面板状态：
 * - 左侧面板：场景树 / 构件库（可切换）
 * - 右侧面板：属性 / 校验（可切换）
 * - 底部面板：AI 对话
 * - 面板显示/隐藏状态
 * - 面板宽度/高度
 * 
 * 核心方法：
 * - toggleLeftPanel() / toggleRightPanel() / toggleBottomPanel(): 切换面板显示
 * - setLeftActivePanel() / setRightActivePanel(): 设置激活的标签页
 * 
 * 用于：
 * - 保存用户的界面布局偏好
 * - 控制面板显示和隐藏
 * - 管理面板尺寸（可扩展为可拖拽调整）
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export type PanelType = 'sceneTree' | 'blockLibrary' | 'properties' | 'validation' | 'aiChat'

export const useUIStore = defineStore('ui', () => {
  const leftPanelVisible = ref(true)
  const rightPanelVisible = ref(true)
  const bottomPanelVisible = ref(true)
  
  const leftActivePanel = ref<'sceneTree' | 'blockLibrary'>('sceneTree')
  const rightActivePanel = ref<'properties' | 'validation'>('properties')

  const leftPanelWidth = ref(280)
  const rightPanelWidth = ref(320)
  const bottomPanelHeight = ref(240)

  function toggleLeftPanel() {
    leftPanelVisible.value = !leftPanelVisible.value
  }

  function toggleRightPanel() {
    rightPanelVisible.value = !rightPanelVisible.value
  }

  function toggleBottomPanel() {
    bottomPanelVisible.value = !bottomPanelVisible.value
  }

  function setLeftActivePanel(panel: 'sceneTree' | 'blockLibrary') {
    leftActivePanel.value = panel
    leftPanelVisible.value = true
  }

  function setRightActivePanel(panel: 'properties' | 'validation') {
    rightActivePanel.value = panel
    rightPanelVisible.value = true
  }

  return {
    leftPanelVisible,
    rightPanelVisible,
    bottomPanelVisible,
    leftActivePanel,
    rightActivePanel,
    leftPanelWidth,
    rightPanelWidth,
    bottomPanelHeight,
    toggleLeftPanel,
    toggleRightPanel,
    toggleBottomPanel,
    setLeftActivePanel,
    setRightActivePanel
  }
})
