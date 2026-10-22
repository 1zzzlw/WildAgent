<template>
  <aside class="editor-dock" aria-label="编辑器功能">
    <nav class="icon-rail" aria-label="工作台导航">
      <div class="rail-panels">
        <button v-for="(panel,index) in panels" :key="panel.id" type="button"
          :class="['rail-button', { active: ui.activePanel === panel.id && ui.panelOpen }]"
          :aria-label="panel.label" :aria-pressed="ui.activePanel === panel.id && ui.panelOpen"
          :title="panel.label + ' · Alt+' + (index+1)" @click="ui.selectPanel(panel.id)">
          <el-icon><component :is="panel.icon" /></el-icon><span>{{ panel.short }}</span>
          <i v-if="panel.id === 'validation' && errorCount" class="rail-badge">{{ errorCount }}</i>
        </button>
      </div>
      <div class="rail-footer">
        <button type="button" class="rail-button" aria-label="快捷键帮助" title="快捷键帮助 · ?" @click="ui.shortcutsVisible = true"><el-icon><QuestionFilled /></el-icon><span>帮助</span></button>
        <button type="button" class="rail-button" :aria-label="ui.panelOpen ? '收起左侧面板' : '展开左侧面板'" title="收起 / 展开 · Ctrl+B" @click="ui.panelOpen = !ui.panelOpen"><el-icon><Fold v-if="ui.panelOpen" /><Expand v-else /></el-icon></button>
      </div>
    </nav>
    <section :class="['dock-panel', { closed: !ui.panelOpen }]" :style="{ '--dock-width': ui.panelWidth + 'px' }" :aria-hidden="!ui.panelOpen" :inert="!ui.panelOpen">
      <header class="dock-header"><div><small>WORKSPACE</small><h1>{{ currentPanel.label }}</h1></div>
        <button type="button" class="dock-close" aria-label="收起当前面板" @click="ui.panelOpen = false">×</button>
      </header>
      <div class="dock-content">
        <EditorTools v-show="ui.activePanel === 'tools'" />
        <SceneTree v-show="ui.activePanel === 'sceneTree'" />
        <BlockLibrary v-show="ui.activePanel === 'blockLibrary'" />
        <PropertyPanel v-show="ui.activePanel === 'properties'" />
        <ValidationPanel v-show="ui.activePanel === 'validation'" />
        <MaterialPanel v-show="ui.activePanel === 'assets'" />
        <WorldLookPanel v-show="ui.activePanel === 'look'" />
        <AIChatPanel v-show="ui.activePanel === 'aiChat'" />
      </div>
      <div class="dock-status"><span class="status-dot"></span><span>{{ scene.document?.dirty ? '修改尚未保存' : '准备就绪' }}</span><span>{{ selection.selectedIds.length ? selection.selectedIds.length + ' 项已选' : 'WILD 1.1' }}</span></div>
      <button type="button" class="dock-resize" role="separator" aria-label="调整左侧面板宽度" aria-orientation="vertical"
        :aria-valuenow="ui.panelWidth" :aria-valuemin="300" :aria-valuemax="760" @pointerdown="startResize"
        @keydown.left.prevent="ui.setPanelWidth(ui.panelWidth-20)" @keydown.right.prevent="ui.setPanelWidth(ui.panelWidth+20)"></button>
    </section>
  </aside>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import { Operation, Share, Box, Setting, CircleCheck, Brush, Sunny, ChatDotRound, Fold, Expand, QuestionFilled } from '@element-plus/icons-vue'
