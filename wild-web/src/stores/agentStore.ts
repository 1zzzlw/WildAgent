/**
 * Agent 对话状态管理 Store
 *
 * 管理 AI Agent 会话和消息：
 * - session: 会话信息（session_id, messages, connected）
 * - sessions: 从后端 storage/scenes 文件列表恢复的会话列表
 * - connectionStatus: 详细连接状态
 * - pendingPatch: 待用户确认的 Patch
 * - isProcessing: Agent 是否正在处理
 * - currentStep: 当前执行步骤（用于显示进度）
 * - networkError: 最近一次网络错误信息
 *
 * 消息持久化：
 * - 每次 addMessage 即时写入 localStorage（key: wild_msgs_{sessionId}）
 * - switchToSession 时自动从 localStorage 恢复消息
 * - 草稿会话存 localStorage（key: wild_draft_sessions）
 *
 * 核心方法：
 * - addUserMessage() / addAgentMessage() / addSystemMessage(): 添加消息
 * - setPendingPatch(): 设置待确认的 Patch
 * - createSession() / switchToSession() / removeSession(): 会话管理
 * - updateSessionInfo(): 从 blueprint 更新会话元数据
 *
 * 用于：
 * - 底部 AI 对话面板
 * - 会话切换
 * - 显示用户和 Agent 的对话历史
 * - 显示 Agent 执行进度
 * - 处理需要用户确认的 Patch
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  ChatMessage,
  AgentSession,
  ConnectionStatus,
  SessionInfo,
  GeneratingNode,
  NodeDiagnostic,
  ErrorDiagnostic,
  SessionMetrics,
  AgentTurn,
  AgentTurnStep,
} from '../types/agent'
import type { ScenePatch } from '../types/scenePatch'

type ThinkingStatus = 'idle' | 'thinking' | 'completed' | 'unsupported' | 'error'

const STORAGE_KEY_THINKING_MODE = 'wild_thinking_mode'
const STORAGE_KEY_PRECISION_MODE = 'wild_precision_mode'
const STORAGE_KEY_LAST_SESSION = 'wild_last_session'
const STORAGE_KEY_DRAFT_SESSIONS = 'wild_draft_sessions'
const MSG_STORAGE_PREFIX = 'wild_msgs_'
const TURN_STORAGE_PREFIX = 'wild_turns_'

function loadThinkingMode(): boolean {
  // 精密模式开启时强制启用思考，避免页面刷新后状态不一致
  if (loadPrecisionMode()) return true
  return localStorage.getItem(STORAGE_KEY_THINKING_MODE) === 'true'
}

function loadPrecisionMode(): boolean {
  return localStorage.getItem(STORAGE_KEY_PRECISION_MODE) === 'true'
}

// ── 消息持久化工具 ──

function saveMessagesToLocal(sessionId: string, messages: ChatMessage[]) {
  try {
    localStorage.setItem(MSG_STORAGE_PREFIX + sessionId, JSON.stringify(messages))
  } catch { /* localStorage 满或不可用，静默失败 */ }
}

