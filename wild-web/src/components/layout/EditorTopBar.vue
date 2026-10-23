<template>
  <header class="editor-header">
    <button class="brand" type="button" aria-label="打开工作台工具" @click="ui.openPanel('tools')"><span>W</span> WildAgent
      <small>STUDIO</small></button>
    <nav class="file-toolbar" aria-label="文件操作">
      <button aria-label="新建场景" title="新建场景" :disabled="busy" @click="workspace.newScene()"><el-icon>
          <DocumentAdd />
        </el-icon><span>新建</span></button>
      <button aria-label="打开 WILD" title="打开 WILD，导入后自动保存到服务器" :disabled="busy" @click="fileInput?.click()"><el-icon>
          <FolderOpened />
        </el-icon><span>打开</span></button>
      <button class="save-button" aria-label="保存到服务器" title="保存到服务器 · Ctrl+S" :disabled="!scene.document || busy"
        @click="workspace.saveScene()"><el-icon>
          <Upload />
        </el-icon><span>{{ workspace.isSaving ? '保存中' : '保存' }}</span></button>
      <button aria-label="导出 WILD" title="导出 WILD" :disabled="!scene.document" @click="exportFile"><el-icon>
          <Download />
        </el-icon><span>导出</span></button>
      <i class="toolbar-divider"></i>
      <button aria-label="撤销" title="撤销 · Ctrl+Z" :disabled="!history.canUndo || busy" @click="restore(false)"><el-icon>
          <RefreshLeft />
        </el-icon></button>
      <button aria-label="重做" title="重做 · Ctrl+Shift+Z" :disabled="!history.canRedo || busy"
        @click="restore(true)"><el-icon>
          <RefreshRight />
        </el-icon></button>
    </nav>
    <input ref="fileInput" class="file-input" type="file" accept=".wild,.json" aria-label="导入 WILD 文件"
      @change="importFile" />
    <div class="document-title" :title="scene.document?.name">
      <span>{{ scene.document?.name || '建筑工作台' }}</span>
      <span :class="['save-state', { dirty: scene.document?.dirty }]" role="status">
        {{ workspace.isSaving ? '正在保存…' : scene.document?.dirty ? '未保存' : scene.document?.savedAt ? '已保存到服务器' : '本地预览'
        }}
      </span>
    </div>
    <OnlinePresence />
  </header>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { DocumentAdd, FolderOpened, Upload, Download, RefreshLeft, RefreshRight } from '@element-plus/icons-vue'
import { useHistoryStore } from '../../stores/historyStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useUIStore } from '../../stores/uiStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import OnlinePresence from '../../extensions/presence/OnlinePresence.vue'
const scene = useSceneStore()
const ui = useUIStore()
const workspace = useWorkspaceStore()
const history = useHistoryStore()
const fileInput = ref<HTMLInputElement>()
const busy = computed(() => workspace.isSaving || workspace.isImporting)
async function importFile(event: Event) {
  // 获取 wild 文件内容
  const input = event.target as HTMLInputElement
  if (input.files?.[0]) await workspace.importFile(input.files[0])
  input.value = ''
}
function exportFile() {
  const url = URL.createObjectURL(new Blob([scene.exportWild()], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = (scene.document?.name || 'scene') + '.wild'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function restore(redo: boolean) {
  const entry = redo ? history.redo() : history.undo()
  if (entry) await scene.restoreBlueprint(redo ? entry.after : entry.before)
}
</script>
<style scoped>
.editor-header {
  height: 50px;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 18px 0 12px;
  border-bottom: 1px solid var(--studio-border);
  background: var(--studio-surface);
  flex-shrink: 0;
  min-width: 0
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  background: none;
  border: 0;
  color: #f1f4f7;
  font-size: 15px;
  font-weight: 650;
  cursor: pointer;
  white-space: nowrap
}

.brand>span {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid #a6c3b54a;
  border-radius: 8px;
  background: #a6c3b518;
  color: var(--studio-accent);
  font-family: Georgia, serif;
  font-size: 21px
}

.brand small {
  font-size: 9px;
  letter-spacing: 2px;
  color: #77858e;
  font-weight: 500
}

.document-title {
  display: flex;
  gap: 12px;
  align-items: center;
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: #d5dde1
}

.document-title>span:first-child {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis
}

.save-state {
  font-size: 10px;
  white-space: nowrap;
  color: #8fb7a1
}

.save-state.dirty {
  color: #dbb57c
}

.file-toolbar {
  display: flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0
}

.file-toolbar button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #b7c6ce;
  cursor: pointer;
  font-size: 11px;
  white-space: nowrap
}

.file-toolbar button:hover:not(:disabled) {
  background: #ffffff0c;
  color: #edf5f0
}

.file-toolbar button:disabled {
  opacity: .3;
  cursor: not-allowed
}

.file-toolbar .save-button {
  color: #b6d7c3;
  background: #a6c3b513;
  border-color: #a6c3b527
}

.toolbar-divider {
  height: 18px;
  width: 1px;
  background: var(--studio-border);
  margin: 0 5px
}

.file-input {
  display: none
}

@media(max-width:1000px) {
  .brand small {
    display: none
  }

  .editor-header {
    gap: 12px
  }

  .save-state {
    display: none
  }
}

@media(max-width:620px) {
  .brand {
    font-size: 0 !important;
    gap: 0
  }

  .file-toolbar button>span {
    display: none
  }

  .file-toolbar button {
    padding: 8px
  }

  .document-title {
    font-size: 11px
  }

  .editor-header {
    padding: 0 8px;
    gap: 8px
  }
}

@media(max-width:700px) {
  .editor-header {
    gap: 10px;
    padding: 0 10px
  }

  .brand small,
  .save-state {
    display: none
  }

  .brand {
    font-size: 12px
  }
}
</style>
