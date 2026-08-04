<template>
  <div class="ai-chat-panel">
    <!-- 会话切换栏 -->
    <div class="session-bar">
      <el-select v-model="agentStore.currentSessionId" class="session-select" size="small" popper-class="session-popper"
        @change="handleSessionSwitch" placeholder="选择会话">
        <el-option v-for="s in agentStore.sessions" :key="s.session_id" :label="`${s.name} (${s.elements_count} 构件)`"
          :value="s.session_id" />
      </el-select>
      <el-button class="session-new-btn" size="small" @click="handleNewSession">
        + 新建
      </el-button>
      <el-button class="session-del-btn" size="small" :disabled="agentStore.sessions.length <= 1"
        :title="agentStore.sessions.length <= 1 ? '至少保留一个会话' : '删除当前会话'" @click="handleDeleteSession">
        删除
      </el-button>
    </div>

    <div class="messages-container" ref="messagesRef">

      <!-- 精密模式：只显示用户消息（AI 回复在精密面板后） -->
      <div v-if="agentStore.precisionMode">
        <div v-for="message in userMessagesOnly" :key="message.id" :class="['message', message.role]">
          <div class="message-header">
            <span class="message-role">{{ getRoleLabel(message.role) }}</span>
            <span class="message-time">{{ formatTime(message.timestamp) }}</span>
          </div>
          <div class="message-content" v-html="renderMarkdown(message.content)"></div>
        </div>
      </div>

      <!-- 非精密模式：显示所有消息 -->
      <div v-else>
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
      </div>

      <!-- 处理中指示器 -->
      <div v-if="agentStore.isProcessing && !agentStore.precisionMode" class="processing">
        <el-icon class="processing-icon is-loading">
          <Loading />
        </el-icon>
        <span>{{ agentStore.currentStep || '处理中...' }}</span>
      </div>

      <!-- LangChain 思考模式 -->
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

      <!-- LangChain 校验流水线 -->
      <div v-if="!agentStore.precisionMode && agentStore.pipelineSteps.length > 0" class="pipeline-stream">
        <div class="pipeline-stream-title">校验流水线</div>
        <div v-for="(step, i) in agentStore.pipelineSteps" :key="i" :class="['pipeline-line', `status-${step.status}`]">
          {{ step.label }}
        </div>
      </div>

      <!-- 精密模式：思考流对话模式 -->
      <div v-if="agentStore.precisionMode && agentStore.generatingNodes.length > 0" class="precision-panel">

        <!-- 每个节点的思考块 -->
        <div v-for="node in agentStore.generatingNodes" :key="node.name"
          :class="['thought-block', `status-${node.status}`]">
          <!-- 思考块头部 -->
          <div class="thought-header" @click="toggleNodeExpand(node.name)">
            <div class="thought-icon">
              <el-icon v-if="node.status === 'running'" class="is-loading">
                <Loading />
              </el-icon>
              <span v-else>{{ statusEmoji(node.status) }}</span>
            </div>
            <div class="thought-meta">
              <div class="thought-title">
                <span class="thought-label">{{ node.label }}</span>
                <span class="thought-status">{{ getStatusLabel(node.status) }}</span>
              </div>
              <div class="thought-summary">{{ node.detail }}</div>
            </div>
            <div class="thought-toggle">
              <el-icon>
                <component :is="expandedNodes.has(node.name) ? 'ArrowDown' : 'ArrowRight'" />
              </el-icon>
            </div>
          </div>

          <!-- 思考过程内容区（可折叠） -->
          <transition name="thought-expand">
            <div v-if="expandedNodes.has(node.name)" class="thought-content">

              <!-- 实时思考流（打字机效果 + Markdown 渲染） -->
              <div v-if="getNodeThinking(node.name)" class="reasoning-section">
                <div class="reasoning-header">
                  <el-icon class="reasoning-icon">
                    <ChatDotRound />
                  </el-icon>
                  <span class="reasoning-title">推理过程</span>
                  <span v-if="node.status === 'running'" class="reasoning-badge">思考中...</span>
                  <span v-else class="reasoning-badge completed">已完成</span>
                </div>
                <div class="reasoning-content typewriter" v-html="renderMarkdown(getNodeThinking(node.name))"></div>
              </div>

              <!-- 诊断信息（完成后显示） -->
              <div v-if="getNodeDiag(node.name)" class="diagnostics-section">
                <div class="diagnostics-header">
                  <el-icon class="diagnostics-icon">
                    <DataAnalysis />
                  </el-icon>
                  <span class="diagnostics-title">执行诊断</span>
                </div>
                <div class="diagnostics-grid">
                  <div v-if="getNodeDiag(node.name).rag_chars" class="diag-card">
                    <div class="diag-card-label">RAG 检索</div>
                    <div class="diag-card-value">{{ getNodeDiag(node.name).rag_chars }} 字</div>
                    <div class="diag-card-sub">{{ getNodeDiag(node.name).rag_ms }}ms</div>
                  </div>
                  <div v-if="getNodeDiag(node.name).llm_chars" class="diag-card">
                    <div class="diag-card-label">LLM 生成</div>
                    <div class="diag-card-value">{{ getNodeDiag(node.name).llm_chars }} 字</div>
                    <div class="diag-card-sub">{{ getNodeDiag(node.name).llm_ms }}ms</div>
                  </div>
                  <div v-if="getNodeDiag(node.name).token_usage" class="diag-card">
                    <div class="diag-card-label">Token 消耗</div>
                    <div class="diag-card-value">{{ getNodeDiag(node.name).token_usage.total }}</div>
                    <div class="diag-card-sub">↑{{ getNodeDiag(node.name).token_usage.input }} ↓{{
                      getNodeDiag(node.name).token_usage.output }}</div>
                  </div>
                  <div v-if="getNodeDiag(node.name).fragment_count" class="diag-card">
                    <div class="diag-card-label">生成结果</div>
                    <div class="diag-card-value">{{ getNodeDiag(node.name).fragment_count }} 个</div>
                    <div class="diag-card-sub">组件</div>
                  </div>
                </div>
              </div>

            </div>
          </transition>
        </div>

        <!-- 性能汇总卡片 -->
        <div v-if="agentStore.sessionMetrics" class="metrics-card">
          <div class="metrics-header">
            <el-icon class="metrics-icon">
              <DataLine />
            </el-icon>
            <span class="metrics-title">性能汇总</span>
          </div>
          <div class="metrics-body">
            <div class="metric-row">
              <span class="metric-label">节点执行</span>
              <span class="metric-value">{{ agentStore.sessionMetrics.active_nodes }}/{{
                agentStore.sessionMetrics.node_count }} 个</span>
            </div>
            <div class="metric-row">
              <span class="metric-label">Token 消耗</span>
              <span class="metric-value">{{ (agentStore.sessionMetrics.total_tokens?.total || 0).toLocaleString()
              }}</span>
            </div>
            <div class="metric-row">
              <span class="metric-label">RAG 检索</span>
              <span class="metric-value">{{ agentStore.sessionMetrics.total_rag_ms }}ms</span>
            </div>
            <div class="metric-row">
              <span class="metric-label">LLM 生成</span>
              <span class="metric-value">{{ agentStore.sessionMetrics.total_llm_ms }}ms</span>
            </div>
            <div class="metric-row">
              <span class="metric-label">组件总数</span>
              <span class="metric-value">{{ agentStore.sessionMetrics.fragment_total }} 个</span>
            </div>
            <div class="metric-row">
              <span class="metric-label">校验状态</span>
              <span class="metric-value">{{ agentStore.sessionMetrics.validation_steps }}步 · {{
                agentStore.sessionMetrics.validation_errors }}错</span>
            </div>
            <div v-if="agentStore.sessionMetrics.retry_count !== undefined" class="metric-row">
              <span class="metric-label">回调重试</span>
              <span class="metric-value">{{ agentStore.sessionMetrics.retry_count }}/{{
                agentStore.sessionMetrics.max_retries || 3 }} 次</span>
            </div>
          </div>
        </div>

      </div>

      <!-- 精密模式：AI 回复和系统消息放到精密面板下方 -->
      <div v-if="agentStore.precisionMode && nonUserMessages.length > 0">
        <div v-for="message in nonUserMessages" :key="message.id" :class="['message', message.role]">
          <div class="message-header">
            <span class="message-role">{{ getRoleLabel(message.role) }}</span>
            <span class="message-time">{{ formatTime(message.timestamp) }}</span>
          </div>
          <div class="message-content" v-html="renderMarkdown(message.content)"></div>
        </div>
      </div>

      <!-- Blueprint 加载成功 -->
      <div v-if="agentStore.blueprintLoaded" class="success-indicator">
        <el-icon class="success-icon">
          <CircleCheckFilled />
        </el-icon>
        <span>Blueprint 已加载到场景</span>
      </div>

    </div>

    <!-- 连接状态栏 -->
    <div class="connection-bar" :class="connectionStatusClass">
      <el-icon v-if="connectionIcon" class="connection-icon">
        <component :is="connectionIcon" />
      </el-icon>
      <span class="connection-text">{{ connectionStatusText }}</span>
      <div class="thinking-toggle" title="请求模型开启思考，并实时展示接口返回的 reasoning_content">
        <span>思考</span>
        <el-switch :model-value="agentStore.thinkingMode" size="small" :disabled="agentStore.isProcessing"
          @change="handleThinkingModeChange" />
      </div>
      <div class="thinking-toggle precision-toggle"
        :title="agentStore.precisionMode ? 'LangGraph 精密模式：分片并行 + RAG/LLM 详细诊断' : 'LangChain 快速模式：单体 Agent'">
        <span>精密</span>
        <el-switch :model-value="agentStore.precisionMode" size="small" :disabled="agentStore.isProcessing"
          @change="handlePrecisionModeChange" />
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
import hljs from 'highlight.js'
import 'highlight.js/styles/vs2015.css'
import {
  Loading, Promotion, Connection, Link, WarningFilled, CircleCheckFilled,
  ArrowDown, ArrowRight, ChatDotRound, DataAnalysis, DataLine,
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
const expandedNodes = ref(new Set<string>())

// 用户滚动检测
const isUserScrolling = ref(false)
const scrollTimeout = ref<number | null>(null)

// 自动滚动到底部
function scrollToBottom() {
  // 如果用户正在滚动，不要自动滚动
  if (isUserScrolling.value) return

  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// 检测用户是否在滚动
function handleUserScroll() {
  if (!messagesRef.value) return

  const container = messagesRef.value
  const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50

  // 如果不在底部，说明用户在向上滚动
  if (!isAtBottom) {
    isUserScrolling.value = true
  } else {
    // 如果在底部，允许自动滚动
    isUserScrolling.value = false
  }

  // 清除之前的定时器
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }

  // 2秒后如果用户没有继续滚动，恢复自动滚动
  scrollTimeout.value = window.setTimeout(() => {
    isUserScrolling.value = false
  }, 2000)
}

// 消息或流水线步骤有变化时自动滚动
watch(() => agentStore.session.messages.length, scrollToBottom)
watch(() => agentStore.pipelineSteps.length, scrollToBottom)
watch(() => agentStore.thinkingContent.length, scrollToBottom)
watch(() => agentStore.thinkingStatus, scrollToBottom)
watch(() => agentStore.isProcessing, scrollToBottom)
watch(() => agentStore.blueprintLoaded, scrollToBottom)
watch(() => agentStore.generatingNodes.length, scrollToBottom)
watch(() => agentStore.sessionMetrics, scrollToBottom)
watch(() => agentStore.nodeThinkingMap.size, scrollToBottom, { deep: true })

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

// ── 精密模式：消息拆分 ──
const userMessagesOnly = computed(() => {
  return agentStore.session.messages.filter(m => m.role === 'user')
})

const nonUserMessages = computed(() => {
  return agentStore.session.messages.filter(m => m.role !== 'user')
})

// ── 精密模式：展开/收起 + 诊断数据获取 ──
function statusEmoji(status: string) {
  return { done: '✅', skipped: '⏭️', error: '❌', running: '🔄' }[status] || '🔄'
}

function getStatusLabel(status: string) {
  return { done: '已完成', skipped: '已跳过', error: '执行失败', running: '执行中...' }[status] || status
}

function getNodeThinking(nodeName: string): string {
  const thinking = agentStore.nodeThinkingMap.get(nodeName)
  return thinking?.content || ''
}

function formatThinkingTime(nodeName: string): string {
  const thinking = agentStore.nodeThinkingMap.get(nodeName)
  if (!thinking) return ''
  const charCount = thinking.content.length
  if (charCount === 0) return ''
  // 估算耗时：假设平均每秒生成50个字符
  const estimatedSeconds = Math.ceil(charCount / 50)
  return `${estimatedSeconds}s`
}

function getNodeReasoning(nodeName: string): string {
  const diag = agentStore.debugLogs.find(
    d => d.category === 'node' && (d.data as any).node === nodeName
  )
  return (diag?.data as any)?.reasoning_preview || ''
}

function getNodeDiag(nodeName: string): any {
  const diag = agentStore.debugLogs.find(
    d => d.category === 'node' && (d.data as any).node === nodeName
  )
  return diag?.data || null
}

function toggleNodeExpand(nodeName: string) {
  const s = new Set(expandedNodes.value)
  if (s.has(nodeName)) s.delete(nodeName)
  else s.add(nodeName)
  expandedNodes.value = s
}

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

function handlePrecisionModeChange(value: boolean | string | number) {
  agentStore.setPrecisionMode(Boolean(value))
  // 精密模式开启时自动关闭思考模式（两者展示内容不同，避免混淆）
  if (Boolean(value) && agentStore.thinkingMode) {
    agentStore.setThinkingMode(false)
  }
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
  restoreSessionsFromServer()
})

onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', handleUserScroll)
  }
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
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
    agentStore.addSystemMessage('✅ 已应用到当前草稿；点击顶部“保存”后才会写入服务器')
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

async function handleNewSession() {
  const newId = agentStore.createSession()
  agentStore.switchToSession(newId)
  const doc = sceneStore.createEmptyDocument()
  await sceneStore.loadBlueprint(doc.blueprint, doc.name)
  agentStore.addSystemMessage('✨ 新会话草稿已创建；生成建筑或点击顶部“保存”后才会写入服务器')
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

  const deleted = await agentBridge.deleteSessionBlueprint(sid)
  if (!deleted) {
    agentStore.addSystemMessage('❌ 服务器删除失败，会话仍然保留')
    return
  }
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

// ── 页面初始化：以服务器 storage/scenes/*.wild 为会话事实来源 ──
async function restoreSessionsFromServer() {
  const serverScenes = await agentBridge.fetchSessionList()
  if (serverScenes === null) {
    // 后端暂不可用时保留一个临时空会话，避免发送消息时使用空 session_id。
    const newId = agentStore.createSession()
    agentStore.switchToSession(newId)
    const doc = sceneStore.createEmptyDocument()
    sceneStore.loadBlueprint(doc.blueprint, doc.name)
    agentStore.addSystemMessage('❌ 无法从服务器读取会话列表，当前会话尚未持久化')
    return
  }

  const serverSessions = serverScenes.map(scene => {
    // filename 格式：
    //   新格式：2026-08-02/session_1234567890_建筑名.wild
    //   旧格式：session_1234567890.wild
    // session_id 固定格式是 session_<timestamp>，从 basename 里精确提取
    const basename = scene.filename.split('/').pop()!.replace(/\.wild$/, '')
    // 匹配 session_ 开头 + 纯数字的部分作为 session_id
    const match = basename.match(/^(session_\d+)/)
    const session_id = match ? match[1] : basename
    return {
      session_id,
      filename: scene.filename,   // 保留完整相对路径供 load/delete 使用
      name: scene.name,
      created_at: scene.updated_at,
      updated_at: scene.updated_at,
      elements_count: scene.elements_count,
    }
  })
  agentStore.replaceSessions(serverSessions)

  if (serverSessions.length === 0) {
    await handleNewSession()
    return
  }

  // 接口已按文件修改时间倒序返回，因此默认恢复服务器上最近更新的场景。
  const sessionId = serverSessions[0].session_id
  agentStore.switchToSession(sessionId)
  const bp = await agentBridge.loadSessionBlueprint(sessionId)
  if (bp) {
    sceneStore.loadBlueprint(bp as any)
  } else {
    agentStore.addSystemMessage(`❌ 无法读取服务器会话文件: ${sessionId}.wild`)
  }
}
</script>

<style scoped>
/* ── 基础变量 ── */
.ai-chat-panel {
  --bg-primary: #1a1a1a;
  --bg-secondary: #202020;
  --bg-tertiary: #262626;
  --bg-hover: #2a2a2a;
  --border: rgba(255, 255, 255, 0.06);
  --border-strong: rgba(255, 255, 255, 0.1);
  --text-primary: #e8e8e8;
  --text-secondary: #999;
  --text-muted: #666;
  --accent: #4ea1f3;
  --accent-soft: rgba(78, 161, 243, 0.12);
  --success: #4ec9b0;
  --warn: #dcdcaa;
  --error: #f48771;
  --user-bubble: rgba(78, 161, 243, 0.15);
  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 18px;

  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-primary);
  color: var(--text-primary);
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

/* ── Session Bar ── */
.session-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.session-select {
  flex: 1;
  min-width: 0;
}

.session-new-btn {
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  flex-shrink: 0;
  background: var(--accent-soft);
  border: 1px solid rgba(78, 161, 243, 0.2);
  color: var(--accent);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all 0.15s;
}

.session-new-btn:hover {
  background: rgba(78, 161, 243, 0.2);
}

.session-del-btn {
  font-size: 12px;
  color: var(--text-muted);
  padding: 0 6px;
  height: 28px;
}

/* ── Messages Container ── */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 0;
}

