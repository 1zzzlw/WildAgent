<template>
  <div class="ai-chat-panel">
    <!-- 会话切换栏 -->
    <div class="session-bar">
      <el-select
        v-model="agentStore.currentSessionId"
        class="session-select"
        size="small"
        popper-class="session-popper"
        @change="handleSessionSwitch"
        placeholder="选择会话"
      >
        <el-option
          v-for="s in agentStore.sessions"
          :key="s.session_id"
          :label="`${s.name} (${s.elements_count} 构件)`"
          :value="s.session_id"
        />
      </el-select>
      <el-button class="session-new-btn" size="small" @click="handleNewSession">
        + 新建
      </el-button>
      <el-button
        class="session-del-btn"
        size="small"
        :disabled="agentStore.sessions.length <= 1"
        :title="agentStore.sessions.length <= 1 ? '至少保留一个会话' : '删除当前会话'"
        @click="handleDeleteSession"
      >
        删除
      </el-button>
    </div>

    <div class="messages-container" ref="messagesRef">

      <!-- 聊天消息 -->
      <div v-for="message in agentStore.session.messages" :key="message.id" :class="['message', message.role]">
        <div class="message-header">
          <span class="message-role">{{ getRoleLabel(message.role) }}</span>
          <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        </div>
        <div class="message-content" v-html="renderMarkdown(message.content)"></div>
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

      <!-- DashScope/OpenAI-compatible 接口实际返回的 reasoning_content -->
      <div v-if="agentStore.thinkingMode && agentStore.thinkingStatus !== 'idle'" class="thinking-stream">
        <div class="thinking-stream-title">
          <span>模型思考内容</span>
          <span :class="['thinking-status', `status-${agentStore.thinkingStatus}`]">
            {{ getThinkingStatusLabel(agentStore.thinkingStatus) }}
          </span>
        </div>
        <div v-if="agentStore.thinkingContent" class="thinking-content">{{ agentStore.thinkingContent }}</div>
        <div v-if="agentStore.thinkingNotice" class="thinking-notice">{{ agentStore.thinkingNotice }}</div>
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
      <div
        class="thinking-toggle"
        title="请求模型开启思考，并实时展示接口返回的 reasoning_content"
      >
        <span>思考模式</span>
        <el-switch
          :model-value="agentStore.thinkingMode"
          size="small"
          :disabled="agentStore.isProcessing"
          @change="handleThinkingModeChange"
        />
      </div>
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
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ElNotification, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/vs2015.css'
import {
  Loading, Promotion, Connection, Link, WarningFilled, CircleCheckFilled,
} from '@element-plus/icons-vue'
import { useAgentStore } from '../../stores/agentStore'
import { useSceneStore } from '../../stores/sceneStore'
import { agentBridge } from '../../agent/agentBridge'
import type { ScenePatch } from '../../types/scenePatch'

// ── Markdown 渲染 ──
const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch { /* fallthrough */ }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

function renderMarkdown(content: string): string {
  return md.render(content)
}

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
watch(() => agentStore.thinkingContent.length, scrollToBottom)
watch(() => agentStore.thinkingStatus, scrollToBottom)
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

function handleThinkingModeChange(value: boolean | string | number) {
  agentStore.setThinkingMode(Boolean(value))
}

