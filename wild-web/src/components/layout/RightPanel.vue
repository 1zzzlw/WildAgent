<template>
  <div class="right-panel" :style="{ width: `${width}px` }">
    <div class="panel-tabs">
      <el-button class="tab" :class="{ active: uiStore.rightActivePanel === 'properties' }"
        @click="uiStore.setRightActivePanel('properties')">
        属性
      </el-button>
      <el-button class="tab" :class="{ active: uiStore.rightActivePanel === 'validation' }"
        @click="uiStore.setRightActivePanel('validation')">
        校验
      </el-button>
    </div>
    <div class="panel-content">
      <PropertyPanel v-if="uiStore.rightActivePanel === 'properties'" />
      <ValidationPanel v-if="uiStore.rightActivePanel === 'validation'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useUIStore } from '../../stores/uiStore'
import PropertyPanel from '../panels/PropertyPanel.vue'
import ValidationPanel from '../panels/ValidationPanel.vue'

defineProps<{
  width: number
}>()

const uiStore = useUIStore()
</script>

<style scoped>
.right-panel {
  background: #252526;
  border-left: 1px solid #3e3e42;
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
