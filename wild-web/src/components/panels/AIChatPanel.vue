<template>
  <div class="ai-chat-panel">
    <div class="messages-container" ref="messagesRef">
      <div
        v-for="message in agentStore.session.messages"
        :key="message.id"
        :class="['message', message.role]"
      >
        <div class="message-header">
          <span class="message-role">{{ getRoleLabel(message.role) }}</span>
          <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        </div>
        <div class="message-content">{{ message.content }}</div>
        <div v-if="message.patch" class="message-patch">
          <div class="patch-summary">{{ message.patch.summary }}</div>
          <button class="patch-btn" @click="handleApplyPatch(message.patch!)">
            应用修改
          </button>
        </div>
      </div>

      <div v-if="agentStore.isProcessing" class="processing">
        <span class="processing-icon">⟳</span>
        <span>{{ agentStore.currentStep || '处理中...' }}</span>
      </div>

      <div v-if="!agentStore.session.connected" class="connection-status">
        未连接到 Agent 服务
      </div>
    </div>

    <div class="input-container">
      <textarea
        v-model="inputText"
        placeholder="输入您的建筑需求..."
        @keydown.enter.ctrl="handleSend"
        rows="3"
      ></textarea>
      <button @click="handleSend" :disabled="!inputText.trim() || agentStore.isProcessing">
        发送
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAgentStore } from '../../stores/agentStore'
import { useSceneStore } from '../../stores/sceneStore'
import type { ScenePatch } from '../../types/scenePatch'

const agentStore = useAgentStore()
const sceneStore = useSceneStore()
const inputText = ref('')

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

function handleSend() {
  if (!inputText.value.trim()) return

  agentStore.addUserMessage(inputText.value)
  
  // TODO: 通过 WebSocket 发送到后端
  // 目前只是模拟响应
  setTimeout(() => {
    agentStore.addAgentMessage('收到您的请求，Agent 服务尚未启动。')
  }, 500)

  inputText.value = ''
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

.processing-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.connection-status {
  padding: 8px 12px;
  text-align: center;
  font-size: 12px;
  color: #f48771;
}

.input-container {
  padding: 12px;
  background: #2d2d30;
  border-top: 1px solid #3e3e42;
  display: flex;
  gap: 8px;
}

.input-container textarea {
  flex: 1;
  padding: 8px;
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  color: #cccccc;
  font-size: 13px;
  font-family: inherit;
  border-radius: 3px;
  resize: none;
}

.input-container textarea:focus {
  outline: none;
  border-color: #007acc;
}

.input-container button {
  padding: 0 20px;
  background: #0e639c;
  border: none;
  color: #ffffff;
  cursor: pointer;
  font-size: 13px;
  border-radius: 3px;
  transition: all 0.15s;
}

.input-container button:hover:not(:disabled) {
  background: #1177bb;
}

.input-container button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
