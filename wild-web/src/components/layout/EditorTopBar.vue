<template>
  <header class="editor-header">
    <div class="workspace-heading">
      <button class="brand" type="button" aria-label="打开场景树" title="打开场景树" @click="ui.openPanel('sceneTree')">
        <span class="brand-mark">W</span><span class="brand-name">WildAgent</span>
      </button>
      <div class="document-title" :title="scene.document?.name">
        <span class="document-name">{{ scene.document?.name || '建筑工作台' }}</span>
        <span :class="['save-state', { dirty: scene.document?.dirty }]" role="status">
          {{ workspace.isSaving ? '保存中…' : scene.document?.dirty ? '未保存' : scene.document?.savedAt ? '已保存' : '本地预览' }}
        </span>
      </div>
    </div>
    <nav class="file-toolbar" aria-label="文件操作">
      <button v-if="auth.canEdit" aria-label="新建场景" title="新建场景" :disabled="busy" @click="workspace.newScene()"><el-icon>
          <DocumentAdd />
        </el-icon><span>新建</span></button>
      <button v-if="auth.canEdit" aria-label="打开 WILD" title="打开 WILD，导入后自动保存到服务器" :disabled="busy" @click="fileInput?.click()"><el-icon>
          <FolderOpened />
        </el-icon><span>打开</span></button>
      <button v-if="auth.canEdit" class="save-button" aria-label="保存到服务器" title="保存到服务器 · Ctrl+S" :disabled="!scene.document || busy || scene.isLocked"
        @click="workspace.saveScene()"><el-icon>
          <Upload />
        </el-icon><span>{{ workspace.isSaving ? '保存中' : '保存' }}</span></button>
      <button v-if="auth.canEdit" aria-label="导出 WILD" title="导出 WILD" :disabled="!scene.document" @click="exportFile"><el-icon>
          <Download />
        </el-icon><span>导出</span></button>
      <button aria-label="导出 GLB" title="导出建筑与材质贴图；程序化表面按当前状态烘焙，光照与动态效果由查看器呈现"
        :disabled="!scene.reconstructed?.meshes.length || scene.isReconstructing || busy || render.exportingGlb"
        @click="render.requestGlbExport()"><el-icon>
          <Box />
        </el-icon><span>{{ render.exportingGlb ? '导出中…' : '导出 GLB' }}</span></button>
      <i v-if="auth.canEdit" class="toolbar-divider"></i>
      <button v-if="auth.canEdit" aria-label="撤销" title="撤销 · Ctrl+Z" :disabled="!history.canUndo || busy || !scene.canModifyManually" @click="restore(false)"><el-icon>
          <RefreshLeft />
        </el-icon></button>
      <button v-if="auth.canEdit" aria-label="重做" title="重做 · Ctrl+Shift+Z" :disabled="!history.canRedo || busy || !scene.canModifyManually"
        @click="restore(true)"><el-icon>
          <RefreshRight />
        </el-icon></button>
      <i class="toolbar-divider"></i>
      <button aria-label="切换会话" title="搜索、切换和管理会话" :disabled="busy" @click="ui.sessionPickerVisible = true">
        <el-icon><Switch /></el-icon><span>切换会话</span>
      </button>
    </nav>
    <input ref="fileInput" class="file-input" type="file" accept=".wild,.json" aria-label="导入 WILD 文件"
      @change="importFile" />
    <div class="header-actions">
      <UsageStatus />
      <OnlinePresence />
      <RouterLink v-if="auth.isAdmin" class="header-action" to="/admin" aria-label="管理后台" title="管理后台">
        <el-icon><Setting /></el-icon><span>管理后台</span>
      </RouterLink>
      <RouterLink class="header-action" to="/business-plan" aria-label="商业计划书" title="商业计划书">
        <el-icon><Tickets /></el-icon><span>商业计划书</span>
      </RouterLink>
      <button class="header-action" type="button" :aria-label="theme.isDark ? '切换为亮色主题' : '切换为暗色主题'" :title="theme.isDark ? '亮色主题' : '暗色主题'" @click="theme.toggle()">
        <el-icon><Sunny v-if="theme.isDark" /><Moon v-else /></el-icon>
      </button>
      <button class="header-action account-button" type="button" aria-label="退出登录" :title="accountName + ' · 退出登录'" @click="logout">
        <span>{{ accountName }}</span><el-icon><SwitchButton /></el-icon>
      </button>
    </div>
  </header>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RouterLink } from 'vue-router'