function loadMessagesFromLocal(sessionId: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(MSG_STORAGE_PREFIX + sessionId)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function removeMessagesFromLocal(sessionId: string) {
  try {
    localStorage.removeItem(MSG_STORAGE_PREFIX + sessionId)
  } catch { /* ignore */ }
}

function saveTurnsToLocal(sessionId: string, turns: AgentTurn[]) {
  try {
    localStorage.setItem(TURN_STORAGE_PREFIX + sessionId, JSON.stringify(turns))
  } catch { /* ignore */ }
}

function loadTurnsFromLocal(sessionId: string): AgentTurn[] {
  try {
    const raw = localStorage.getItem(TURN_STORAGE_PREFIX + sessionId)
    return normalizeLoadedTurns(raw ? JSON.parse(raw) : [])
  } catch {
    return []
  }
}

function normalizeLoadedTurns(value: unknown, interruptRunning = true): AgentTurn[] {
  if (!Array.isArray(value)) return []
  const now = Date.now()
  return value
    .filter((turn): turn is AgentTurn => Boolean(
      turn && typeof turn === 'object' && typeof turn.request_id === 'string',
    ))
    .map(turn => {
    if (!interruptRunning || turn.status !== 'running') return turn
      return {
        ...turn,
        status: 'error' as const,
        completed_at: now,
        interruption_reason: '页面刷新或连接中断，任务状态无法继续恢复',
        thinking_status: 'error' as const,
        steps: (turn.steps || []).map(step => ({
          ...step,
          status: step.status === 'running' ? 'error' as const : step.status,
        })),
      }
    })
}

function removeTurnsFromLocal(sessionId: string) {
  try { localStorage.removeItem(TURN_STORAGE_PREFIX + sessionId) } catch { /* ignore */ }
}

function saveDraftSessions(sessions: SessionInfo[]) {
  try {
    const drafts = sessions.filter(s => s.status === 'draft')
    localStorage.setItem(STORAGE_KEY_DRAFT_SESSIONS, JSON.stringify(drafts))
  } catch { /* ignore */ }
}

function loadDraftSessions(): SessionInfo[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_DRAFT_SESSIONS)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveLastSession(sessionId: string) {
  try { localStorage.setItem(STORAGE_KEY_LAST_SESSION, sessionId) } catch { /* ignore */ }
}

function loadLastSession(): string | null {
  try { return localStorage.getItem(STORAGE_KEY_LAST_SESSION) } catch { return null }
}

/** 相对时间格式化（"刚刚" / "5分钟前" / "2小时前" / "3天前"） */
export function formatRelativeTime(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}分钟前`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}小时前`
  if (diff < 604800_000) return `${Math.floor(diff / 86400_000)}天前`
  return new Date(ts).toLocaleDateString('zh-CN')
}