/* ── Message Bubbles ── */
.message {
  padding: 12px 16px;
  border-radius: var(--radius-md);
  max-width: 85%;
  animation: msgIn 0.2s ease-out;
  line-height: 1.6;
}

.message.user {
  align-self: flex-end;
  background: var(--user-bubble);
  border-bottom-right-radius: 4px;
}

.message.agent {
  align-self: flex-start;
  background: var(--bg-tertiary);
  border-bottom-left-radius: 4px;
}

.message.system {
  align-self: center;
  background: transparent;
  font-size: 11px;
  max-width: 70%;
  color: var(--text-muted);
  text-align: center;
  padding: 4px 12px;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.message-role {
  font-weight: 600;
  letter-spacing: 0.02em;
}

.message-content {
  font-size: 13.5px;
  line-height: 1.65;
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

/* ── Processing ── */
.processing {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-secondary);
  align-self: flex-start;
  border-bottom-left-radius: 4px;
}

.processing-icon {
  font-size: 15px;
  color: var(--accent);
}

/* ── Pipeline Stream (LangChain) ── */
.pipeline-stream {
  align-self: stretch;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
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
  color: #555;
}

/* ── Thinking Stream (LangChain) ── */
.thinking-stream {
  align-self: stretch;
  background: rgba(78, 161, 243, 0.04);
  border: 1px solid rgba(78, 161, 243, 0.12);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.thinking-stream-title {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.05em;
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
  background: rgba(78, 201, 176, 0.08);
  border: 1px solid rgba(78, 201, 176, 0.2);
  border-radius: var(--radius-sm);
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
  padding: 6px 14px;
  font-size: 11px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.connection-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.connection-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thinking-toggle,
.precision-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-secondary);
  flex-shrink: 0;
  font-size: 11px;
}

.reconnect-btn {
  flex-shrink: 0;
  color: var(--accent);
  font-size: 11px;
  padding: 0 4px;
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
  padding: 14px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.input-container :deep(.el-textarea) {
  flex: 1;
}

.input-container :deep(.el-textarea__inner) {
  min-height: 80px;
  padding: 10px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 13.5px;
  font-family: inherit;
  border-radius: var(--radius-sm);
  resize: none;
  line-height: 1.6;
  transition: border-color 0.15s;
}

.input-container :deep(.el-textarea__inner):focus {
  outline: none;
  border-color: var(--accent);
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
  border-radius: var(--radius-sm);
  transition: all 0.15s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: #5ab1ff;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ================================================
   Precision Mode - Thought Blocks
   ================================================ */
.precision-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-self: stretch;
  background: transparent;
  border: none;
  padding: 0;
}

.thought-block {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: border-color 0.2s;
  animation: thoughtIn 0.3s ease-out;
}

.thought-block:hover {
  border-color: var(--border-strong);
}

.thought-block.status-running {
  border-left: 3px solid var(--accent);
}

.thought-block.status-done {
  border-left: 3px solid var(--success);
}

.thought-block.status-error {
  border-left: 3px solid var(--error);
}

.thought-block.status-skipped {
  opacity: 0.5;
}

@keyframes thoughtIn {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.thought-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.thought-header:hover {
  background: rgba(255, 255, 255, 0.02);
}

.thought-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  font-size: 15px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: var(--radius-sm);
}

.thought-icon .is-loading {
  color: var(--accent);
}

.thought-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.thought-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.thought-label {
  font-weight: 600;
  color: var(--text-primary);
}

.thought-status {
  font-size: 10px;
  color: var(--text-muted);
}

.thought-summary {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thought-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 12px;
}

.thought-content {
  padding: 0 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.thought-expand-enter-active,
.thought-expand-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.thought-expand-enter-from,
.thought-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.thought-expand-enter-to,
.thought-expand-leave-from {
  opacity: 1;
  max-height: 1200px;
}

.reasoning-section {
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.reasoning-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.15);
  border-bottom: 1px solid var(--border);
}

.reasoning-icon {
  font-size: 13px;
  color: var(--accent);
}

.reasoning-title {
  flex: 1;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.reasoning-badge {
  font-size: 10px;
  padding: 2px 6px;
  background: rgba(78, 161, 243, 0.12);
  color: var(--accent);
  border-radius: 3px;
}

.reasoning-badge.completed {
  background: rgba(78, 201, 176, 0.12);
  color: var(--success);
}

.reasoning-content {
  padding: 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', 'Consolas', 'Menlo', monospace;
  max-height: 380px;
  overflow-y: auto;
}

.reasoning-content :deep(p) {
  margin: 6px 0;
}

.reasoning-content :deep(ul),
.reasoning-content :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.reasoning-content :deep(li) {
  margin: 3px 0;
}

.reasoning-content :deep(code) {
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 5px;
  border-radius: 3px;
  color: #ce9178;
  font-size: 11px;
}

.reasoning-content :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  padding: 8px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  margin: 8px 0;
}

.reasoning-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.reasoning-content :deep(strong) {
  color: var(--success);
  font-weight: 600;
}

.reasoning-content :deep(em) {
  color: var(--warn);
}

.reasoning-content :deep(h1),
.reasoning-content :deep(h2),
.reasoning-content :deep(h3) {
  margin: 10px 0 6px;
  font-weight: 600;
  color: var(--text-primary);
}

.diagnostics-section {
  background: rgba(0, 0, 0, 0.15);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.diagnostics-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.15);
  border-bottom: 1px solid var(--border);
}

.diagnostics-icon {
  font-size: 13px;
  color: var(--warn);
}

.diagnostics-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.diagnostics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 6px;
  padding: 10px;
}

.diag-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 4px;
  transition: all 0.15s;
}

.diag-card:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--border-strong);
}

.diag-card-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.diag-card-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--success);
}

.diag-card-sub {
  font-size: 10px;
  color: var(--text-muted);
}

.metrics-card {
  background: linear-gradient(135deg, rgba(78, 161, 243, 0.04), rgba(78, 201, 176, 0.04));
  border: 1px solid rgba(78, 201, 176, 0.15);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.metrics-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 1px solid rgba(78, 201, 176, 0.1);
}

.metrics-icon {
  font-size: 15px;
  color: var(--success);
}

.metrics-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--success);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.metrics-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
}

.metric-row:last-child {
  border-bottom: none;
}

.metric-row .metric-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.metric-row .metric-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--success);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
</style>