import { DocumentAdd, FolderOpened, Upload, Download, Box, RefreshLeft, RefreshRight, Switch, Sunny, Moon, Setting, Tickets, SwitchButton } from '@element-plus/icons-vue'
import { useHistoryStore } from '../../stores/historyStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useUIStore } from '../../stores/uiStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import { useRenderPanelStore } from '../../stores/renderPanelStore'
import OnlinePresence from '../../extensions/presence/OnlinePresence.vue'
import UsageStatus from './UsageStatus.vue'
import { useThemeStore } from '../../stores/themeStore'
import { useAuthStore } from '../../stores/authStore'
import { useAgentStore } from '../../stores/agentStore'
const auth = useAuthStore()
const theme = useThemeStore()
const scene = useSceneStore()
const ui = useUIStore()
const workspace = useWorkspaceStore()
const history = useHistoryStore()
const render = useRenderPanelStore()
const fileInput = ref<HTMLInputElement>()
const busy = computed(() => workspace.isSaving || workspace.isImporting || scene.isCommitting)
const accountName = computed(() => auth.isGuest ? '游客 · 只读' : auth.user?.username || '账号')
async function importFile(event: Event) {
  // 获取 wild 文件内容
  const input = event.target as HTMLInputElement
  if (input.files?.[0]) await workspace.importFile(input.files[0])
  input.value = ''
}
function exportFile() {
  if (!auth.canEdit) return
  const url = URL.createObjectURL(new Blob([scene.exportWild()], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  const agent = useAgentStore()
  const savedFilename = agent.sessions.find(item => item.session_id === agent.currentSessionId)?.filename
  link.download = savedFilename?.split('/').pop() || (scene.document?.name || 'scene') + '.wild'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function restore(redo: boolean) {
  if (!scene.canModifyManually) return
  const previousIndex = history.currentIndex
  const entry = redo ? history.redo() : history.undo()
  if (entry && !await scene.restoreBlueprint(redo ? entry.after : entry.before)) history.currentIndex = previousIndex
}
async function logout() {
  if (scene.document?.dirty) {
    try { await ElMessageBox.confirm('当前修改尚未保存，退出后将丢失。确认退出？', '退出登录', { type: 'warning' }) }
    catch { return }
  }
  try {
    await auth.logout()
    window.location.reload()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '退出失败') }
}
</script>
<style scoped>
.editor-header {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: minmax(175px, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  min-height: 54px;
  padding: 0 12px;
  border-bottom: 1px solid var(--studio-border);
  background: var(--studio-surface);
}
.workspace-heading, .brand, .header-actions {
  display: flex;
  align-items: center;
}
.workspace-heading { gap: 12px; min-width: 0; }
.brand {
  flex-shrink: 0;
  gap: 8px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--studio-text);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 31px;
  height: 31px;
  border-radius: 8px;
  background: var(--studio-accent);
  color: var(--studio-bg);
  font: 600 20px Georgia, serif;
}
.document-title {
  display: grid;
  gap: 2px;
  min-width: 0;
  padding-left: 12px;
  border-left: 1px solid var(--studio-border);
  color: var(--studio-text);
}
.document-name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13px;
  font-weight: 600;
}
.save-state {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--studio-muted);
  font-size: 11px;
  white-space: nowrap;
}
.save-state::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}
.save-state.dirty { color: var(--studio-orange); }
.file-toolbar {
  display: flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
  padding: 3px;
  border: 1px solid var(--studio-border);
  border-radius: 9px;
  background: var(--studio-bg);
  overflow-x: auto;
  scrollbar-width: none;
}
.file-toolbar button, .header-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  gap: 6px;
  min-width: 32px;
  min-height: 32px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--studio-muted);
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
}
.file-toolbar button .el-icon, .header-action .el-icon { font-size: 15px; }
.file-toolbar button:hover:not(:disabled), .header-action:hover {
  background: var(--studio-hover);
  color: var(--studio-text);
}
.file-toolbar button:focus-visible { outline-offset: -2px; }
.file-toolbar button:disabled { opacity: .45; cursor: not-allowed; }
.file-toolbar .save-button {
  background: var(--studio-hover);
  border-color: var(--studio-accent-border);
  color: var(--studio-accent);
  font-weight: 650;
}
.toolbar-divider { flex: none; width: 1px; height: 16px; margin: 0 2px; background: var(--studio-border); }
.file-input { display: none; }
.header-actions { gap: 5px; }
.header-action { text-decoration: none; }
.header-action:focus-visible { outline: 2px solid var(--studio-accent); outline-offset: 1px; }
.account-button {
  gap: 7px;
  border-color: var(--studio-border);
  color: var(--studio-text);
}
.account-button span { max-width: 86px; overflow: hidden; text-overflow: ellipsis; }

@media (max-width: 1320px) {
  .header-actions a > span, .file-toolbar button:not(.save-button) > span { display: none; }
}
@media (max-width: 980px) {
  .editor-header {
    grid-template-columns: minmax(0, 1fr) auto;
    row-gap: 6px;
    padding: 7px 10px;
  }
  .file-toolbar { grid-row: 2; grid-column: 1 / -1; }
  .file-toolbar button:not(.save-button) > span { display: inline; }
  .header-actions { grid-column: 2; grid-row: 1; }
}
@media (max-width: 600px) {
  .editor-header { column-gap: 6px; padding-inline: 8px; }
  .workspace-heading { gap: 6px; }
  .document-title { padding-left: 0; border: 0; }
  .document-name { font-size: 12px; }
  .save-state { display: block; overflow: hidden; text-overflow: ellipsis; }
  .save-state::before { display: none; }
  .header-actions { gap: 3px; }
  .header-action { padding-inline: 6px; }
  .file-toolbar { gap: 2px; padding: 2px; }
  .toolbar-divider { margin-inline: 1px; }
  .file-toolbar button { min-width: 34px; min-height: 38px; padding-inline: 6px; }
  .file-toolbar button > span, .file-toolbar button:not(.save-button) > span,
  .brand-name, .account-button span { display: none; }
}
</style>