export const useAgentStore = defineStore('agent', () => {
  // ── 会话列表（页面启动后由后端 storage/scenes 文件列表填充）──
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string>('')
  /** 每个会话独立保存执行轮次；运行事件不再依附于全局浮动面板。 */
  const turnsBySession = ref<Record<string, AgentTurn[]>>({})
  const currentTurns = computed(() => turnsBySession.value[currentSessionId.value] || [])

  // ── 当前会话 ──
  const session = ref<AgentSession>({
    session_id: `session_${Date.now()}`,
    messages: [],
    connected: false
  })

  /** 详细连接状态 */
  const connectionStatus = ref<ConnectionStatus>('disconnected')

  /** 最近一次网络错误信息，null 表示无错误 */
  const networkError = ref<string | null>(null)

  const pendingPatch = ref<ScenePatch | null>(null)
  const isProcessing = ref(false)
  const currentStep = ref<string>('')

  /** 用户偏好与模型接口实际返回的思考内容 */
  const thinkingMode = ref(loadThinkingMode())
  const thinkingContent = ref('')
  const thinkingStatus = ref<ThinkingStatus>('idle')
  const thinkingNotice = ref('')

  /** 精密模式：按节点分组的思考内容 */
  interface NodeThinking {
    node: string
    content: string
    status: 'thinking' | 'completed'
  }
  const nodeThinkingMap = ref<Map<string, NodeThinking>>(new Map())

  /** 校验流水线步骤列表（每次生成任务独立一组） */
  interface PipelineStep {
    label: string
    status: 'ok' | 'warn' | 'error' | 'skip'
  }
  const pipelineSteps = ref<PipelineStep[]>([])

  /** Blueprint 加载成功标记（用于 AIChatPanel 显示成功动画，5 秒后自动清除） */
  const blueprintLoaded = ref(false)
  const lastBlueprintPath = ref<string>('')

  /** 精密模式：LangGraph 分片并行 + 详细诊断日志 */
  const precisionMode = ref(loadPrecisionMode())

  /** 精密模式：节点生成进度列表 */
  const generatingNodes = ref<GeneratingNode[]>([])

  /** 精密模式：调试日志（节点诊断 RAG/LLM 数据） */
  const debugLogs = ref<Array<{ category: string; data: NodeDiagnostic | ErrorDiagnostic }>>([])

  /** 精密模式：最终性能汇总 */
  const sessionMetrics = ref<SessionMetrics | null>(null)

  const hasMessages = computed(() => session.value.messages.length > 0)
  const hasPendingPatch = computed(() => pendingPatch.value !== null)
  const isConnected = computed(() => connectionStatus.value === 'connected')

  // ── 消息管理 ──

  function addMessage(message: ChatMessage) {
    if (session.value.messages.some(existing => existing.id === message.id)) return
    session.value.messages.push(message)
    // 即时持久化到 localStorage
    saveMessagesToLocal(currentSessionId.value, session.value.messages)
  }

  function addMessageToSession(sessionId: string, message: ChatMessage) {
    if (sessionId === currentSessionId.value) {
      addMessage(message)
    } else {
      const messages = loadMessagesFromLocal(sessionId)
      if (!messages.some(existing => existing.id === message.id)) {
        messages.push(message)
        saveMessagesToLocal(sessionId, messages)
      }
    }

    const info = sessions.value.find(item => item.session_id === sessionId)
    if (info) {
      info.message_count = (info.message_count || 0) + 1
      info.updated_at = Date.now()
    }
  }

  function getMessagesForSession(sessionId: string): ChatMessage[] {
    return sessionId === currentSessionId.value
      ? session.value.messages
      : loadMessagesFromLocal(sessionId)
  }

  function mergeMessagesForSession(sessionId: string, serverMessages: ChatMessage[]) {
    const localMessages = getMessagesForSession(sessionId)
    const merged = new Map<string, ChatMessage>()
    for (const message of [...serverMessages, ...localMessages]) {
      if (message?.id) merged.set(message.id, message)
    }
    const messages = [...merged.values()].sort((a, b) => a.timestamp - b.timestamp)
    saveMessagesToLocal(sessionId, messages)
    if (sessionId === currentSessionId.value) session.value.messages = messages
  }

  function ensureTurns(sessionId: string): AgentTurn[] {
    if (!turnsBySession.value[sessionId]) {
      turnsBySession.value = {
        ...turnsBySession.value,
        [sessionId]: loadTurnsFromLocal(sessionId),
      }
    }
    return turnsBySession.value[sessionId]
  }

  function getTurnsForSession(sessionId: string): AgentTurn[] {
    return ensureTurns(sessionId)
  }

  function mergeTurnsForSession(sessionId: string, serverTurns: AgentTurn[]) {
    const merged = new Map<string, AgentTurn>()
    for (const turn of [...normalizeLoadedTurns(serverTurns, false), ...ensureTurns(sessionId)]) {
      merged.set(turn.request_id, turn)
    }
    const turns = [...merged.values()].sort((a, b) => a.started_at - b.started_at)
    turnsBySession.value = { ...turnsBySession.value, [sessionId]: turns }
    saveTurnsToLocal(sessionId, turns)
  }

  function persistTurns(sessionId: string) {
    saveTurnsToLocal(sessionId, ensureTurns(sessionId))
  }

  function findTurn(sessionId: string, requestId: string): AgentTurn | undefined {
    return ensureTurns(sessionId).find(turn => turn.request_id === requestId)
  }

  function startTurn(requestId: string, sessionId: string, content: string): AgentTurn {
    const message: ChatMessage = {
      id: `msg_${requestId}_user`,
      role: 'user',
      content,
      timestamp: Date.now(),
      request_id: requestId,
      turn_id: requestId,
    }
    addMessageToSession(sessionId, message)

    const turn: AgentTurn = {
      turn_id: requestId,
      request_id: requestId,
      session_id: sessionId,
      user_message_id: message.id,
      status: 'running',
      started_at: Date.now(),
      steps: [],
      validation_steps: [],
    }
    const turns = ensureTurns(sessionId)
    const existingIndex = turns.findIndex(item => item.request_id === requestId)
    if (existingIndex >= 0) turns.splice(existingIndex, 1, turn)
    else turns.push(turn)
    persistTurns(sessionId)
    return turn
  }

  function addAgentMessageForTurn(
    sessionId: string,
    requestId: string,
    content: string,
    patch?: ScenePatch,
  ) {
    addMessageToSession(sessionId, {
      id: `msg_${requestId}_${patch ? 'artifact' : 'agent'}`,
      role: 'agent',
      content,
      timestamp: Date.now(),
      patch,
      request_id: requestId,
      turn_id: requestId,
    })
  }

  function addSystemMessageForTurn(sessionId: string, requestId: string, content: string) {
    addMessageToSession(sessionId, {
      id: `msg_${requestId}_system_${Date.now()}`,
      role: 'system',
      content,
      timestamp: Date.now(),
      request_id: requestId,
      turn_id: requestId,
    })
  }

  function updateTurnStep(
    sessionId: string,
    requestId: string,
    step: Omit<AgentTurnStep, 'thinking'> & { thinking?: string },
  ) {
    const turn = findTurn(sessionId, requestId)
    if (!turn) return
    const existing = turn.steps.find(item => item.node === step.node)
    if (existing) {
      Object.assign(existing, step)
    } else {
      turn.steps.push({ ...step, thinking: step.thinking || '' })
    }
    turn.status = step.status === 'error' ? 'error' : turn.status
  }

  function appendTurnThinking(
    sessionId: string,
    requestId: string,
    node: string,
    delta: string,
    channel: 'reasoning' | 'progress' = 'reasoning',
  ) {
    const turn = findTurn(sessionId, requestId)
    if (!turn) return
    let step = turn.steps.find(item => item.node === node)
    if (!step) {
      step = {
        node,
        label: _resolveLabel(node),
        stage: 'generating',
        status: 'running',
        detail: '',
        thinking: '',
      }
      turn.steps.push(step)
    }
    step.thinking += delta
    step.thinking_channel = channel
  }

  function addTurnValidationStep(
    sessionId: string,
    requestId: string,
    label: string,
    status: 'ok' | 'warn' | 'error' | 'skip',
  ) {
    const turn = findTurn(sessionId, requestId)
    if (turn) turn.validation_steps.push({ label, status })
  }

  function clearTurnValidationSteps(sessionId: string, requestId: string) {
    const turn = findTurn(sessionId, requestId)
    if (turn) turn.validation_steps = []
  }

  function setTurnDiagnostic(
    sessionId: string,
    requestId: string,
    diagnostic: NodeDiagnostic,
  ) {
    const turn = findTurn(sessionId, requestId)
    if (!turn) return
    const node = diagnostic.node
    let step = turn.steps.find(item => item.node === node)
    if (!step) {
      step = {
        node,
        label: diagnostic.label || _resolveLabel(node),
        stage: 'generating',
        status: diagnostic.error ? 'error' : 'done',
        detail: '',
        thinking: '',
      }
      turn.steps.push(step)
    }
    step.diagnostic = diagnostic
  }

  function setTurnMetrics(sessionId: string, requestId: string, metrics: SessionMetrics) {
    const turn = findTurn(sessionId, requestId)
    if (turn) turn.metrics = metrics
  }

  function setTurnThinkingStatus(
    sessionId: string,
    requestId: string,
    status: 'thinking' | 'completed' | 'unsupported' | 'error',
    notice = '',
  ) {
    const turn = findTurn(sessionId, requestId)
    if (!turn) return
    turn.thinking_status = status
    turn.thinking_notice = notice
    if (status === 'error') turn.status = 'error'
    if (status !== 'thinking') persistTurns(sessionId)
  }

  function completeTurn(
    sessionId: string,
    requestId: string,
    status: 'completed' | 'error' = 'completed',
    interruptionReason?: string,
  ) {
    const turn = findTurn(sessionId, requestId)
    if (!turn) return
    turn.status = status
    turn.completed_at = Date.now()
    if (interruptionReason) turn.interruption_reason = interruptionReason
    turn.steps.forEach(step => {
      if (step.status === 'running') step.status = status === 'error' ? 'error' : 'done'
    })
    persistTurns(sessionId)
  }

  function getTurnForMessage(message: ChatMessage): AgentTurn | undefined {
    if (!message.turn_id) return undefined
    return currentTurns.value.find(turn => turn.turn_id === message.turn_id)
  }

  function addUserMessage(content: string) {
    addMessage({
      id: `msg_${Date.now()}`,
      role: 'user',
      content,
      timestamp: Date.now()
    })
  }

  function addAgentMessage(content: string, patch?: ScenePatch) {
    addMessage({
      id: `msg_${Date.now()}`,
      role: 'agent',
      content,
      timestamp: Date.now(),
      patch
    })
  }

  function addSystemMessage(content: string) {
    addMessage({
      id: `msg_${Date.now()}`,
      role: 'system',
      content,
      timestamp: Date.now()
    })
  }

  function setProcessing(processing: boolean, step?: string) {
    isProcessing.value = processing
    if (step !== undefined) {
      currentStep.value = step
    }
    if (processing && !step) {
      pipelineSteps.value = []
    }
  }

  function addPipelineStep(label: string, status: 'ok' | 'warn' | 'error' | 'skip') {
    pipelineSteps.value.push({ label, status })
  }

  function clearPipelineSteps() {
    pipelineSteps.value = []
  }

  function setThinkingMode(enabled: boolean) {
    thinkingMode.value = enabled
    localStorage.setItem(STORAGE_KEY_THINKING_MODE, String(enabled))
    if (!enabled) {
      clearThinkingState()
    }
  }

  function appendThinkingContent(delta: string, nodeName?: string) {
    if (precisionMode.value && nodeName) {
      // 精密模式：按节点分组存储
      const existing = nodeThinkingMap.value.get(nodeName)
      if (existing) {
        existing.content += delta
        existing.status = 'thinking'
      } else {
        nodeThinkingMap.value.set(nodeName, {
          node: nodeName,
          content: delta,
          status: 'thinking'
        })
      }
      // 触发响应式更新
      nodeThinkingMap.value = new Map(nodeThinkingMap.value)
    } else {
      // 非精密模式：累加到单一内容
      thinkingContent.value += delta
    }
  }

  function completeNodeThinking(nodeName: string) {
    const thinking = nodeThinkingMap.value.get(nodeName)
    if (thinking) {
      thinking.status = 'completed'
      nodeThinkingMap.value = new Map(nodeThinkingMap.value)
    }
  }

  function completeAllGeneratingNodes() {
    generatingNodes.value = generatingNodes.value.map(node => {
      if (node.status === 'running') {
        return { ...node, status: 'done' }
      }
      return node
    })
    nodeThinkingMap.value.forEach((thinking, node) => {
      if (thinking.status === 'thinking') {
        thinking.status = 'completed'
      }
    })
    nodeThinkingMap.value = new Map(nodeThinkingMap.value)
  }

  function setThinkingStatus(status: Exclude<ThinkingStatus, 'idle'>, content = '') {
    thinkingStatus.value = status
    thinkingNotice.value = content
  }

  function clearThinkingState() {
    thinkingContent.value = ''
    thinkingStatus.value = 'idle'
    thinkingNotice.value = ''
    nodeThinkingMap.value.clear()
  }

  function setPendingPatch(patch: ScenePatch | null) {
    pendingPatch.value = patch
  }

  function confirmPatch() {
    pendingPatch.value = null
  }

  function rejectPatch() {
    pendingPatch.value = null
  }

  function setConnectionStatus(status: ConnectionStatus) {
    connectionStatus.value = status
    session.value.connected = status === 'connected'
  }

  function setNetworkError(error: string | null) {
    networkError.value = error
  }

  function clearNetworkError() {
    networkError.value = null
  }

  function clearMessages() {
    session.value.messages = []
    saveMessagesToLocal(currentSessionId.value, [])
    turnsBySession.value = { ...turnsBySession.value, [currentSessionId.value]: [] }
    saveTurnsToLocal(currentSessionId.value, [])
  }

  // ── 会话扩展操作 ──

  function renameSession(sessionId: string, newName: string) {
    const info = sessions.value.find(s => s.session_id === sessionId)
    if (info) {
      info.name = newName
      info.updated_at = Date.now()
    }
  }

  function setSessionGenerating(sessionId: string) {
    const info = sessions.value.find(s => s.session_id === sessionId)
    if (info) {
      info.status = 'generating'
    }
  }

  function setSessionSaved(sessionId: string) {
    const info = sessions.value.find(s => s.session_id === sessionId)
    if (info) {
      info.status = 'saved'
    }
  }

  /** 用服务器场景文件摘要整体替换会话列表（保留本地草稿）。 */
  function replaceSessions(serverSessions: SessionInfo[]) {
    // 保留本地草稿（未同步到服务端的会话）
    const localDrafts = sessions.value.filter(s => s.status === 'draft' && !serverSessions.find(ss => ss.session_id === s.session_id))
    sessions.value = [...serverSessions, ...localDrafts]
    saveDraftSessions(sessions.value)
  }

  // ── 会话管理 ──

  function createSession(name?: string): string {
    const id = `session_${Date.now()}`
    const info: SessionInfo = {
      session_id: id,
      name: name || '新建筑',
      created_at: Date.now(),
      updated_at: Date.now(),
      elements_count: 0,
      status: 'draft',
    }
    sessions.value.unshift(info)
    saveDraftSessions(sessions.value)
    return id
  }

  function switchToSession(sessionId: string) {
    // 1. 保存当前会话消息到 localStorage（防止丢失）
    if (currentSessionId.value) {
      saveMessagesToLocal(currentSessionId.value, session.value.messages)
    }

    // 2. 找到或创建会话记录
    let info = sessions.value.find(s => s.session_id === sessionId)
    if (!info) {
      info = {
        session_id: sessionId,
        name: '未命名建筑',
        created_at: Date.now(),
        updated_at: Date.now(),
        elements_count: 0,
        status: 'draft',
      }
      sessions.value.unshift(info)
    }

    // 3. 切换 session_id
    currentSessionId.value = sessionId
    saveLastSession(sessionId)
    ensureTurns(sessionId)

    // 4. 从 localStorage 恢复目标会话消息（而不是丢弃！）
    const savedMessages = loadMessagesFromLocal(sessionId)
    session.value = {
      session_id: sessionId,
      messages: savedMessages,
      connected: session.value.connected,
    }

    // 5. 清除运行时状态（思考/进度——这些不应持久化）
    pendingPatch.value = null
    pipelineSteps.value = []
    clearThinkingState()
    clearPrecisionState()
    blueprintLoaded.value = false
  }

  function updateSessionInfo(sessionId: string, name: string, elementsCount: number, componentsCount?: number, buildingType?: string) {
    const info = sessions.value.find(s => s.session_id === sessionId)
    if (info) {
      info.name = name
      info.elements_count = elementsCount
      if (componentsCount !== undefined) info.components_count = componentsCount
      if (buildingType) info.building_type = buildingType
      info.updated_at = Date.now()
      // 有蓝图保存后标记为已保存
      if (elementsCount > 0) info.status = 'saved'
    } else {
      sessions.value.unshift({
        session_id: sessionId,
        name,
        created_at: Date.now(),
        updated_at: Date.now(),
        elements_count: elementsCount,
        components_count: componentsCount,
        building_type: buildingType,
        status: elementsCount > 0 ? 'saved' : 'draft',
      })
    }
  }

  function removeSession(sessionId: string) {
    // 清理 localStorage 中的消息
    removeMessagesFromLocal(sessionId)
    removeTurnsFromLocal(sessionId)
    const nextTurns = { ...turnsBySession.value }
    delete nextTurns[sessionId]
    turnsBySession.value = nextTurns

    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    saveDraftSessions(sessions.value)

    if (currentSessionId.value === sessionId) {
      // 优先跳转到最近使用的会话，否则第一个，否则新建
      const lastId = loadLastSession()
      const next = sessions.value.find(s => s.session_id === lastId && s.session_id !== sessionId)
        || sessions.value[0]
      if (next) {
        switchToSession(next.session_id)
      } else {
        const newId = createSession()
        switchToSession(newId)
      }
    }
  }

  function resetSession() {
    session.value = {
      session_id: `session_${Date.now()}`,
      messages: [],
      connected: false
    }
    connectionStatus.value = 'disconnected'
    networkError.value = null
    pendingPatch.value = null
    isProcessing.value = false
    currentStep.value = ''
    turnsBySession.value = {}
    clearThinkingState()
    blueprintLoaded.value = false
    lastBlueprintPath.value = ''
  }

  function setBlueprintLoaded(path: string) {
    lastBlueprintPath.value = path
    blueprintLoaded.value = true
  }

  function clearBlueprintLoaded() {
    blueprintLoaded.value = false
  }

  // ── 精密模式 ──

  function setPrecisionMode(enabled: boolean) {
    precisionMode.value = enabled
    localStorage.setItem(STORAGE_KEY_PRECISION_MODE, String(enabled))
    if (!enabled) {
      clearPrecisionState()
    }
  }

  function updateGeneratingNode(
    nodeName: string,
    status: GeneratingNode['status'],
    detail: string,
    label = _resolveLabel(nodeName),
  ) {

    const existing = generatingNodes.value.find(n => n.name === nodeName)
    if (existing) {
      existing.status = status
      existing.detail = detail
      existing.label = label
    } else {
      generatingNodes.value.push({ name: nodeName, label, status, detail })
    }
  }

  // 节点名→中文标签（与后端 _node_label 对应）
  const _COMP_LABELS: Record<string, string> = {
    door: '门', window: '窗', roof: '屋顶',
    railing: '栏杆', canopy: '雨棚', balcony: '阳台',
    light: '灯具', ramp: '坡道', bay_window: '凸窗',
    cornice: '檐口', chimney: '烟囱',
  }
  const _NODE_LABELS: Record<string, string> = {
    skeleton: '骨架',
    merge: '合并', final_validate: '最终校验', callback: '修正',
  }
  function _resolveLabel(nodeName: string): string {
    if (_NODE_LABELS[nodeName]) return _NODE_LABELS[nodeName]
    for (const [ct, cl] of Object.entries(_COMP_LABELS)) {
      if (nodeName === `${ct}_gen`) return `${cl}·生成`
      if (nodeName === `${ct}_val`) return `${cl}·校验`
    }
    return nodeName
  }

  function addDebugLog(category: string, data: any) {
    debugLogs.value.push({ category, data })
  }

  function setSessionMetrics(metrics: SessionMetrics) {
    sessionMetrics.value = metrics
  }

  function clearPrecisionState() {
    generatingNodes.value = []
    nodeThinkingMap.value.clear()
    debugLogs.value = []
    sessionMetrics.value = null
  }

  function clearDebugLogs() {
    debugLogs.value = []
    sessionMetrics.value = null
  }

  return {
    // 会话列表
    sessions,
    currentSessionId,
    turnsBySession,
    currentTurns,
    replaceSessions,
    createSession,
    switchToSession,
    updateSessionInfo,
    removeSession,
    renameSession,
    setSessionGenerating,
    setSessionSaved,
    // 原有
    session,
    connectionStatus,
    networkError,
    pendingPatch,
    isProcessing,
    currentStep,
    hasMessages,
    hasPendingPatch,
    isConnected,
    addMessage,
    addMessageToSession,
    getMessagesForSession,
    getTurnsForSession,
    mergeMessagesForSession,
    mergeTurnsForSession,
    addUserMessage,
    addAgentMessage,
    addSystemMessage,
    startTurn,
    addAgentMessageForTurn,
    addSystemMessageForTurn,
    updateTurnStep,
    appendTurnThinking,
    addTurnValidationStep,
    clearTurnValidationSteps,
    setTurnDiagnostic,
    setTurnMetrics,
    setTurnThinkingStatus,
    completeTurn,
    getTurnForMessage,
    setProcessing,
    setPendingPatch,
    confirmPatch,
    rejectPatch,
    setConnectionStatus,
    setNetworkError,
    clearNetworkError,
    clearMessages,
    resetSession,
    blueprintLoaded,
    lastBlueprintPath,
    setBlueprintLoaded,
    clearBlueprintLoaded,
    pipelineSteps,
    addPipelineStep,
    clearPipelineSteps,
    thinkingMode,
    thinkingContent,
    thinkingStatus,
    thinkingNotice,
    nodeThinkingMap,
    setThinkingMode,
    appendThinkingContent,
    completeNodeThinking,
    completeAllGeneratingNodes,
    setThinkingStatus,
    clearThinkingState,
    // 精密模式
    precisionMode,
    generatingNodes,
    debugLogs,
    sessionMetrics,
    setPrecisionMode,
    updateGeneratingNode,
    addDebugLog,
    setSessionMetrics,
    clearPrecisionState,
    clearDebugLogs,
  }
})
