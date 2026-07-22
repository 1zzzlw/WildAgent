<template>
  <div class="ai-chat-panel">
    <div class="messages-container" ref="messagesRef">
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

      <div v-if="agentStore.isProcessing" class="processing">
        <el-icon class="processing-icon is-loading">
          <Loading />
        </el-icon>
        <span>{{ agentStore.currentStep || '处理中...' }}</span>
      </div>

      <!-- Blueprint 加载成功动画 -->
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
      <el-button v-if="agentStore.connectionStatus === 'disconnected'" text size="small" class="reconnect-btn"
        @click="handleReconnect">
        重新连接
      </el-button>
    </div>

    <div class="input-container">
      <el-input v-model="inputText" type="textarea" placeholder="输入您的建筑需求..." :rows="3" resize="none"
        @keydown.enter.ctrl="handleSend" />
      <el-button class="send-btn" @click="handleSend" :disabled="!canSend" :title="sendButtonTitle">
        <el-icon v-if="agentStore.isProcessing" class="is-loading">
          <Loading />
        </el-icon>
        <el-icon v-else>
          <Promotion />
        </el-icon>
        <span>发送</span>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElNotification } from 'element-plus'
import {
  Loading,
  Promotion,
  Connection,
  Link,
  WarningFilled,
  CircleCheckFilled
} from '@element-plus/icons-vue'
import { useAgentStore } from '../../stores/agentStore'
import { useSceneStore } from '../../stores/sceneStore'
import { agentBridge } from '../../agent/agentBridge'
import type { ScenePatch } from '../../types/scenePatch'

const agentStore = useAgentStore()
const sceneStore = useSceneStore()
const inputText = ref('')

// ---------- 发送逻辑 ----------

const canSend = computed(() => {
  return inputText.value.trim().length > 0
    && agentStore.connectionStatus === 'connected'
    && !agentStore.isProcessing
})

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

// ---------- 连接状态显示 ----------
const connectionIcon = computed(() => {
  switch (agentStore.connectionStatus) {
    case 'connected': return CircleCheckFilled
    case 'connecting':
    case 'reconnecting': return Connection
    case 'disconnected': return WarningFilled
    default: return Link
  }
})

const connectionStatusClass = computed(() => {
  return `status-${agentStore.connectionStatus}`
})

const connectionStatusText = computed(() => {
  const attempt = agentStore.connectionStatus === 'reconnecting'
    ? ` (重试中...)`
    : ''
  switch (agentStore.connectionStatus) {
    case 'connecting': return '正在连接 Agent 服务...'
    case 'connected': return 'Agent 服务已连接'
    case 'reconnecting': return '连接断开，正在重新连接...'
    case 'disconnected': return agentStore.networkError || '未连接到 Agent 服务'
    default: return '未知状态'
  }
})

// ---------- 通知 ----------
/** 上次的连接状态，用于检测变化 */
let previousStatus = agentStore.connectionStatus

watch(() => agentStore.connectionStatus, (newStatus) => {
  if (newStatus === previousStatus) return
  previousStatus = newStatus

  switch (newStatus) {
    case 'connected':
      ElNotification({
        title: '已连接',
        message: 'Agent 服务连接成功',
        type: 'success',
        duration: 3000,
        icon: CircleCheckFilled
      })
      break

    case 'disconnected':
      if (agentStore.networkError) {
        ElNotification({
          title: '连接断开',
          message: agentStore.networkError,
          type: 'error',
          duration: 6000,
          icon: WarningFilled
        })
      }
      break

    case 'reconnecting':
      ElNotification({
        title: '连接中断',
        message: '正在尝试重新连接...',
        type: 'warning',
        duration: 4000,
        icon: Connection
      })
      break
  }
})

watch(() => agentStore.networkError, (error) => {
  if (error) {
    ElNotification({
      title: '网络异常',
      message: error,
      type: 'error',
      duration: 8000,
      icon: WarningFilled
    })
  }
})

// ---------- 生命周期 ----------
onMounted(() => {
  // 自动连接 Agent 服务
  agentBridge.connect()
})

onUnmounted(() => {
  agentBridge.disconnect()
})

/** Blueprint 加载成功后 5 秒自动清除动画 */
watch(() => agentStore.blueprintLoaded, (loaded) => {
  if (loaded) {
    setTimeout(() => {
      agentStore.clearBlueprintLoaded()
    }, 5000)
  }
})

// ---------- 工具函数 ----------
function getRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    user: '用户',
    agent: 'AI',
    system: '系统'
  }
  return labels[role] || role
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN')
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
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  padding: 8px 12px;
  border-radius: 4px;
  max-width: 80%;
}

.message.user {
  align-self: flex-end;
  background: #094771;
}

.message.agent {
  align-self: flex-start;
  background: #2d2d30;
}

.message.system {
  align-self: center;
  background: #3e3e42;
  font-size: 12px;
  max-width: 60%;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 11px;
  color: #888888;
}

.message-role {
  font-weight: 500;
}

.message-content {
  font-size: 13px;
  line-height: 1.5;
}

.message-patch {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #3e3e42;
}

.patch-summary {
  font-size: 12px;
  color: #4ec9b0;
  margin-bottom: 8px;
}

.patch-btn {
  padding: 4px 12px;
  background: #0e639c;
  border: none;
  color: #ffffff;
  cursor: pointer;
  font-size: 12px;
  border-radius: 3px;
}

.patch-btn:hover {
  background: #1177bb;
}

.processing {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #2d2d30;
  border-radius: 4px;
  font-size: 13px;
  color: #888888;
}

.processing .processing-icon {
  font-size: 16px;
}

/* Blueprint 加载成功动画 */
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
}

.success-indicator .success-icon {
  font-size: 18px;
  flex-shrink: 0;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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
}

.connection-bar .connection-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.connection-bar .connection-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.connection-bar .reconnect-btn {
  flex-shrink: 0;
  color: #4ec9b0;
  font-size: 12px;
  padding: 0 4px;
  height: auto;
}

.connection-bar.status-connected {
  color: #4ec9b0;
}

.connection-bar.status-connecting,
.connection-bar.status-reconnecting {
  color: #dcdcaa;
}

.connection-bar.status-disconnected {
  color: #f48771;
}

/* 发送按钮 */
.input-container {
  padding: 12px;
  background: #2d2d30;
  border-top: 1px solid #3e3e42;
  display: flex;
  gap: 8px;
}

.input-container :deep(.el-textarea) {
  flex: 1;
}

.input-container :deep(.el-textarea__inner) {
  min-height: 84px;
  padding: 8px;
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  color: #cccccc;
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
  color: #ffffff;
  cursor: pointer;
  font-size: 13px;
  border-radius: 3px;
  transition: all 0.15s;
}

.send-btn:hover:not(:disabled) {
  background: #1177bb;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
