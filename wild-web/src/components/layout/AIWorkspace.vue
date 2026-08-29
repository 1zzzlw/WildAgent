<template>
  <div :class="['ai-workspace', `ai-workspace--${uiStore.aiPanelMode}`]">
    <button
      v-if="uiStore.aiPanelMode !== 'focus'"
      type="button"
      :class="['resize-handle', `resize-handle--${uiStore.aiPanelMode}`]"
      :title="uiStore.aiPanelMode === 'bottom' ? '拖拽调整 AI 工作区高度' : '拖拽调整 AI 工作区宽度'"
      :aria-label="uiStore.aiPanelMode === 'bottom' ? '调整 AI 工作区高度' : '调整 AI 工作区宽度'"
      @pointerdown="startResize"
    ></button>

    <header class="workspace-header">
      <div class="workspace-heading">
        <strong>AI 工作区</strong>
        <span>{{ modeDescription }}</span>
      </div>

      <div class="workspace-actions" role="group" aria-label="AI 工作区显示方式">
        <button
          v-for="mode in panelModes"
          :key="mode.value"
          type="button"
          :class="['mode-button', { active: uiStore.aiPanelMode === mode.value }]"
          :title="mode.title"
          :aria-pressed="uiStore.aiPanelMode === mode.value"
          @click="setMode(mode.value)"
        >{{ mode.label }}</button>
        <button
          type="button"
          class="close-button"
          title="关闭 AI 工作区"
          aria-label="关闭 AI 工作区"
          @click="uiStore.toggleAIPanel"
        >×</button>
      </div>
    </header>

    <div class="workspace-content">
      <AIChatPanel />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useUIStore, type AIPanelMode } from '../../stores/uiStore'
import AIChatPanel from '../panels/AIChatPanel.vue'

const uiStore = useUIStore()
const isResizing = ref(false)
let startPosition = 0
let startSize = 0

const panelModes: Array<{ value: AIPanelMode; label: string; title: string }> = [
  { value: 'bottom', label: '底部', title: '适合简短对话和快速修改' },
  { value: 'side', label: '侧栏', title: '一边观察三维场景，一边跟踪 Agent' },
  { value: 'focus', label: '专注', title: '最大化阅读计划、审核和校验日志' },
]

const modeDescription = computed(() => ({
  bottom: '简洁对话',
  side: '对照三维场景',
  focus: 'Esc 返回上一布局',
})[uiStore.aiPanelMode])

function setMode(mode: AIPanelMode) {
  // 窄屏无法同时容纳三维视口和侧栏，直接进入专注模式，避免两边都不可用。
  if (mode === 'side' && window.innerWidth < 900) {
    uiStore.setAIPanelMode('focus')
    return
  }
  uiStore.setAIPanelMode(mode)
}

function startResize(event: PointerEvent) {
  event.preventDefault()
  isResizing.value = true
  startPosition = uiStore.aiPanelMode === 'bottom' ? event.clientY : event.clientX
  startSize = uiStore.aiPanelMode === 'bottom'
    ? uiStore.aiPanelBottomHeight
    : uiStore.aiPanelSideWidth
  document.body.style.cursor = uiStore.aiPanelMode === 'bottom' ? 'row-resize' : 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', onResize)
  window.addEventListener('pointerup', stopResize)
  window.addEventListener('pointercancel', stopResize)
}

function onResize(event: PointerEvent) {
  if (!isResizing.value) return
  if (uiStore.aiPanelMode === 'bottom') {
    uiStore.setAIPanelBottomHeight(startSize + startPosition - event.clientY)
  } else if (uiStore.aiPanelMode === 'side') {
    uiStore.setAIPanelSideWidth(startSize + startPosition - event.clientX)
  }
}

function stopResize() {
  if (!isResizing.value) return
  isResizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', onResize)
  window.removeEventListener('pointerup', stopResize)
  window.removeEventListener('pointercancel', stopResize)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && uiStore.aiPanelMode === 'focus') {
    uiStore.exitAIFocusMode()
  }
}

function handleWindowResize() {
  uiStore.setAIPanelBottomHeight(uiStore.aiPanelBottomHeight)
  uiStore.setAIPanelSideWidth(uiStore.aiPanelSideWidth)
  if (window.innerWidth < 900 && uiStore.aiPanelMode === 'side') {
    uiStore.setAIPanelMode('focus')
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', handleWindowResize)
  handleWindowResize()
})

onBeforeUnmount(() => {
  stopResize()
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleWindowResize)
})
</script>

<style scoped>
.ai-workspace {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #202023;
  color: #d7d7da;
}

.ai-workspace--bottom {
  border-top: 1px solid #3e3e42;
}

.ai-workspace--side {
  border-left: 1px solid #3e3e42;
}

.ai-workspace--focus {
  background: #1e1e20;
}

.workspace-header {
  height: 40px;
  flex: 0 0 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 10px 0 14px;
  border-bottom: 1px solid #3e3e42;
  background: #2d2d30;
}

.workspace-heading {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
  white-space: nowrap;
}

.workspace-heading strong {
  color: #e5e5e7;
  font-size: 13px;
  font-weight: 600;
}

.workspace-heading span {
  overflow: hidden;
  color: #85858d;
  font-size: 11px;
  text-overflow: ellipsis;
}

.workspace-actions {
  display: flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
}

.mode-button,
.close-button {
  height: 26px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: #a7a7ad;
  cursor: pointer;
  font-size: 11px;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.mode-button {
  padding: 0 9px;
}

.mode-button:hover,
.close-button:hover {
  background: #3b3b40;
  color: #f2f2f3;
}

.mode-button.active {
  border-color: rgba(104, 153, 212, 0.42);
  background: rgba(104, 153, 212, 0.15);
  color: #a9cff7;
}

.mode-button:focus-visible,
.close-button:focus-visible,
.resize-handle:focus-visible {
  outline: 2px solid #77aee8;
  outline-offset: 1px;
}

.close-button {
  width: 28px;
  padding: 0;
  font-size: 19px;
  line-height: 1;
}

.workspace-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
}

.resize-handle {
  z-index: 20;
  position: absolute;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
}

.resize-handle::after {
  content: '';
  position: absolute;
  background: transparent;
  transition: background 0.15s ease;
}

.resize-handle:hover::after {
  background: #6899d4;
}

.resize-handle--bottom {
  top: -4px;
  right: 0;
  left: 0;
  height: 8px;
  cursor: row-resize;
}

.resize-handle--bottom::after {
  top: 3px;
  right: 0;
  left: 0;
  height: 2px;
}

.resize-handle--side {
  top: 0;
  bottom: 0;
  left: -4px;
  width: 8px;
  cursor: col-resize;
}

.resize-handle--side::after {
  top: 0;
  bottom: 0;
  left: 3px;
  width: 2px;
}

.ai-workspace--side :deep(.message) {
  max-width: 94%;
}

.ai-workspace--focus :deep(.messages-timeline) {
  width: min(1100px, 100%);
  margin: 0 auto;
}

.ai-workspace--focus :deep(.input-container),
.ai-workspace--focus :deep(.connection-bar),
.ai-workspace--focus :deep(.content-toolbar) {
  padding-right: max(16px, calc((100% - 1100px) / 2));
  padding-left: max(16px, calc((100% - 1100px) / 2));
}

@media (max-width: 620px) {
  .workspace-heading span {
    display: none;
  }

  .mode-button {
    padding: 0 6px;
  }
}
</style>
