<template>
  <VisitorNameGate v-if="!editorReady" @confirmed="enterEditor" />
  <div v-else class="wild-editor">
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
import { onMounted, onUnmounted, ref } from 'vue'
import { agentBridge } from './agent/agentBridge'
import VisitorNameGate from './extensions/presence/VisitorNameGate.vue'
import { usePresenceStore } from './extensions/presence/store'
import { useUIStore } from './stores/uiStore'
import { useSceneStore } from './stores/sceneStore'
import EditorTopBar from './components/layout/EditorTopBar.vue'
import LeftPanel from './components/layout/LeftPanel.vue'
import RightPanel from './components/layout/RightPanel.vue'
import BottomPanel from './components/layout/BottomPanel.vue'
import CanvasViewport from './components/viewport/CanvasViewport.vue'

const uiStore = useUIStore()
const sceneStore = useSceneStore()
const presenceStore = usePresenceStore()
const editorReady = ref(false)

function enterEditor() {
  if (editorReady.value) return
  editorReady.value = true
  // 初始化空场景（构件库需要document存在）
  const emptyDoc = sceneStore.createEmptyDocument()
  // 只设置document，不调用loadBlueprint（避免自动reconstruct）
  sceneStore.document = emptyDoc
  agentBridge.connect()
  console.log('App mounted - Empty document created, GridHelper should be visible');
}

onMounted(() => {
  if (presenceStore.hasVisitorName) enterEditor()
})

onUnmounted(() => agentBridge.disconnect())
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
