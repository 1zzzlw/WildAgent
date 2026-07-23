<template>
  <div class="ai-chat-panel">
    <div class="messages-container" ref="messagesRef">

      <!-- 聊天消息 -->
      <div v-for="message in agentStore.session.messages" :key="message.id" :class="['message', message.role]">
        <div class="message-header">
          <span class="message-role">{{ getRoleLabel(message.role) }}</span>
          <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        </div>
        <div class="message-content">{{ message.content }}</div>
        <div v-if="message.patch" class="message-patch">
          <div class="patch-summary">{{ message.patch.summary }}</div>
          <el-button class="patch-btn" size="small" @click="handleApplyPatch(message.patch!)">
            应用修改
          </el-button>
        </div>
      </div>

      <!-- 处理中指示器 -->
      <div v-if="agentStore.isProcessing" class="processing">
        <el-icon class="processing-icon is-loading"><Loading /></el-icon>
        <span>{{ agentStore.currentStep || '处理中...' }}</span>
      </div>

      <!-- 校验流水线：逐条流式展示，直接内联在消息流里 -->
      <div v-if="agentStore.pipelineSteps.length > 0" class="pipeline-stream">
        <div class="pipeline-stream-title">校验流水线</div>
        <div
          v-for="(step, i) in agentStore.pipelineSteps"
          :key="i"
          :class="['pipeline-line', `status-${step.status}`]"
        >
          {{ step.label }}
        </div>
      </div>

      <!-- Blueprint 加载成功 -->
      <div v-if="agentStore.blueprintLoaded" class="success-indicator">
        <el-icon class="success-icon"><CircleCheckFilled /></el-icon>
        <span>Blueprint 已加载到场景</span>
      </div>

    </div>

    <!-- 连接状态栏 -->
    <div class="connection-bar" :class="connectionStatusClass">
      <el-icon v-if="connectionIcon" class="connection-icon">
        <component :is="connectionIcon" />
      </el-icon>
      <span class="connection-text">{{ connectionStatusText }}</span>
      <el-button v-if="agentStore.connectionStatus === 'disconnected'" text size="small"
        class="reconnect-btn" @click="handleReconnect">
        重新连接
      </el-button>
    </div>

    <!-- 输入框 -->
    <div class="input-container">
      <el-input v-model="inputText" type="textarea" placeholder="输入您的建筑需求..." :rows="3"
        resize="none" @keydown.enter.ctrl="handleSend" />
      <el-button class="send-btn" @click="handleSend" :disabled="!canSend" :title="sendButtonTitle">
        <el-icon v-if="agentStore.isProcessing" class="is-loading"><Loading /></el-icon>
        <el-icon v-else><Promotion /></el-icon>
        <span>发送</span>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { ElNotification } from 'element-plus'
import {
  Loading, Promotion, Connection, Link, WarningFilled, CircleCheckFilled,
} from '@element-plus/icons-vue'
import { useAgentStore } from '../../stores/agentStore'
import { useSceneStore } from '../../stores/sceneStore'
import { agentBridge } from '../../agent/agentBridge'
import type { ScenePatch } from '../../types/scenePatch'

const agentStore = useAgentStore()
const sceneStore = useSceneStore()
const inputText = ref('')
const messagesRef = ref<HTMLElement | null>(null)

// 自动滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// 消息或流水线步骤有变化时自动滚动
watch(() => agentStore.session.messages.length, scrollToBottom)
watch(() => agentStore.pipelineSteps.length, scrollToBottom)
watch(() => agentStore.isProcessing, scrollToBottom)
watch(() => agentStore.blueprintLoaded, scrollToBottom)

// ---------- 发送 ----------
const canSend = computed(() =>
  inputText.value.trim().length > 0
  && agentStore.connectionStatus === 'connected'
  && !agentStore.isProcessing
)

const sendButtonTitle = computed(() => {
  if (agentStore.connectionStatus !== 'connected') return '未连接到 Agent 服务'
  if (agentStore.isProcessing) return '处理中...'
  return '发送 (Ctrl+Enter)'
})

function handleSend() {
  if (!canSend.value) return
  const message = inputText.value.trim()
  agentStore.addUserMessage(message)
  agentBridge.sendUserMessage(message)
  inputText.value = ''
}

function handleReconnect() {
  agentBridge.connect()
}

// ---------- 连接状态 ----------
const connectionIcon = computed(() => {
  switch (agentStore.connectionStatus) {
    case 'connected':    return CircleCheckFilled
    case 'connecting':
    case 'reconnecting': return Connection
    case 'disconnected': return WarningFilled
    default:             return Link
  }
})

const connectionStatusClass = computed(() => `status-${agentStore.connectionStatus}`)

const connectionStatusText = computed(() => {
  switch (agentStore.connectionStatus) {
    case 'connecting':   return '正在连接 Agent 服务...'
    case 'connected':    return 'Agent 服务已连接'
    case 'reconnecting': return '连接断开，正在重新连接...'
    case 'disconnected': return agentStore.networkError || '未连接到 Agent 服务'
    default:             return '未知状态'
  }
})

