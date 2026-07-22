<template>
  <div class="bottom-panel" :style="{ height: `${height}px` }">
    <div class="panel-header">
      <span class="panel-title">AI 对话</span>
      <el-button class="close-btn" link @click="uiStore.toggleBottomPanel" aria-label="关闭 AI 对话">×</el-button>
    </div>
    <div class="resize-handle" @mousedown="startResize" title="拖拽调整高度"></div>
    <div class="panel-content">
      <AIChatPanel />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useUIStore } from '../../stores/uiStore'
import AIChatPanel from '../panels/AIChatPanel.vue'

const props = defineProps<{
  height: number
}>()

const uiStore = useUIStore()
const isResizing = ref(false)
let startY = 0
let startHeight = 0

function startResize(event: MouseEvent) {
  event.preventDefault()
  isResizing.value = true
  startY = event.clientY
  startHeight = props.height
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'

  window.addEventListener('mousemove', onResize)
  window.addEventListener('mouseup', stopResize)
}

function onResize(event: MouseEvent) {
  if (!isResizing.value) return

  const deltaY = startY - event.clientY
  const nextHeight = Math.min(Math.max(startHeight + deltaY, 180), 600)
  uiStore.bottomPanelHeight = nextHeight
}

function stopResize() {
  if (!isResizing.value) return

  isResizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onResize)
  window.removeEventListener('mouseup', stopResize)
}

onBeforeUnmount(() => {
  stopResize()
})
</script>

<style scoped>
.bottom-panel {
  background: #252526;
  border-top: 1px solid #3e3e42;
  display: flex;
  flex-direction: column;
}

.panel-header {
  height: 36px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  display: flex;
  align-items: center;
  padding: 0 12px;
  justify-content: space-between;
}

.resize-handle {
  height: 8px;
  cursor: row-resize;
  background: transparent;
  flex-shrink: 0;
  position: relative;
}

.resize-handle::before {
  content: '';
  position: absolute;
  top: 2px;
  left: 0;
  right: 0;
  height: 4px;
  border-top: 1px solid #3e3e42;
}

.panel-title {
  font-size: 13px;
  color: #cccccc;
}

.close-btn {
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  color: #cccccc;
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
  transition: all 0.15s;
  padding: 0;
}

.close-btn:hover {
  background: #3e3e42;
}

.panel-content {
  flex: 1;
  overflow: hidden;
}
</style>