import { useUIStore, type PanelType } from '../../stores/uiStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import EditorTools from './EditorTools.vue'
import SceneTree from '../panels/SceneTree.vue'
import BlockLibrary from '../panels/BlockLibrary.vue'
import PropertyPanel from '../panels/PropertyPanel.vue'
import ValidationPanel from '../panels/ValidationPanel.vue'
import MaterialPanel from '../panels/MaterialPanel.vue'
import WorldLookPanel from '../panels/WorldLookPanel.vue'
import AIChatPanel from '../panels/AIChatPanel.vue'
const ui = useUIStore()
const scene = useSceneStore()
const selection = useSelectionStore()
const panels = [
  { id: 'tools' as PanelType, label: '工作台设置', short: '设置', icon: Operation },
  { id: 'sceneTree' as PanelType, label: '场景树', short: '场景', icon: Share },
  { id: 'blockLibrary' as PanelType, label: '构件库', short: '构件', icon: Box },
  { id: 'properties' as PanelType, label: '属性', short: '属性', icon: Setting },
  { id: 'validation' as PanelType, label: '校验', short: '校验', icon: CircleCheck },
  { id: 'assets' as PanelType, label: '材质', short: '材质', icon: Brush },
  { id: 'look' as PanelType, label: '光影', short: '光影', icon: Sunny },
  { id: 'aiChat' as PanelType, label: 'AI 对话', short: 'AI', icon: ChatDotRound },
]
const currentPanel = computed(() => panels.find(p => p.id === ui.activePanel) || panels[0]!)
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
.editor-dock{display:flex;flex-shrink:0;min-height:0;z-index:50;filter:drop-shadow(5px 0 12px #00000016)}.icon-rail{width:68px;flex-shrink:0;display:flex;flex-direction:column;justify-content:space-between;gap:12px;background:var(--studio-rail);border-right:1px solid var(--studio-border);padding:10px 7px}.rail-panels{display:flex;flex-direction:column;gap:5px;overflow-y:auto;scrollbar-width:none}.rail-button{position:relative;display:flex;width:52px;min-height:52px;flex-direction:column;align-items:center;justify-content:center;gap:5px;border:1px solid transparent;border-radius:10px;background:transparent;color:#8c9ba5;cursor:pointer;transition:color .16s,background .16s,transform .16s}.rail-button .el-icon{font-size:19px}.rail-button>span{font-size:10px;line-height:12px}.rail-button:hover{background:#ffffff08;color:#e0e8ed;transform:translateY(-1px)}.rail-button.active{color:var(--studio-accent);background:#a6c3b511;border-color:#a6c3b529}.rail-button.active:before{content:'';position:absolute;left:-8px;height:22px;width:2px;border-radius:3px;background:var(--studio-accent)}.rail-footer{display:flex;flex-direction:column;gap:4px}.rail-footer .rail-button:last-child{min-height:34px}.rail-badge{position:absolute;top:3px;right:3px;min-width:15px;background:#a7544f;border-radius:6px;color:white;font-size:9px;font-style:normal;padding:2px}
.dock-panel{position:relative;width:min(var(--dock-width),calc(100vw - 76px));display:flex;flex-direction:column;min-height:0;overflow:hidden;background:var(--studio-surface);border-right:1px solid var(--studio-border);transition:width .22s cubic-bezier(.2,.7,.2,1),opacity .16s}.dock-panel.closed{width:0;opacity:0;border:0;pointer-events:none}.dock-header{height:72px;min-height:72px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid var(--studio-border);white-space:nowrap}.dock-header small{font-size:9px;letter-spacing:2px;color:#73848e}.dock-header h1{margin-top:6px;font-size:17px;font-weight:550;color:#e4eaf0}.dock-close{background:transparent;border:0;color:#8d9aa3;font-size:23px;cursor:pointer;padding:8px}.dock-content{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain}.dock-content>:deep(*){min-height:0}.dock-content>:deep(.ai-chat-panel){height:100%}.dock-status{min-height:30px;display:flex;align-items:center;gap:7px;border-top:1px solid var(--studio-border);padding:0 13px;color:#82929d;font-size:10px;white-space:nowrap}.dock-status>span:last-child{margin-left:auto}.status-dot{width:5px;height:5px;border-radius:50%;background:#87b79c}.dock-resize{position:absolute;right:0;top:0;height:100%;width:5px;border:0;background:transparent;cursor:col-resize}.dock-resize:hover,.dock-resize:focus-visible{background:#a6c3b566}
@media(max-width:760px){.editor-dock{position:absolute;left:0;top:0;bottom:0}.dock-panel{box-shadow:12px 0 30px #0005}.rail-button{min-height:46px}.icon-rail{width:62px;padding:7px 5px}.dock-panel{width:min(var(--dock-width),calc(100vw - 70px))}.dock-panel.closed{width:0}}
</style>
