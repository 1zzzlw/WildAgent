<template>
  <div class="wild-editor">
    <EditorTopBar />
    <div class="editor-main">
      <LeftPanel v-if="uiStore.leftPanelVisible" :width="uiStore.leftPanelWidth" />
      <div class="viewport-container">
        <CanvasViewport />
      </div>
      <RightPanel v-if="uiStore.rightPanelVisible" :width="uiStore.rightPanelWidth" />
    </div>
    <BottomPanel v-if="uiStore.bottomPanelVisible" :height="uiStore.bottomPanelHeight" />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useUIStore } from './stores/uiStore'
import { useSceneStore } from './stores/sceneStore'
import EditorTopBar from './components/layout/EditorTopBar.vue'
import LeftPanel from './components/layout/LeftPanel.vue'
import RightPanel from './components/layout/RightPanel.vue'
import BottomPanel from './components/layout/BottomPanel.vue'
import CanvasViewport from './components/viewport/CanvasViewport.vue'

const uiStore = useUIStore()
const sceneStore = useSceneStore()

onMounted(() => {
  // 初始化空场景（构件库需要document存在）
  const emptyDoc = sceneStore.createEmptyDocument()
  // 只设置document，不调用loadBlueprint（避免自动reconstruct）
  sceneStore.document = emptyDoc
  console.log('App mounted - Empty document created, GridHelper should be visible');
})
</script>

<style scoped>
.wild-editor {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  color: #cccccc;
  overflow: hidden;
}

.editor-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.viewport-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}
</style>
