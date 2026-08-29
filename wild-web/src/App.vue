<template>
  <VisitorNameGate v-if="!editorReady" @confirmed="enterEditor" />
  <div v-else :class="['wild-editor', aiLayoutClass]">
    <EditorTopBar class="editor-topbar" />
    <div class="editor-main">
      <LeftPanel v-if="uiStore.leftPanelVisible" class="left-panel-slot" :width="uiStore.leftPanelWidth" />
      <div class="viewport-container">
        <CanvasViewport />
      </div>
      <RightPanel v-if="uiStore.rightPanelVisible" class="right-panel-slot" :width="uiStore.rightPanelWidth" />
    </div>
    <section v-if="uiStore.aiPanelVisible" class="ai-workspace-slot" :style="aiWorkspaceStyle">
      <AIWorkspace />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { agentBridge } from './agent/agentBridge'
import VisitorNameGate from './extensions/presence/VisitorNameGate.vue'
import { usePresenceStore } from './extensions/presence/store'
import { useUIStore } from './stores/uiStore'
import { useSceneStore } from './stores/sceneStore'
import EditorTopBar from './components/layout/EditorTopBar.vue'
import LeftPanel from './components/layout/LeftPanel.vue'
import RightPanel from './components/layout/RightPanel.vue'
import AIWorkspace from './components/layout/AIWorkspace.vue'
import CanvasViewport from './components/viewport/CanvasViewport.vue'

const uiStore = useUIStore()
const sceneStore = useSceneStore()
const presenceStore = usePresenceStore()
const editorReady = ref(false)

const aiLayoutClass = computed(() => uiStore.aiPanelVisible
  ? `ai-${uiStore.aiPanelMode}`
  : 'ai-hidden')

const aiWorkspaceStyle = computed(() => {
  if (uiStore.aiPanelMode === 'bottom') {
    return { height: `${uiStore.aiPanelBottomHeight}px` }
  }
  if (uiStore.aiPanelMode === 'side') {
    return { width: `${uiStore.aiPanelSideWidth}px` }
  }
  return undefined
})

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
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: 48px minmax(0, 1fr);
  background: #1e1e1e;
  color: #cccccc;
  overflow: hidden;
}

.wild-editor.ai-bottom {
  grid-template-rows: 48px minmax(0, 1fr) auto;
}

.wild-editor.ai-side {
  grid-template-columns: minmax(0, 1fr) auto;
}

.editor-topbar {
  grid-row: 1;
  grid-column: 1 / -1;
}

.editor-main {
  grid-row: 2;
  grid-column: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.viewport-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.ai-workspace-slot {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.ai-bottom .ai-workspace-slot {
  grid-row: 3;
  grid-column: 1;
}

.ai-side .ai-workspace-slot {
  grid-row: 2;
  grid-column: 2;
}

.ai-focus .editor-main {
  display: none;
}

.ai-focus .ai-workspace-slot {
  grid-row: 2;
  grid-column: 1;
}

/* 中等宽度屏幕优先保留三维视口；退出侧栏模式后辅助面板会自动恢复。 */
@media (max-width: 1500px) {
  .ai-side .right-panel-slot {
    display: none;
  }
}

@media (max-width: 1100px) {
  .ai-side .left-panel-slot {
    display: none;
  }
}
</style>
