/**
 * Agent 对话状态管理 Store
 *
 * 管理 AI Agent 会话和消息：
 * - session: 会话信息（session_id, messages, connected）
 * - connectionStatus: 详细连接状态
 * - pendingPatch: 待用户确认的 Patch
 * - isProcessing: Agent 是否正在处理
 * - currentStep: 当前执行步骤（用于显示进度）
 * - networkError: 最近一次网络错误信息
 *
 * 核心方法：
 * - addUserMessage() / addAgentMessage() / addSystemMessage(): 添加消息
 * - setPendingPatch(): 设置待确认的 Patch
 * - confirmPatch() / rejectPatch(): 确认或拒绝 Patch
 * - setConnectionStatus(): 设置 WebSocket 连接状态
 * - setNetworkError(): 设置网络错误信息
 *
 * 用于：
 * - 底部 AI 对话面板
 * - 显示用户和 Agent 的对话历史
 * - 显示 Agent 执行进度
 * - 处理需要用户确认的 Patch
 * - 显示网络连接状态与错误通知
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage, AgentSession, ConnectionStatus } from '../types/agent'
import type { ScenePatch } from '../types/scenePatch'

export const useAgentStore = defineStore('agent', () => {
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

  /** Blueprint 加载成功标记（用于 AIChatPanel 显示成功动画，5 秒后自动清除） */
  const blueprintLoaded = ref(false)
  const lastBlueprintPath = ref<string>('')

  const hasMessages = computed(() => session.value.messages.length > 0)
  const hasPendingPatch = computed(() => pendingPatch.value !== null)
  const isConnected = computed(() => connectionStatus.value === 'connected')

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

  /** 设置连接状态，同时同步旧版 boolean 字段 */
  function setConnectionStatus(status: ConnectionStatus) {
    connectionStatus.value = status
    session.value.connected = status === 'connected'
  }

  /** 设置网络错误信息 */
  function setNetworkError(error: string | null) {
    networkError.value = error
  }

  /** 清除网络错误 */
  function clearNetworkError() {
    networkError.value = null
  }

  function clearMessages() {
    session.value.messages = []
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

  /** 标记 Blueprint 已加载（触发成功动画） */
  function setBlueprintLoaded(path: string) {
    lastBlueprintPath.value = path
    blueprintLoaded.value = true
  }

  /** 清除 Blueprint 加载标记（成功动画消失） */
  function clearBlueprintLoaded() {
    blueprintLoaded.value = false
  }

  return {
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
  }
})