function getThinkingStatusLabel(status: string) {
  return ({
    thinking: '思考中',
    completed: '已完成',
    unsupported: '不支持',
    error: '失败',
  } as Record<string, string>)[status] || ''
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
onMounted(() => {
  restoreLastSession()
})

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

async function handleApplyPatch(patch: ScenePatch) {
  const ok = await sceneStore.applyPatch(patch)
  if (ok) {
    agentStore.addSystemMessage('✅ 已应用修改')
    // 同步更新后的蓝图到后端
    if (sceneStore.document) {
      agentBridge.syncBlueprintToBackend(
        sceneStore.document.blueprint as Record<string, unknown>
      )
      // 更新会话信息
      const bp = sceneStore.document.blueprint
      const name = bp.meta?.name || '未命名建筑'
      const count = bp.geometry?.elements?.length || 0
      agentStore.updateSessionInfo(agentStore.currentSessionId, name, count)
    }
  } else {
    agentStore.addSystemMessage('❌ 应用修改失败，可能版本已过期')
  }
}

// ── 会话切换 ──
async function handleSessionSwitch(sessionId: string) {
  agentStore.switchToSession(sessionId)
  const bp = await agentBridge.loadSessionBlueprint(sessionId)
  if (bp) {
    sceneStore.loadBlueprint(bp as any)
    const name = (bp as any).meta?.name || '未命名建筑'
    const count = (bp as any).geometry?.elements?.length || 0
    agentStore.updateSessionInfo(sessionId, name, count)
    agentStore.addSystemMessage(`✅ 已切换到: ${name}`)
  } else {
    // 文件不存在，创建空场景
    const doc = sceneStore.createEmptyDocument()
    sceneStore.loadBlueprint(doc.blueprint, doc.name)
  }
}

function handleNewSession() {
  const newId = agentStore.createSession()
  agentStore.switchToSession(newId)
  const doc = sceneStore.createEmptyDocument()
  sceneStore.loadBlueprint(doc.blueprint, doc.name)
  agentStore.addSystemMessage('✨ 新会话已创建，输入建筑需求开始')
}

async function handleDeleteSession() {
  const sid = agentStore.currentSessionId
  if (agentStore.sessions.length <= 1) return

  try {
    await ElMessageBox.confirm(
      '删除当前会话将永久移除该建筑及其蓝图文件，不可恢复。确定继续？',
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return // 用户取消
  }

  await agentBridge.deleteSessionBlueprint(sid)
  agentStore.removeSession(sid)
  // 切换到下一个会话
  const bp = await agentBridge.loadSessionBlueprint(agentStore.currentSessionId)
  if (bp) {
    sceneStore.loadBlueprint(bp as any)
  } else {
    const doc = sceneStore.createEmptyDocument()
    sceneStore.loadBlueprint(doc.blueprint, doc.name)
  }
  agentStore.addSystemMessage('🗑️ 会话已删除')
}

// ── 页面初始化：恢复上次会话 ──
async function restoreLastSession() {
  const sessionId = agentStore.currentSessionId
  if (!sessionId) return

  // 只在会话已有构件时才从后端加载（空会话无对应 .wild 文件）
  const info = agentStore.sessions.find(s => s.session_id === sessionId)
  if (!info || info.elements_count === 0) return

  const bp = await agentBridge.loadSessionBlueprint(sessionId)
  if (bp) {
    sceneStore.loadBlueprint(bp as any)
  }
}
</script>

<style scoped>
.ai-chat-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 会话切换栏 */
.session-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #252526;
  border-bottom: 1px solid #3e3e42;
  flex-shrink: 0;
}
.session-select {
  flex: 1;
  min-width: 0;
}
.session-new-btn {
  height: 28px;
  padding: 0 10px;
  background: #0e639c;
  border: none;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}
.session-new-btn:hover {
  background: #1177bb;
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

/* ── Markdown 渲染样式 ── */
.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3),
.message-content :deep(h4) {
  margin: 12px 0 6px;
  font-weight: 600;
  line-height: 1.3;
}
.message-content :deep(h1) { font-size: 1.4em; }
.message-content :deep(h2) { font-size: 1.25em; border-bottom: 1px solid #3e3e42; padding-bottom: 4px; }
.message-content :deep(h3) { font-size: 1.1em; }
.message-content :deep(h4) { font-size: 1em; color: #aaa; }

.message-content :deep(p) { margin: 4px 0; }
.message-content :deep(ul),
.message-content :deep(ol) { margin: 4px 0; padding-left: 20px; }
.message-content :deep(li) { margin: 2px 0; }
.message-content :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid #007acc;
  background: #1e1e1e;
  color: #999;
}
.message-content :deep(code) {
  font-family: 'Consolas', 'Menlo', monospace;
  font-size: 12px;
  background: #1e1e1e;
  padding: 1px 5px;
  border-radius: 3px;
  color: #ce9178;
}
.message-content :deep(pre.hljs) {
  margin: 8px 0;
  padding: 10px;
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}
.message-content :deep(pre.hljs code) {
  background: transparent;
  padding: 0;
  color: inherit;
}
.message-content :deep(table) {
  margin: 8px 0;
  border-collapse: collapse;
  font-size: 12px;
  width: 100%;
}
.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid #3e3e42;
  padding: 4px 8px;
  text-align: left;
}
.message-content :deep(th) { background: #2d2d30; font-weight: 600; }
.message-content :deep(a) { color: #4ea1f3; text-decoration: none; }
.message-content :deep(a:hover) { text-decoration: underline; }
.message-content :deep(hr) {
  margin: 12px 0;
  border: none;
  border-top: 1px solid #3e3e42;
}
.message-content :deep(strong) { font-weight: 600; color: #e0e0e0; }
.message-content :deep(em) { font-style: italic; }

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

/* 用户可选的模型真实思考流 */
.thinking-stream {
  align-self: stretch;
  background: #20202a;
  border: 1px solid #3d3d55;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.thinking-stream-title {
  color: #9a9ac7;
  font-size: 11px;
  letter-spacing: 0.05em;
  display: flex;
  justify-content: space-between;
}

.thinking-content {
  color: #c5c5dc;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  animation: fadeIn 0.2s ease-out;
}

.thinking-notice { color: #dcdcaa; }
.thinking-status.status-thinking { color: #4ea1f3; }
.thinking-status.status-completed { color: #4ec9b0; }
.thinking-status.status-unsupported,
.thinking-status.status-error { color: #f48771; }

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
.thinking-toggle { display: flex; align-items: center; gap: 6px; color: #b8b8b8; flex-shrink: 0; }
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
