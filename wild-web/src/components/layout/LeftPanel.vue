<template>
  <div class="left-panel" :style="{ width: `${width}px` }">
    <div class="panel-tabs">
      <button :class="['tab', { active: uiStore.leftActivePanel === 'sceneTree' }]"
        @click="uiStore.setLeftActivePanel('sceneTree')">
        场景树
      </button>
      <button :class="['tab', { active: uiStore.leftActivePanel === 'blockLibrary' }]"
        @click="uiStore.setLeftActivePanel('blockLibrary')">
        构件库
      </button>
    </div>
    <div class="panel-content">
      <SceneTree v-if="uiStore.leftActivePanel === 'sceneTree'" />
      <BlockLibrary v-if="uiStore.leftActivePanel === 'blockLibrary'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useUIStore } from '../../stores/uiStore'
import SceneTree from '../panels/SceneTree.vue'
import BlockLibrary from '../panels/BlockLibrary.vue'

defineProps<{
  width: number
}>()

const uiStore = useUIStore()
</script>

<style scoped>
.left-panel {
  background: #252526;
  border-right: 1px solid #3e3e42;
  display: flex;
  flex-direction: column;
}

.panel-tabs {
  height: 36px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  display: flex;
}

.tab {
  flex: 1;
  background: transparent;
  border: none;
  color: #cccccc;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.tab:hover {
  background: #3e3e42;
}

.tab.active {
  background: #252526;
  color: #ffffff;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
}
</style>
