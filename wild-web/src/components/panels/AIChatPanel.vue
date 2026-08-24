<template>
  <div class="ai-chat-panel">
    <!-- 会话列表面板 -->
    <SessionListPanel
      @switch="handleSessionSwitch"
      @new="handleNewSession"
      @delete="handleDeleteSession"
    />

    <div class="messages-container" ref="messagesRef">
      <div class="messages-timeline" ref="timelineRef">
      <!-- 所有模式共用同一条时间线；执行过程绑定到发起它的用户消息。 -->
      <template v-for="message in agentStore.session.messages" :key="message.id">
        <div :class="['message', message.role]">
          <div class="message-header">
            <span class="message-role">{{ getRoleLabel(message.role) }}</span>
            <span class="message-time">{{ formatTime(message.timestamp) }}</span>
          </div>
          <div class="message-content" v-html="renderMarkdown(message.content)"></div>
          <div
            v-if="message.role === 'agent' && (message.cited_chunk_ids?.length || message.evidence_status === 'insufficient')"
            class="rag-evidence"
          >
            <span class="rag-evidence-title">
              {{ message.evidence_status === 'insufficient' ? '知识库证据不足' : '知识库引用' }}
            </span>
            <code
              v-for="chunkId in message.cited_chunk_ids || []"
              :key="chunkId"
              class="rag-chunk-id"
              :title="chunkId"
            >{{ chunkId }}</code>
          </div>
          <div v-if="message.role === 'agent' && message.request_id && !message.patch" class="rag-feedback">
            <span>这个回答有帮助吗？</span>
            <button
              type="button"
              class="feedback-button"
              :class="{ active: message.feedback_rating === 'up' }"
              :disabled="message.feedback_pending || Boolean(message.feedback_rating)"
              title="有帮助"
              @click="handleRagFeedback(message, 'up')"
            >👍</button>
            <button
              type="button"
              class="feedback-button"
              :class="{ active: message.feedback_rating === 'down' }"
              :disabled="message.feedback_pending || Boolean(message.feedback_rating)"
              title="没有帮助"
              @click="handleRagFeedback(message, 'down')"
            >👎</button>
            <span v-if="message.feedback_pending" class="feedback-status">提交中…</span>
            <span v-else-if="message.feedback_error" class="feedback-error">{{ message.feedback_error }}</span>
          </div>
          <div v-if="message.patch" class="message-patch">
            <div class="patch-summary">{{ message.patch.summary }}</div>
            <div v-if="getMaterialTunings(message).length" class="material-tuning-list">
              <div v-for="tuning in getMaterialTunings(message)" :key="`${tuning.id}:${tuning.newName}`" class="material-tuning-item">
                <div class="material-tuning-title">
                  {{ tuning.id }} · {{ tuning.field }} · {{ tuning.sourceName || '当前材质' }} → {{ tuning.newName }}
                </div>
                <div class="material-tuning-values">{{ tuning.values }}</div>
                <div v-if="tuning.rationale" class="material-tuning-reason">{{ tuning.rationale }}</div>
              </div>
            </div>
            <div class="patch-actions">
              <el-button
                class="patch-btn"
                size="small"
                :disabled="getPatchStatus(message) !== 'pending'"
                :loading="getPatchStatus(message) === 'applying'"
                @click="handleApplyPatch(message)"
              >
                {{ getPatchActionLabel(message) }}
              </el-button>
              <el-button
                v-if="message.patch.requires_confirmation && getPatchStatus(message) === 'pending'"
                class="patch-btn reject-btn"
                size="small"
                @click="handleRejectPatch(message)"
              >
                拒绝
              </el-button>
              </div>
            </div>
        </div>
        <AgentExecutionPanel
          v-if="message.role === 'user' && agentStore.getTurnForMessage(message)"
          :turn="agentStore.getTurnForMessage(message)!"
        />
      </template>

      <!-- 兼容没有 request_id 的旧后端事件。 -->
      <div v-if="agentStore.isProcessing && !hasRunningTurn" class="processing">
        <el-icon class="processing-icon is-loading">
          <Loading />
        </el-icon>
        <span>{{ agentStore.currentStep || '处理中...' }}</span>
      </div>

      <!-- Blueprint 加载成功 -->
      <div v-if="agentStore.blueprintLoaded" class="success-indicator">
        <el-icon class="success-icon">
          <CircleCheckFilled />
        </el-icon>
        <span>Blueprint 已加载到场景</span>
      </div>
      </div>
    </div>

    <button v-if="isUserScrolling" class="jump-latest" type="button" @click="resumeAutoScroll">
      回到最新
    </button>

    <!-- 连接状态栏 -->
    <div class="connection-bar" :class="connectionStatusClass">
      <el-icon v-if="connectionIcon" class="connection-icon">
        <component :is="connectionIcon" />
      </el-icon>
      <span class="connection-text">{{ connectionStatusText }}</span>
      <div class="thinking-toggle"
        :title="agentStore.precisionMode ? '精密模式下自动开启思考，不可关闭' : '请求模型开启思考，并实时展示接口返回的 reasoning_content'">
        <span>思考</span>
        <el-switch :model-value="agentStore.precisionMode ? true : agentStore.thinkingMode" size="small"
          :disabled="agentStore.isProcessing || agentStore.precisionMode" @change="handleThinkingModeChange" />
      </div>
      <div class="thinking-toggle precision-toggle"
        :title="agentStore.precisionMode ? 'LangGraph 精密模式：分片并行 + RAG/LLM 详细诊断' : 'LangChain 快速模式：单体 Agent'">
        <span>精密</span>
        <el-switch :model-value="agentStore.precisionMode" size="small" :disabled="agentStore.isProcessing"
          @change="handlePrecisionModeChange" />
      </div>
      <div class="thinking-toggle shader-toggle"
        :title="agentStore.proceduralMaterialsEnabled ? '已允许 AI 自动生成程序化纹理 Shader' : '默认关闭；开启后 AI 才能自动生成程序化纹理 Shader'">
        <span>Shader</span>
        <el-switch :model-value="agentStore.proceduralMaterialsEnabled" size="small"
          :disabled="agentStore.isProcessing" @change="handleProceduralMaterialsChange" />
      </div>
      <el-button v-if="agentStore.connectionStatus === 'disconnected'" text size="small" class="reconnect-btn"
        @click="handleReconnect">
        重新连接
      </el-button>
    </div>

    <!-- 输入框 -->
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
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { ElNotification, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import 'highlight.js/styles/vs2015.css'
import {
  Loading, Promotion, Connection, Link, WarningFilled, CircleCheckFilled,
} from '@element-plus/icons-vue'
import { useAgentStore } from '../../stores/agentStore'
import { useSceneStore } from '../../stores/sceneStore'
import { agentBridge } from '../../agent/agentBridge'
import SessionListPanel from './SessionListPanel.vue'
import AgentExecutionPanel from './AgentExecutionPanel.vue'
import type { ChatMessage } from '../../types/agent'

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('python', python)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('xml', xml)

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
const timelineRef = ref<HTMLElement | null>(null)
const sessionHint = ref('')

// 用户滚动检测
const isUserScrolling = ref(false)
const hasRunningTurn = computed(() =>
  agentStore.currentTurns.some(turn => turn.status === 'running')
)

let scrollFrame: number | null = null
let timelineResizeObserver: ResizeObserver | null = null

// 所有流式内容只使用主消息区这一层滚动。等 DOM 和 Markdown 完成布局后再贴底，
// 避免连续 thinking_delta 到达时 scrollHeight 仍是上一帧的值。
function scrollToBottom(force = false) {
  if (!force && isUserScrolling.value) return

  void nextTick().then(() => {
    if (!force && isUserScrolling.value) return
    if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame)
    scrollFrame = window.requestAnimationFrame(() => {
      scrollFrame = null
      const container = messagesRef.value
      if (!container || (!force && isUserScrolling.value)) return
      container.scrollTop = Math.max(0, container.scrollHeight - container.clientHeight)
    })
  })
}

