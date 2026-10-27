<template>
  <VisitorNameGate v-if="!editorReady" @confirmed="enterEditor" />
  <div v-else :class="['wild-editor', { 'viewport-focused': ui.viewportFocused, 'reduce-motion': !ui.animationsEnabled }]" @click.capture="handleClickSound">
    <EditorTopBar v-show="!ui.viewportFocused" />
    <div class="editor-main">
      <LeftPanel v-show="!ui.viewportFocused" />
      <main ref="viewportRef" class="viewport-container" aria-label="建筑渲染视口">
        <CanvasViewport />
        <ViewportToolDock v-show="!roaming.active" />
        <CharacterRoamingPanel />
        <button class="viewport-expand" type="button" :aria-label="ui.viewportFocused ? '退出渲染全屏' : '渲染界面全屏'"
          :title="ui.viewportFocused ? '退出全屏 · Esc' : '渲染界面全屏 · Shift+F'" @click="ui.viewportFocused = !ui.viewportFocused">
          <el-icon><FullScreen /></el-icon><span>{{ ui.viewportFocused ? '退出全屏' : '全屏' }}</span>
        </button>
      </main>
    </div>
  </div>
</template>
<script setup lang="ts">
import { nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { FullScreen } from '@element-plus/icons-vue'
import { agentBridge } from '../agent/agentBridge'
import VisitorNameGate from '../extensions/presence/VisitorNameGate.vue'
import { usePresenceStore } from '../extensions/presence/store'
import { useUIStore, PANEL_IDS } from '../stores/uiStore'
import { useSceneStore } from '../stores/sceneStore'
import { useHistoryStore } from '../stores/historyStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useRenderPanelStore } from '../stores/renderPanelStore'
import { playUISound } from '../utils/uiSound'
import EditorTopBar from '../components/layout/EditorTopBar.vue'
import LeftPanel from '../components/layout/LeftPanel.vue'
import CanvasViewport from '../components/viewport/CanvasViewport.vue'
import ViewportToolDock from '../components/viewport/ViewportToolDock.vue'
import CharacterRoamingPanel from '../extensions/characterRoaming/CharacterRoamingPanel.vue'
import { useCharacterRoamingStore } from '../extensions/characterRoaming/store'
const ui = useUIStore()
defineOptions({ name: 'WorkbenchView' })
let workbenchActive = true
const scene = useSceneStore()
const history = useHistoryStore()
const workspace = useWorkspaceStore()
const render = useRenderPanelStore()
const presence = usePresenceStore()
const roaming = useCharacterRoamingStore()
const editorReady = ref(false)
const viewportRef = ref<HTMLElement>()
let nativeFullscreen = false
function enterEditor() {
  if (editorReady.value) return
  editorReady.value = true
  scene.document = scene.createEmptyDocument()
  agentBridge.connect()
}
watch(() => ui.viewportFocused, async focused => {
  await nextTick()
  if (focused && viewportRef.value?.requestFullscreen) {
    try { await viewportRef.value.requestFullscreen(); nativeFullscreen = true } catch { /* 保持页面内全屏。 */ }
  } else if (!focused && document.fullscreenElement === viewportRef.value) await document.exitFullscreen()
})
function syncFullscreen() {
  if (nativeFullscreen && !document.fullscreenElement) { nativeFullscreen = false; ui.viewportFocused = false }
}
function handleClickSound(event: MouseEvent) {
  if (ui.soundsEnabled && (event.target as HTMLElement).closest('button')) playUISound()
}
async function handleKeydown(event: KeyboardEvent) {
  if (!editorReady.value || !workbenchActive) return
  const target = event.target as HTMLElement
  const typing = target.matches('input,textarea,select') || target.isContentEditable
  const modifier = event.ctrlKey || event.metaKey
  if (modifier && event.key.toLowerCase() === 's') { event.preventDefault(); if (!workspace.isImporting) await workspace.saveScene(); return }
  if (roaming.active && roaming.locked) return
  if (event.key === 'Escape') { ui.viewportFocused = false; return }
  if (typing) return
  if (modifier && event.key.toLowerCase() === 'b') { event.preventDefault(); ui.panelOpen = !ui.panelOpen; return }
  if (modifier && ['z', 'y'].includes(event.key.toLowerCase())) {
    event.preventDefault()
    const redo = event.key.toLowerCase() === 'y' || event.shiftKey
    const entry = redo ? history.redo() : history.undo()
    if (entry) await scene.restoreBlueprint(redo ? entry.after : entry.before)
    return
  }
  if (event.altKey && /^[1-7]$/.test(event.key)) { event.preventDefault(); ui.openPanel(PANEL_IDS[Number(event.key)-1]!); return }
  if (!modifier && event.key.toLowerCase() === 'f') {
    event.preventDefault()
    if (event.shiftKey) ui.viewportFocused = !ui.viewportFocused
    else render.requestFrameSelection()
  }
  if (event.key === '?') ui.shortcutsVisible = true
}
onMounted(() => {
  if (presence.hasVisitorName) enterEditor()
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('fullscreenchange', syncFullscreen)
})
onActivated(() => { workbenchActive = true })
onDeactivated(() => {
  workbenchActive = false
  roaming.stop()
  ui.viewportFocused = false
  if (document.pointerLockElement) document.exitPointerLock()
})
onUnmounted(() => {
  agentBridge.disconnect()
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('fullscreenchange', syncFullscreen)
})
</script>
<style scoped>
.wild-editor{width:100vw;height:100dvh;display:flex;flex-direction:column;background:var(--studio-bg);color:var(--studio-text);overflow:hidden}.editor-main{flex:1;display:flex;min-height:0;min-width:0;position:relative;overflow:hidden}.viewport-container{flex:1;min-width:0;min-height:0;position:relative;overflow:hidden;background:var(--studio-surface)}.viewport-container:fullscreen{width:100vw;height:100dvh}.viewport-expand{position:absolute;right:16px;top:16px;z-index:40;display:flex;align-items:center;gap:7px;background:var(--studio-surface);backdrop-filter:blur(12px);color:var(--studio-text);border:1px solid var(--studio-border);border-radius:9px;padding:9px 12px;font-size:11px;cursor:pointer;transition:background .16s,transform .16s}.viewport-expand:hover{background:var(--studio-hover);transform:translateY(-1px)}
@media(max-width:760px){.editor-main{padding-left:62px}.viewport-focused .editor-main{padding-left:0}}
</style>
