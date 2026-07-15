<template>
  <div class="top-bar">
    <div class="toolbar-section">
      <button @click="handleNew" class="toolbar-btn" title="新建场景">
        <span>新建</span>
      </button>
      <button @click="handleOpen" class="toolbar-btn" title="打开场景">
        <span>打开</span>
      </button>
      <button @click="handleSave" class="toolbar-btn" :disabled="!sceneStore.document?.dirty" title="保存场景">
        <span>保存</span>
      </button>
      <button @click="handleExport" class="toolbar-btn" title="导出 .wild 文件">
        <span>导出</span>
      </button>
    </div>

    <div class="toolbar-section">
      <button @click="handleUndo" class="toolbar-btn" :disabled="!historyStore.canUndo" title="撤销">
        <span>撤销</span>
      </button>
      <button @click="handleRedo" class="toolbar-btn" :disabled="!historyStore.canRedo" title="重做">
        <span>重做</span>
      </button>
    </div>

    <div class="toolbar-section">
      <button @click="handleValidate" class="toolbar-btn" title="运行校验">
        <span>校验</span>
      </button>
    </div>

    <div class="toolbar-section">
      <button @click="handleToggleAIPanel" class="toolbar-btn" title="切换 AI 对话面板">
        <span>{{ uiStore.bottomPanelVisible ? '隐藏 AI' : '显示 AI' }}</span>
      </button>
    </div>

    <div class="scene-info">
      <span v-if="sceneStore.document">
        {{ sceneStore.document.name }}
        <span v-if="sceneStore.document.dirty" class="dirty-indicator">*</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSceneStore } from '../../stores/sceneStore'
import { useHistoryStore } from '../../stores/historyStore'
import { useUIStore } from '../../stores/uiStore'

const sceneStore = useSceneStore()
const historyStore = useHistoryStore()
const uiStore = useUIStore()

function handleNew() {
  if (confirm('创建新场景将清空当前内容，是否继续？')) {
    const doc = sceneStore.createEmptyDocument()
    sceneStore.loadBlueprint(doc.blueprint, doc.name)
    historyStore.clear()
  }
}

function handleOpen() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.wild,.json'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) {
      const text = await file.text()
      try {
        const blueprint = JSON.parse(text)
        sceneStore.loadBlueprint(blueprint, file.name)
        historyStore.clear()
      } catch (error) {
        alert('文件格式错误')
      }
    }
  }
  input.click()
}

function handleSave() {
  const content = sceneStore.exportWild()
  const blob = new Blob([content], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${sceneStore.document?.name || 'scene'}.wild`
  a.click()
  URL.revokeObjectURL(url)
  sceneStore.markSaved()
}

function handleExport() {
  handleSave()
}

function handleUndo() {
  const entry = historyStore.undo()
  if (entry && sceneStore.document) {
    sceneStore.loadBlueprint(entry.before)
  }
}

function handleRedo() {
  const entry = historyStore.redo()
  if (entry && sceneStore.document) {
    sceneStore.loadBlueprint(entry.after)
  }
}

function handleValidate() {
  sceneStore.validate()
}

function handleToggleAIPanel() {
  uiStore.toggleBottomPanel()
}
</script>

<style scoped>
.top-bar {
  height: 48px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  display: flex;
  align-items: center;
  padding: 0 12px;
  gap: 16px;
}

.toolbar-section {
  display: flex;
  gap: 4px;
}

.toolbar-btn {
  height: 32px;
  padding: 0 12px;
  background: transparent;
  border: 1px solid #3e3e42;
  color: #cccccc;
  cursor: pointer;
  font-size: 13px;
  border-radius: 3px;
  transition: all 0.15s;
}

.toolbar-btn:hover:not(:disabled) {
  background: #3e3e42;
  border-color: #4e4e52;
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.scene-info {
  margin-left: auto;
  font-size: 13px;
  color: #cccccc;
}

.dirty-indicator {
  color: #f48771;
  margin-left: 4px;
}
</style>
