<template>
  <div class="bottom-panel" :style="{ height: `${height}px` }">
    <div class="panel-header">
      <span class="panel-title">AI 对话</span>
      <button class="close-btn" @click="uiStore.toggleBottomPanel">×</button>
    </div>
    <div class="panel-content">
      <AIChatPanel />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useUIStore } from '../../stores/uiStore'
import AIChatPanel from '../panels/AIChatPanel.vue'

defineProps<{
  height: number
}>()

const uiStore = useUIStore()
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
}

.close-btn:hover {
  background: #3e3e42;
}

.panel-content {
  flex: 1;
  overflow: hidden;
}
</style>