// 检测用户是否在滚动
function handleUserScroll() {
  if (!messagesRef.value) return

  const container = messagesRef.value
  const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= 80

  isUserScrolling.value = !isAtBottom
}

function resumeAutoScroll() {
  isUserScrolling.value = false
  scrollToBottom(true)
}

// 消息或流水线步骤有变化时自动滚动（只在必要时触发）
watch(() => agentStore.session.messages.length, () => scrollToBottom(), { flush: 'post' })
watch(() => agentStore.blueprintLoaded, () => scrollToBottom(), { flush: 'post' })
watch(
  () => agentStore.currentTurns.map(turn =>
    `${turn.turn_id}:${turn.status}:${turn.steps.length}:${turn.steps.map(step => step.thinking.length).join(',')}`
  ).join('|'),
  () => scrollToBottom(),
  { flush: 'post' },
)

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
  resumeAutoScroll()
  const requestId = agentBridge.sendUserMessage(message)
  if (requestId) inputText.value = ''
}

function handleReconnect() {
  agentBridge.connect()
}

function handleThinkingModeChange(value: boolean | string | number) {
  agentStore.setThinkingMode(Boolean(value))
}

function handlePrecisionModeChange(value: boolean | string | number) {
  const enabled = Boolean(value)
  agentStore.setPrecisionMode(enabled)
  // 精密模式依赖思考流展示每个节点的推理过程，强制开启思考
  if (enabled) {
    agentStore.setThinkingMode(true)
  }
}

