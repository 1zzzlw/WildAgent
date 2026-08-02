<template>
  <div class="top-bar">
    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleNew" title="新建场景">
        <span>新建</span>
      </el-button>
      <el-button class="toolbar-btn" size="small" @click="handleOpen" title="打开场景">
        <span>打开</span>
      </el-button>
      <el-button class="toolbar-btn save-btn" type="primary" size="small" @click="handleSave"
        :loading="isSaving" :disabled="!sceneStore.document?.dirty || isSaving" title="保存到服务器">
        <span>{{ isSaving ? '保存中' : '保存' }}</span>
      </el-button>
      <el-button class="toolbar-btn" size="small" @click="handleExport" title="导出 .wild 文件">
        <span>导出</span>
      </el-button>
    </div>

    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleUndo" :disabled="!historyStore.canUndo" title="撤销">
        <span>撤销</span>
      </el-button>
      <el-button class="toolbar-btn" size="small" @click="handleRedo" :disabled="!historyStore.canRedo" title="重做">
        <span>重做</span>
      </el-button>
    </div>

    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleValidate" title="运行校验">
        <span>校验</span>
      </el-button>
    </div>

    <div class="toolbar-section">
      <el-button class="toolbar-btn" size="small" @click="handleToggleAIPanel" title="切换 AI 对话面板">
        <span>{{ uiStore.bottomPanelVisible ? '隐藏 AI' : '显示 AI' }}</span>
      </el-button>
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
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentBridge } from '../../agent/agentBridge'
import { useAgentStore } from '../../stores/agentStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useHistoryStore } from '../../stores/historyStore'
import { useUIStore } from '../../stores/uiStore'

const sceneStore = useSceneStore()
const historyStore = useHistoryStore()
const uiStore = useUIStore()
const agentStore = useAgentStore()
const isSaving = ref(false)

async function handleNew() {
  try {
    await ElMessageBox.confirm('创建新场景将清空当前内容，是否继续？', '确认操作', {
      confirmButtonText: '继续',
      cancelButtonText: '取消',
      type: 'warning'
    })

    const doc = sceneStore.createEmptyDocument()
    sceneStore.loadBlueprint(doc.blueprint, doc.name)
    historyStore.clear()
  } catch {
    // 用户取消
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
      } catch {
        ElMessage.error('文件格式错误')
      }
    }
  }
  input.click()
}

async function handleSave() {
  if (!sceneStore.document || !agentStore.currentSessionId) {
    ElMessage.error('当前场景没有对应的服务器会话，无法保存')
    return
  }
  const issues = sceneStore.validate()
  if (issues.some(issue => issue.level === 'error')) {
    ElMessage.error('场景校验存在错误，请修复后再保存')
    return
  }

  isSaving.value = true
  const saved = await agentBridge.syncBlueprintToBackend(
    sceneStore.document.blueprint as unknown as Record<string, unknown>,
  )
  isSaving.value = false
  if (!saved) {
    ElMessage.error('保存到服务器失败，本地草稿仍然保留')
    return
  }

  const blueprint = sceneStore.document.blueprint
  const elementsCount = (blueprint.geometry.elements?.length || 0)
    + (blueprint.geometry.components?.length || 0)
  agentStore.updateSessionInfo(
    agentStore.currentSessionId,
    blueprint.meta.name || sceneStore.document.name,
    elementsCount,
  )
  sceneStore.markSaved()
  ElMessage.success('场景已保存到服务器')
}

function handleExport() {
  const content = sceneStore.exportWild()
  const blob = new Blob([content], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${sceneStore.document?.name || 'scene'}.wild`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出当前草稿，服务端文件未修改')
}

async function handleUndo() {
  const entry = historyStore.undo()
  if (entry) {
    await sceneStore.restoreBlueprint(entry.before)
  }
}

async function handleRedo() {
  const entry = historyStore.redo()
  if (entry) {
    await sceneStore.restoreBlueprint(entry.after)
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

.save-btn:not(:disabled) {
  border-color: #168bc2;
  background: #137fac;
  color: #ffffff;
}

.save-btn:hover:not(:disabled) {
  border-color: #35bfe8;
  background: #1593c7;
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
