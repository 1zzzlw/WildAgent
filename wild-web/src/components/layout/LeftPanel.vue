<template>
  <aside class="editor-dock" aria-label="编辑器功能">
    <nav class="icon-rail" aria-label="工作台导航">
      <div class="rail-panels">
        <button v-for="panel in visiblePanels" :key="panel.id" type="button"
          :class="['rail-button', { active: ui.activePanel === panel.id && ui.panelOpen }]"
          :aria-label="panel.label" :aria-pressed="ui.activePanel === panel.id && ui.panelOpen"
          :title="panel.label + ' · Alt+' + (panels.indexOf(panel)+1)" @click="ui.selectPanel(panel.id)">
          <el-icon><component :is="panel.icon" /></el-icon><span>{{ panel.short }}</span>
          <i v-if="panel.id === 'validation' && errorCount" class="rail-badge" :title="errorCount + ' 个错误'">{{ errorCount > 99 ? '99+' : errorCount }}</i>
        </button>
      </div>
      <div class="rail-footer">
        <button type="button" class="rail-button" aria-label="快捷键帮助" title="快捷键帮助 · ?" @click="ui.shortcutsVisible = true"><el-icon><QuestionFilled /></el-icon><span>帮助</span></button>
        <button type="button" class="rail-button rail-toggle" :aria-expanded="ui.panelOpen" :aria-label="ui.panelOpen ? '收起左侧面板' : '展开左侧面板'" title="收起 / 展开 · Ctrl+B" @click="ui.panelOpen = !ui.panelOpen"><el-icon><Fold v-if="ui.panelOpen" /><Expand v-else /></el-icon></button>
      </div>
    </nav>
    <section :class="['dock-panel', { closed: !ui.panelOpen }]" :style="{ '--dock-width': ui.panelWidth + 'px' }" :aria-hidden="!ui.panelOpen" :inert="!ui.panelOpen">
      <header class="dock-header">
        <h1><el-icon aria-hidden="true"><component :is="currentPanel.icon" /></el-icon>{{ currentPanel.label }}</h1>
        <button type="button" class="dock-close" aria-label="收起当前面板" @click="ui.panelOpen = false"><el-icon><Close /></el-icon></button>
      </header>
      <div class="dock-content">
        <SceneTree v-if="visitedPanels.has('sceneTree')" v-show="ui.activePanel === 'sceneTree'" />
        <LibraryPanel v-if="auth.canEdit && visitedPanels.has('library')" v-show="ui.activePanel === 'library'" :inert="!scene.canModifyManually" />
        <PropertyPanel v-if="auth.canEdit && visitedPanels.has('properties')" v-show="ui.activePanel === 'properties'" :inert="!scene.canModifyManually" />
        <ValidationPanel v-if="visitedPanels.has('validation')" v-show="ui.activePanel === 'validation'" />
        <MaterialPanel v-if="auth.canEdit && visitedPanels.has('assets')" v-show="ui.activePanel === 'assets'" :inert="!scene.canModifyManually" />
        <WorldLookPanel v-if="auth.canEdit && visitedPanels.has('look')" v-show="ui.activePanel === 'look'" :inert="!scene.canModifyManually" />
        <AIChatPanel v-show="auth.canEdit && ui.activePanel === 'aiChat'" />
      </div>
      <div class="dock-status">{{ selection.selectedIds.length ? '已选择 ' + selection.selectedIds.length + ' 项' : '未选择对象' }}</div>
      <button type="button" class="dock-resize" role="separator" aria-label="调整左侧面板宽度" aria-orientation="vertical"
        :aria-valuenow="ui.panelWidth" :aria-valuemin="300" :aria-valuemax="760" @pointerdown="startResize"
        @keydown.left.prevent="ui.setPanelWidth(ui.panelWidth-20)" @keydown.right.prevent="ui.setPanelWidth(ui.panelWidth+20)"></button>
    </section>
    <EditorTools />
  </aside>
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { Share, Box, Setting, CircleCheck, Brush, Sunny, ChatDotRound, Fold, Expand, QuestionFilled, Close } from '@element-plus/icons-vue'
import { useUIStore, type PanelType } from '../../stores/uiStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { useAuthStore } from '../../stores/authStore'
import EditorTools from './EditorTools.vue'
import SceneTree from '../panels/SceneTree.vue'
import ValidationPanel from '../panels/ValidationPanel.vue'
import AIChatPanel from '../panels/AIChatPanel.vue'
const LibraryPanel = defineAsyncComponent(() => import('../panels/LibraryPanel.vue'))
const PropertyPanel = defineAsyncComponent(() => import('../panels/PropertyPanel.vue'))
const MaterialPanel = defineAsyncComponent(() => import('../panels/MaterialPanel.vue'))
const WorldLookPanel = defineAsyncComponent(() => import('../panels/WorldLookPanel.vue'))
const ui = useUIStore()
const visitedPanels = ref(new Set<PanelType>())
watch([() => ui.activePanel, () => ui.panelOpen], ([panel, open]) => {
  if (open) visitedPanels.value.add(panel)
}, { immediate: true })
const scene = useSceneStore()
const selection = useSelectionStore()
const auth = useAuthStore()
const panels = [
  { id: 'sceneTree' as PanelType, label: '场景树', short: '场景', icon: Share },
  { id: 'library' as PanelType, label: '构件库', short: '构件', icon: Box },
  { id: 'properties' as PanelType, label: '属性', short: '属性', icon: Setting },
  { id: 'validation' as PanelType, label: '校验', short: '校验', icon: CircleCheck },
  { id: 'assets' as PanelType, label: '材质', short: '材质', icon: Brush },
  { id: 'look' as PanelType, label: '光影', short: '光影', icon: Sunny },
  { id: 'aiChat' as PanelType, label: 'AI 对话', short: 'AI', icon: ChatDotRound },
]
const currentPanel = computed(() => panels.find(p => p.id === ui.activePanel) || panels[0]!)
const visiblePanels = computed(() => auth.canEdit ? panels : panels.filter(p => ['sceneTree', 'validation'].includes(p.id)))
const errorCount = computed(() => scene.validationIssues.filter(issue => issue.level === 'error').length)
let startX = 0
let startWidth = 0
function startResize(event: PointerEvent) {
  event.preventDefault()
  startX = event.clientX
  startWidth = ui.panelWidth
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', resize)
  window.addEventListener('pointerup', stopResize)
  window.addEventListener('pointercancel', stopResize)
}
function resize(event: PointerEvent) { ui.setPanelWidth(Math.min(window.innerWidth-76, startWidth+event.clientX-startX)) }
function stopResize() {
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', resize)
  window.removeEventListener('pointerup', stopResize)
  window.removeEventListener('pointercancel', stopResize)
}
onBeforeUnmount(stopResize)
</script>
<style scoped>
.editor-dock { display: flex; flex-shrink: 0; min-height: 0; z-index: 50; }
.icon-rail {
  width: 68px;
  padding: 10px 7px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex-shrink: 0;
  gap: 10px;
  background: var(--studio-rail);
  border-right: 1px solid var(--studio-border);
}
.rail-panels, .rail-footer { display: flex; flex-direction: column; gap: 4px; }
.rail-panels { overflow-y: auto; scrollbar-width: none; }
.rail-footer { padding-top: 8px; border-top: 1px solid var(--studio-border); }
.rail-button {
  position: relative;
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 100%;
  min-height: 48px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: var(--studio-muted);
  cursor: pointer;
  transition: color .16s, background .16s;
}
.rail-button .el-icon { font-size: 19px; }
.rail-button > span { font-size: 11px; line-height: 13px; }
.rail-button:hover { background: var(--studio-hover); color: var(--studio-text); }
.rail-button:focus-visible { outline-offset: -3px; }
.rail-button.active { color: var(--studio-accent); background: var(--studio-hover); border-color: var(--studio-accent-border); font-weight: 650; }
.rail-toggle { min-height: 40px; }
.rail-badge {
  position: absolute;
  top: 3px;
  right: 3px;
  min-width: 15px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--studio-warm);
  color: var(--studio-danger);
  font: 600 10px/15px system-ui, sans-serif;
}
.dock-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(var(--dock-width), calc(100vw - 76px));
  min-height: 0;
  overflow: hidden;
  background: var(--studio-surface);
  border-right: 1px solid var(--studio-border);
  transition: width .2s ease, opacity .16s;
}
.dock-panel.closed { width: 0; opacity: 0; border: 0; pointer-events: none; }
.dock-header {
  min-height: 54px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px 0 16px;
  border-bottom: 1px solid var(--studio-border);
  white-space: nowrap;
}
.dock-header h1 { display: flex; align-items: center; gap: 9px; font-size: 15px; font-weight: 650; color: var(--studio-text); }
.dock-header h1 .el-icon { color: var(--studio-accent); }
.dock-close {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--studio-muted);
  font-size: 16px;
  cursor: pointer;
}
.dock-close:hover { background: var(--studio-hover); color: var(--studio-text); }
.dock-content { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
.dock-content > :deep(*) { min-height: 0; }
.dock-content > :deep(.ai-chat-panel) { height: 100%; }
.dock-status {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 28px;
  padding: 0 14px;
  border-top: 1px solid var(--studio-border);
  color: var(--studio-muted);
  font-size: 11px;
  white-space: nowrap;
}
.dock-resize { position: absolute; right: 0; top: 0; height: 100%; width: 5px; border: 0; background: transparent; cursor: col-resize; }
.dock-resize:hover, .dock-resize:focus-visible { background: var(--studio-accent-border); }
@media (max-width: 760px) {
  .editor-dock { position: absolute; inset: 0 auto 0 0; }
  .icon-rail { width: 62px; padding: 8px 5px; }
  .dock-panel { width: min(var(--dock-width), calc(100vw - 70px)); box-shadow: 12px 0 30px #0000001f; }
  .dock-close { width: 40px; height: 40px; }
}
</style>