// ---------- 通知 ----------
let previousStatus = agentStore.connectionStatus

watch(() => agentStore.connectionStatus, (newStatus) => {
  if (newStatus === previousStatus) return
  previousStatus = newStatus
  switch (newStatus) {
    case 'connected':
      ElNotification({ title: '已连接', message: 'Agent 服务连接成功', type: 'success', duration: 3000 })
      break
    case 'disconnected':
      if (agentStore.networkError)
        ElNotification({ title: '连接断开', message: agentStore.networkError, type: 'error', duration: 6000 })
      break
    case 'reconnecting':
      ElNotification({ title: '连接中断', message: '正在尝试重新连接...', type: 'warning', duration: 4000 })
      break
  }
})

watch(() => agentStore.networkError, (error) => {
  if (error)
    ElNotification({ title: '网络异常', message: error, type: 'error', duration: 8000 })
})

// ---------- 生命周期 ----------
onMounted(() => agentBridge.connect())
onUnmounted(() => agentBridge.disconnect())

watch(() => agentStore.blueprintLoaded, (loaded) => {
  if (loaded) setTimeout(() => agentStore.clearBlueprintLoaded(), 5000)
})

// ---------- 工具 ----------
function getRoleLabel(role: string) {
  return ({ user: '用户', agent: 'AI', system: '系统' } as Record<string, string>)[role] ?? role
}

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString('zh-CN')
}

function handleApplyPatch(patch: ScenePatch) {
  sceneStore.applyPatch(patch)
  agentStore.addSystemMessage('已应用修改')
}
</script>

<style scoped>
.ai-chat-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0; /* 关键：防止 flex 子项撑破父容器 */
}

/* 消息气泡 */
.message {
  padding: 8px 12px;
  border-radius: 4px;
  max-width: 80%;
}
.message.user   { align-self: flex-end;   background: #094771; }
.message.agent  { align-self: flex-start; background: #2d2d30; }
.message.system { align-self: center; background: #3e3e42; font-size: 12px; max-width: 60%; }

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 11px;
  color: #888;
}
.message-role   { font-weight: 500; }
.message-content { font-size: 13px; line-height: 1.5; }

.message-patch  { margin-top: 8px; padding-top: 8px; border-top: 1px solid #3e3e42; }
.patch-summary  { font-size: 12px; color: #4ec9b0; margin-bottom: 8px; }
.patch-btn {
  padding: 4px 12px;
  background: #0e639c;
  border: none;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
  border-radius: 3px;
}
.patch-btn:hover { background: #1177bb; }

/* 处理中转圈 */
.processing {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: #2d2d30;
  border-radius: 4px;
  font-size: 13px;
  color: #888;
  align-self: flex-start;
}
.processing-icon { font-size: 15px; }

/* 流水线流式展示 */
.pipeline-stream {
  align-self: stretch;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  font-family: 'Consolas', 'Menlo', monospace;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pipeline-stream-title {
  font-size: 11px;
  color: #666;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.pipeline-line {
  line-height: 1.6;
  animation: fadeIn 0.2s ease-out;
  word-break: break-all;
}

.pipeline-line.status-ok    { color: #4ec9b0; }
.pipeline-line.status-warn  { color: #dcdcaa; }
.pipeline-line.status-error { color: #f48771; }
.pipeline-line.status-skip  { color: #555; }

@keyframes fadeIn {
  from { opacity: 0; transform: translateX(-4px); }
  to   { opacity: 1; transform: translateX(0); }
}

/* Blueprint 成功 */
.success-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #1e3a2e;
  border: 1px solid #2d6b4f;
  border-radius: 4px;
  font-size: 13px;
  color: #4ec9b0;
  animation: fadeInUp 0.35s ease-out;
  align-self: stretch;
}
.success-icon { font-size: 18px; flex-shrink: 0; }

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* 连接状态栏 */
.connection-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  border-top: 1px solid #3e3e42;
  background: #252526;
  flex-shrink: 0;
}
.connection-icon { font-size: 14px; flex-shrink: 0; }
.connection-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reconnect-btn   { flex-shrink: 0; color: #4ec9b0; font-size: 12px; padding: 0 4px; height: auto; }

.connection-bar.status-connected                          { color: #4ec9b0; }
.connection-bar.status-connecting,
.connection-bar.status-reconnecting                       { color: #dcdcaa; }
.connection-bar.status-disconnected                       { color: #f48771; }

/* 输入区 */
.input-container {
  padding: 12px;
  background: #2d2d30;
  border-top: 1px solid #3e3e42;
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.input-container :deep(.el-textarea) { flex: 1; }
.input-container :deep(.el-textarea__inner) {
  min-height: 84px;
  padding: 8px;
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  color: #ccc;
  font-size: 13px;
  font-family: inherit;
  border-radius: 3px;
  resize: none;
}
.input-container :deep(.el-textarea__inner:focus) {
  outline: none;
  border-color: #007acc;
}

.send-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 20px;
  background: #0e639c;
  border: none;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  border-radius: 3px;
  transition: background 0.15s;
  flex-shrink: 0;
}
.send-btn:hover:not(:disabled) { background: #1177bb; }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
