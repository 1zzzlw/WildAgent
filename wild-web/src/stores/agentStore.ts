/**
 * Agent 对话状态管理 Store
 *
 * 管理 AI Agent 会话和消息：
 * - session: 会话信息（session_id, messages, connected）
 * - sessions: 会话列表（Pinia + localStorage 持久化）
 * - connectionStatus: 详细连接状态
 * - pendingPatch: 待用户确认的 Patch
 * - isProcessing: Agent 是否正在处理
 * - currentStep: 当前执行步骤（用于显示进度）
 * - networkError: 最近一次网络错误信息
 *
 * 核心方法：
 * - addUserMessage() / addAgentMessage() / addSystemMessage(): 添加消息
 * - setPendingPatch(): 设置待确认的 Patch
 * - createSession() / switchSession() / removeSession(): 会话管理
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
import type { ChatMessage, AgentSession, ConnectionStatus, SessionInfo } from '../types/agent'
import type { ScenePatch } from '../types/scenePatch'

const STORAGE_KEY_SESSIONS = 'wild_sessions'
const STORAGE_KEY_CURRENT = 'wild_current_session'

function loadSessions(): SessionInfo[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_SESSIONS)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveSessions(sessions: SessionInfo[]) {
  try {
    localStorage.setItem(STORAGE_KEY_SESSIONS, JSON.stringify(sessions))
  } catch { /* ignore quota errors */ }
}

function loadCurrentSessionId(): string | null {
  return localStorage.getItem(STORAGE_KEY_CURRENT)
}

function saveCurrentSessionId(id: string) {
  localStorage.setItem(STORAGE_KEY_CURRENT, id)
}

export const useAgentStore = defineStore('agent', () => {
  // ── 会话列表（从 localStorage 恢复）──
  const sessions = ref<SessionInfo[]>(loadSessions())
  const currentSessionId = ref<string>(loadCurrentSessionId() || '')

  // ── 当前会话 ──
  const session = ref<AgentSession>({
    session_id: currentSessionId.value || `session_${Date.now()}`,
    messages: [],
    connected: false
  })

  // 初始化：如果还没有当前会话，创建一个
  if (!currentSessionId.value) {
    currentSessionId.value = session.value.session_id
    saveCurrentSessionId(currentSessionId.value)
  }

  /** 详细连接状态 */
  const connectionStatus = ref<ConnectionStatus>('disconnected')

  /** 最近一次网络错误信息，null 表示无错误 */
  const networkError = ref<string | null>(null)

  const pendingPatch = ref<ScenePatch | null>(null)
  const isProcessing = ref(false)
  const currentStep = ref<string>('')

  /** 校验流水线步骤列表（每次生成任务独立一组） */
  interface PipelineStep {
    label: string
    status: 'ok' | 'warn' | 'error' | 'skip'
  }
  const pipelineSteps = ref<PipelineStep[]>([])

  /** Blueprint 加载成功标记（用于 AIChatPanel 显示成功动画，5 秒后自动清除） */
  const blueprintLoaded = ref(false)
  const lastBlueprintPath = ref<string>('')

  const hasMessages = computed(() => session.value.messages.length > 0)
  const hasPendingPatch = computed(() => pendingPatch.value !== null)
  const isConnected = computed(() => connectionStatus.value === 'connected')

  // ── 消息管理 ──

  function addMessage(message: ChatMessage) {
    session.value.messages.push(message)
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
    }
    sessions.value.unshift(info)
    saveSessions(sessions.value)
    return id
  }

  function switchToSession(sessionId: string) {
    // 找到或创建会话记录
    let info = sessions.value.find(s => s.session_id === sessionId)
    if (!info) {
      info = {
        session_id: sessionId,
        name: '未命名建筑',
        created_at: Date.now(),
        updated_at: Date.now(),
        elements_count: 0,
      }
      sessions.value.unshift(info)
    }

    currentSessionId.value = sessionId
    saveCurrentSessionId(sessionId)
    saveSessions(sessions.value)

    // 重置当前会话状态（消息清空，蓝图由外部加载）
    session.value = {
      session_id: sessionId,
      messages: [],
      connected: session.value.connected,
    }
    pendingPatch.value = null
    pipelineSteps.value = []
    blueprintLoaded.value = false
  }

  function updateSessionInfo(sessionId: string, name: string, elementsCount: number) {
    const info = sessions.value.find(s => s.session_id === sessionId)
    if (info) {
      info.name = name
      info.elements_count = elementsCount
      info.updated_at = Date.now()
    } else {
      sessions.value.unshift({
        session_id: sessionId,
        name,
        created_at: Date.now(),
        updated_at: Date.now(),
        elements_count: elementsCount,
      })
    }
    saveSessions(sessions.value)
  }

  function removeSession(sessionId: string) {
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    saveSessions(sessions.value)

    if (currentSessionId.value === sessionId) {
      const next = sessions.value[0]
      if (next) {
        switchToSession(next.session_id)
      } else {
        // 无会话了，创建新的
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

  return {
    // 会话列表
    sessions,
    currentSessionId,
    createSession,
    switchToSession,
    updateSessionInfo,
    removeSession,
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
    addUserMessage,
    addAgentMessage,
    addSystemMessage,
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
  }
})