function handleProceduralMaterialsChange(value: boolean | string | number) {
  agentStore.setProceduralMaterialsEnabled(Boolean(value))
}

// ---------- 连接状态 ----------
const connectionIcon = computed(() => {
  switch (agentStore.connectionStatus) {
    case 'connected': return CircleCheckFilled
    case 'connecting':
    case 'reconnecting': return Connection
    case 'disconnected': return WarningFilled
    default: return Link
  }
})

const connectionStatusClass = computed(() => `status-${agentStore.connectionStatus}`)

const connectionStatusText = computed(() => {
  switch (agentStore.connectionStatus) {
    case 'connecting': return '正在连接 Agent 服务...'
    case 'connected': return 'Agent 服务已连接'
    case 'reconnecting': return '连接断开，正在重新连接...'
    case 'disconnected': return agentStore.networkError || '未连接到 Agent 服务'
    default: return '未知状态'
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

// 监听滚动事件
onMounted(() => {
  if (messagesRef.value) {
    messagesRef.value.addEventListener('scroll', handleUserScroll)
  }
  if (timelineRef.value && typeof ResizeObserver !== 'undefined') {
    timelineResizeObserver = new ResizeObserver(() => scrollToBottom())
    timelineResizeObserver.observe(timelineRef.value)
  }
  void restoreSessionsFromServer().finally(() => resumeAutoScroll())
})

onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', handleUserScroll)
  }
  timelineResizeObserver?.disconnect()
  if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame)
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

function getPatchStatus(message: ChatMessage): NonNullable<ChatMessage['patch_status']> {
  if (message.patch_status) return message.patch_status
  return agentStore.pendingPatch?.patch_id === message.patch?.patch_id
    ? 'pending'
    : 'expired'
}

function getPatchActionLabel(message: ChatMessage): string {
  return ({
    pending: '应用修改',
    applying: '正在应用',
    applied: '已应用',
    rejected: '已拒绝',
    expired: '已失效',
  } as const)[getPatchStatus(message)]
}

function getMaterialTunings(message: ChatMessage) {
  const labels: Record<string, string> = {
    baseColor: '基础色', roughness: '粗糙度', metallic: '金属度', albedo: '反照率',
    emissive: '自发光', opacity: '透明度', normalScale: '法线强度', uvScale: '纹理比例',
  }
  return (message.patch?.operations || [])
    .filter(operation => operation.op === 'tune_material')
    .map(operation => ({
      id: operation.id,
      field: operation.material_field || 'material',
      sourceName: operation.source_name,
      newName: operation.new_name,
      rationale: operation.rationale,
      values: Object.entries(operation.changes)
        .map(([key, value]) => {
          const format = (item: unknown) => Array.isArray(item) ? item.join(' × ') : String(item)
          const before = operation.before?.[key]
          return `${labels[key] || key}: ${before === undefined ? '' : `${format(before)} → `}${format(value)}`
        })
        .join('；'),
    }))
}

function setPatchStatus(
  message: ChatMessage,
  status: NonNullable<ChatMessage['patch_status']>,
) {
  // 兼容本次开发热更新前已经创建的旧 Pinia Store 实例。
  // 新实例通过 action 同步 localStorage；旧实例至少能立即更新按钮状态并避免运行时异常。
  if (typeof agentStore.setPatchMessageStatus === 'function' && message.patch) {
    agentStore.setPatchMessageStatus(message.patch.patch_id, status)
    return
  }
  message.patch_status = status
}

async function handleApplyPatch(message: ChatMessage) {
  const patch = message.patch
  if (!patch || getPatchStatus(message) !== 'pending') return
  setPatchStatus(message, 'applying')
  const ok = await sceneStore.applyPatch(patch)
  if (ok) {
    setPatchStatus(message, 'applied')
    agentStore.addSystemMessage('✅ 已应用到当前草稿；点击顶部“保存”后才会写入服务器')
    agentStore.confirmPatch(patch.patch_id)
  } else {
    setPatchStatus(message, 'pending')
    agentStore.addSystemMessage('❌ 应用修改失败，可能版本已过期')
  }
}

function handleRejectPatch(message: ChatMessage) {
  const patch = message.patch
  if (!patch || getPatchStatus(message) !== 'pending') return
  setPatchStatus(message, 'rejected')
  agentStore.rejectPatch(patch.patch_id)
  agentStore.addSystemMessage('🚫 已拒绝该修改建议')
}

async function handleRagFeedback(message: ChatMessage, rating: 'up' | 'down') {
  if (!message.request_id || message.feedback_pending || message.feedback_rating) return
  const sessionId = agentStore.currentSessionId
  agentStore.setMessageFeedback(sessionId, message.id, {
    feedback_pending: true,
    feedback_error: undefined,
  })
  const ok = await agentBridge.submitRagFeedback(sessionId, message.request_id, rating)
  agentStore.setMessageFeedback(sessionId, message.id, ok
    ? { feedback_pending: false, feedback_rating: rating, feedback_error: undefined }
    : { feedback_pending: false, feedback_error: '提交失败，请稍后重试' })
  if (!ok) {
    ElNotification({
      title: '反馈提交失败',
      message: '没有找到对应的 RAG 追踪记录，请稍后重试。',
      type: 'warning',
      duration: 4000,
    })
  }
}

// ── 会话切换 ──
async function handleSessionSwitch(sessionId: string) {
  if (sessionId === agentStore.currentSessionId) return
  resumeAutoScroll()
  agentStore.switchToSession(sessionId)
  const [serverMessages, serverTurns] = await Promise.all([
    agentBridge.fetchSessionMessages(sessionId),
    agentBridge.fetchSessionTurns(sessionId),
  ])
  if (serverMessages) agentStore.mergeMessagesForSession(sessionId, serverMessages)
  if (serverTurns) agentStore.mergeTurnsForSession(sessionId, serverTurns)
  const bp = await agentBridge.loadSessionBlueprint(sessionId)
  if (bp) {
    await sceneStore.loadBlueprint(bp as any)
    const name = agentStore.sessions.find(item => item.session_id === sessionId)?.name
      || (bp as any).meta?.name
      || '未命名建筑'
    const count = (bp as any).geometry?.elements?.length || 0
    const compCount = (bp as any).geometry?.components?.length || 0
    agentStore.updateSessionInfo(sessionId, name, count, compCount)
    agentStore.addSystemMessage(`✅ 已切换到: ${name}`)
  } else {
    const doc = sceneStore.createEmptyDocument()
    await sceneStore.loadBlueprint(doc.blueprint, doc.name)
  }
}

async function handleNewSession() {
  resumeAutoScroll()
  const newId = agentStore.createSession()
  agentStore.switchToSession(newId)
  const doc = sceneStore.createEmptyDocument()
  await sceneStore.loadBlueprint(doc.blueprint, doc.name)
}

async function handleDeleteSession(sessionId: string) {
  if (agentStore.sessions.length <= 1) return

  try {
    await ElMessageBox.confirm(
      '删除后将永久移除该建筑及其蓝图文件，不可恢复。确定继续？',
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  const deleted = await agentBridge.deleteSessionBlueprint(sessionId)
  if (!deleted) {
    agentStore.addSystemMessage('❌ 服务器删除失败，会话仍然保留')
    return
  }
  agentStore.removeSession(sessionId)
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

// ── 页面初始化：以服务器 storage/scenes/*.wild 为会话事实来源 ──
async function restoreSessionsFromServer() {
  const serverScenes = await agentBridge.fetchSessionList()
  if (serverScenes === null) {
    // 后端暂不可用时，从 localStorage 恢复草稿会话
    restoreFromLocalDrafts()
    return
  }

  const serverSessions = serverScenes.map((scene, index) => {
    const filename = scene.filename || ''
    const basename = filename.split(/[\\/]/).pop()?.replace(/\.wild$/, '') || ''
    const match = basename.match(/^(session_\d+)/)
    const session_id = scene.session_id || (match ? match[1] : basename) || `session_restored_${index}`
    return {
      session_id,
      filename: filename || undefined,
      name: scene.name,
      created_at: scene.created_at || scene.updated_at,
      updated_at: scene.updated_at,
      elements_count: scene.elements_count,
      components_count: scene.components_count || 0,
      message_count: scene.message_count || 0,
      building_type: scene.building_type,
      status: scene.status === 'draft' ? 'draft' as const : 'saved' as const,
    }
  })
  agentStore.replaceSessions(serverSessions)

  if (serverSessions.length === 0) {
    await handleNewSession()
    return
  }

  // 优先恢复上次使用的会话（localStorage），否则恢复最近更新的
  const lastId = loadLastSessionFromLocal()
  const targetId = lastId && serverSessions.find(s => s.session_id === lastId)
    ? lastId
    : serverSessions[0].session_id

  agentStore.switchToSession(targetId)
  const [serverMessages, serverTurns] = await Promise.all([
    agentBridge.fetchSessionMessages(targetId),
    agentBridge.fetchSessionTurns(targetId),
  ])
  if (serverMessages) agentStore.mergeMessagesForSession(targetId, serverMessages)
  if (serverTurns) agentStore.mergeTurnsForSession(targetId, serverTurns)
  const bp = await agentBridge.loadSessionBlueprint(targetId)
  if (bp) {
    sceneStore.loadBlueprint(bp as any)
    const name = agentStore.sessions.find(item => item.session_id === targetId)?.name
      || (bp as any).meta?.name
      || '未命名建筑'
    const count = (bp as any).geometry?.elements?.length || 0
    const compCount = (bp as any).geometry?.components?.length || 0
    agentStore.updateSessionInfo(targetId, name, count, compCount)
  } else {
    const sessionInfo = agentStore.sessions.find(item => item.session_id === targetId)
    if (sessionInfo?.status === 'draft') {
      const doc = sceneStore.createEmptyDocument()
      await sceneStore.loadBlueprint(doc.blueprint, doc.name)
    } else {
      agentStore.addSystemMessage(`❌ 无法读取服务器会话文件`)
    }
  }
}

function restoreFromLocalDrafts() {
  const drafts = loadDraftSessionsFromLocal()
  if (drafts.length > 0) {
    agentStore.replaceSessions(drafts)
    agentStore.switchToSession(drafts[0].session_id)
  } else {
    const newId = agentStore.createSession()
    agentStore.switchToSession(newId)
  }
  const doc = sceneStore.createEmptyDocument()
  sceneStore.loadBlueprint(doc.blueprint, doc.name)
}

function loadLastSessionFromLocal(): string | null {
  try { return localStorage.getItem('wild_last_session') } catch { return null }
}

function loadDraftSessionsFromLocal(): any[] {
  try {
    const raw = localStorage.getItem('wild_draft_sessions')
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}
</script>

<style scoped>
/* ── 基础变量 ── */
.ai-chat-panel {
  --bg-primary: #1e1e20;
  --bg-secondary: #252528;
  --bg-tertiary: #2c2c30;
  --bg-hover: #323236;
  --border: rgba(255, 255, 255, 0.05);
  --border-strong: rgba(255, 255, 255, 0.08);
  --text-primary: #e4e4e7;
  --text-secondary: #a0a0a8;
  --text-muted: #6b6b75;
  --accent: #6899d4;
  --accent-soft: rgba(104, 153, 212, 0.10);
  --accent-border: rgba(104, 153, 212, 0.18);
  --success: #6bbf9b;
  --warn: #d4b871;
  --error: #e07060;
  --user-bubble: rgba(104, 153, 212, 0.12);

  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial,
    "Noto Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
  line-height: 1.5;
}

/* ── Session List Panel（替代旧 session-bar）── */
/* SessionListPanel 自带 scoped 样式，此处只保留外层布局 */
.ai-chat-panel :deep(.session-list-panel) {
  flex-shrink: 0;
  position: relative;
  z-index: 10;
}

/* ── Messages Container ── */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  min-height: 0;
  overflow-anchor: none;
}

.messages-timeline {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* 底部锚定：内容少时对话贴底（输入上方），避免下方大片空白；
   内容溢出时该占位 flex 收缩为 0，正常滚动。 */
.messages-timeline::before {
  content: '';
  flex: 1 1 auto;
  min-height: 0;
}

/* ── Message Bubbles ── */
.message {
  padding: 12px 16px;
  border-radius: 12px;
  max-width: 85%;
  animation: msgIn 0.2s ease-out;
  line-height: 1.6;
}

.message.user {
  align-self: flex-end;
  background: var(--user-bubble);
  border: 1px solid var(--accent-border);
  border-bottom-right-radius: 4px;
}

.message.agent {
  align-self: flex-start;
  background: var(--bg-tertiary);
  border-bottom-left-radius: 4px;
}

/* ── System Message: 居中、降权、克制 ── */
.message.system {
  align-self: center;
  background: transparent;
  font-size: 11.5px;
  max-width: 70%;
  color: var(--text-muted);
  text-align: center;
  padding: 6px 16px;
  line-height: 1.5;
  display: flex;
  align-items: center;
  gap: 6px;
  animation: msgIn 0.25s ease-out;
}

.message.system .message-header {
  display: none;
}

.message.system::before {
  content: "✦";
  font-size: 9px;
  color: rgba(212, 184, 113, 0.45);
  flex-shrink: 0;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

.message-role {
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
}

.message-time {
  font-size: 10.5px;
  color: var(--text-muted);
}

.message-content {
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--text-primary);
}

.rag-evidence {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px dashed var(--border);
  font-size: 11px;
}

.rag-evidence-title {
  color: var(--text-muted);
}

.rag-chunk-id {
  max-width: 100%;
  overflow: hidden;
  padding: 2px 5px;
  border-radius: 3px;
  background: rgba(78, 161, 243, 0.09);
  color: var(--accent);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rag-feedback {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 7px;
  font-size: 11px;
  color: var(--text-muted);
}

.feedback-button {
  padding: 1px 4px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  filter: grayscale(1);
  opacity: 0.65;
}

.feedback-button:hover:not(:disabled),
.feedback-button.active {
  border-color: var(--border-strong);
  background: rgba(255, 255, 255, 0.06);
  filter: none;
  opacity: 1;
}

.feedback-button:disabled {
  cursor: default;
}

.feedback-status {
  color: var(--text-secondary);
}

.feedback-error {
  color: var(--error);
}

@keyframes msgIn {
  from {
    opacity: 0;
    transform: translateY(6px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── Markdown ── */
.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3),
.message-content :deep(h4) {
  margin: 12px 0 6px;
  font-weight: 600;
  line-height: 1.3;
}

.message-content :deep(h1) {
  font-size: 1.4em;
}

.message-content :deep(h2) {
  font-size: 1.25em;
  border-bottom: 1px solid var(--border);
  padding-bottom: 4px;
}

.message-content :deep(h3) {
  font-size: 1.1em;
}

.message-content :deep(h4) {
  font-size: 1em;
  color: var(--text-secondary);
}

.message-content :deep(p) {
  margin: 4px 0;
}

.message-content :deep(ul),
.message-content :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}

.message-content :deep(li) {
  margin: 2px 0;
}

.message-content :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--accent);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-secondary);
}

.message-content :deep(code) {
  font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.06);
  padding: 1px 5px;
  border-radius: 3px;
  color: #ce9178;
}

.message-content :deep(pre.hljs) {
  margin: 8px 0;
  padding: 12px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
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
  border: 1px solid var(--border);
  padding: 4px 8px;
  text-align: left;
}

.message-content :deep(th) {
  background: var(--bg-tertiary);
  font-weight: 600;
}

.message-content :deep(a) {
  color: var(--accent);
  text-decoration: none;
}

.message-content :deep(a:hover) {
  text-decoration: underline;
}

.message-content :deep(hr) {
  margin: 12px 0;
  border: none;
  border-top: 1px solid var(--border);
}

.message-content :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}

.message-content :deep(em) {
  font-style: italic;
}

/* ── Patch ── */
.message-patch {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.patch-summary {
  font-size: 12px;
  color: var(--success);
  margin-bottom: 8px;
}

.material-tuning-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.material-tuning-item {
  padding: 7px 8px;
  border-left: 2px solid var(--accent);
  border-radius: var(--radius-sm);
  background: rgba(78, 161, 243, 0.07);
  font-size: 11px;
}

.material-tuning-title { color: var(--text-primary); }
.material-tuning-values { margin-top: 3px; color: var(--text-secondary); line-height: 1.5; }
.material-tuning-reason { margin-top: 3px; color: var(--text-muted); }

.patch-btn {
  padding: 4px 12px;
  font-size: 12px;
  border-radius: var(--radius-sm);
  background: var(--accent-soft);
  border: 1px solid rgba(78, 161, 243, 0.2);
  color: var(--accent);
  cursor: pointer;
  transition: all 0.15s;
}

.patch-btn:hover {
  background: rgba(78, 161, 243, 0.2);
}

.patch-actions {
  display: flex;
  gap: 8px;
}

.reject-btn {
  background: transparent;
  border: 1px solid var(--border-strong);
  color: var(--text-muted);
}

.reject-btn:hover {
  background: rgba(224, 112, 96, 0.08);
  color: var(--error);
  border-color: rgba(224, 112, 96, 0.2);
}

/* ── Processing ── */
.processing {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg-tertiary);
  border-radius: 12px;
  font-size: 13px;
  color: var(--text-secondary);
  align-self: flex-start;
  border-bottom-left-radius: 4px;
}

.processing-icon {
  font-size: 15px;
  color: var(--accent);
}

/* ── Pipeline Stream ── */
.pipeline-stream {
  align-self: stretch;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pipeline-stream-title {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.pipeline-line {
  line-height: 1.6;
  word-break: break-all;
  animation: fadeIn 0.2s ease-out;
}

.pipeline-line.status-ok {
  color: var(--success);
}

.pipeline-line.status-warn {
  color: var(--warn);
}

.pipeline-line.status-error {
  color: var(--error);
}

.pipeline-line.status-skip {
  color: var(--text-muted);
}

/* ── Thinking Stream ── */
.thinking-stream {
  align-self: stretch;
  background: rgba(104, 153, 212, 0.05);
  border: 1px solid rgba(104, 153, 212, 0.10);
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.thinking-stream-title {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.04em;
  display: flex;
  justify-content: space-between;
}

.thinking-content {
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.thinking-notice {
  color: var(--warn);
}

.thinking-status.status-thinking {
  color: var(--accent);
}

.thinking-status.status-completed {
  color: var(--success);
}

.thinking-status.status-unsupported,
.thinking-status.status-error {
  color: var(--error);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateX(-4px);
  }

  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* ── Success Indicator ── */
.success-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(107, 191, 155, 0.07);
  border: 1px solid rgba(107, 191, 155, 0.15);
  border-radius: 8px;
  font-size: 13px;
  color: var(--success);
  align-self: stretch;
  animation: fadeInUp 0.35s ease-out;
}

.success-icon {
  font-size: 18px;
  flex-shrink: 0;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── Connection Bar ── */
.connection-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 16px;
  font-size: 11px;
  background: var(--bg-primary);
  flex-shrink: 0;
  border-top: 1px solid var(--border);
}

.connection-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.connection-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

.thinking-toggle,
.precision-toggle,
.shader-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 11px;
  letter-spacing: 0.02em;
}

.thinking-toggle :deep(.el-switch.is-checked .el-switch__core),
.precision-toggle :deep(.el-switch.is-checked .el-switch__core),
.shader-toggle :deep(.el-switch.is-checked .el-switch__core) {
  background: var(--accent);
  border-color: var(--accent);
}

.reconnect-btn {
  flex-shrink: 0;
  color: var(--accent);
  font-size: 11px;
  padding: 0 6px;
  height: auto;
}

.connection-bar.status-connected {
  color: var(--success);
}

.connection-bar.status-connecting,
.connection-bar.status-reconnecting {
  color: var(--warn);
}

.connection-bar.status-disconnected {
  color: var(--error);
}

/* ── Input ── */
.input-container {
  padding: 14px 16px;
  background: var(--bg-primary);
  border-top: 1px solid var(--border);
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.input-container :deep(.el-textarea) {
  flex: 1;
}

.input-container :deep(.el-textarea__inner) {
  min-height: 76px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 13.5px;
  font-family: inherit;
  border-radius: 8px;
  resize: none;
  line-height: 1.6;
  transition: border-color 0.15s;
}

.input-container :deep(.el-textarea__inner):focus {
  outline: none;
  border-color: var(--accent-border);
}

.input-container :deep(.el-textarea__inner)::placeholder {
  color: var(--text-muted);
}

.send-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 22px;
  background: var(--accent);
  border: none;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  transition: opacity 0.15s, transform 0.1s;
  flex-shrink: 0;
  letter-spacing: 0.01em;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.88;
  transform: scale(1.01);
}

.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}


.jump-latest {
  position: absolute;
  right: 18px;
  bottom: 128px;
  z-index: 8;
  padding: 7px 12px;
  color: var(--text-primary);
  background: rgba(44, 44, 48, 0.96);
  border: 1px solid var(--accent-border);
  border-radius: 999px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
  cursor: pointer;
  font-size: 12px;
}

.jump-latest:hover {
  border-color: var(--accent);
}

</style>
