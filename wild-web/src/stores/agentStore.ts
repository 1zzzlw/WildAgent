/**
 * Agent 对话状态管理 Store
 * 
 * 管理 AI Agent 会话和消息：
 * - session: 会话信息（session_id, messages, connected）
 * - pendingPatch: 待用户确认的 Patch
 * - isProcessing: Agent 是否正在处理
 * - currentStep: 当前执行步骤（用于显示进度）
 * 
 * 核心方法：
 * - addUserMessage() / addAgentMessage() / addSystemMessage(): 添加消息
 * - setPendingPatch(): 设置待确认的 Patch
 * - confirmPatch() / rejectPatch(): 确认或拒绝 Patch
 * - setConnected(): 设置 WebSocket 连接状态
 * 
 * 用于：
 * - 底部 AI 对话面板
 * - 显示用户和 Agent 的对话历史
 * - 显示 Agent 执行进度
 * - 处理需要用户确认的 Patch
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage, AgentSession } from '../types/agent'
import type { ScenePatch } from '../types/scenePatch'

export const useAgentStore = defineStore('agent', () => {
  const session = ref<AgentSession>({
    session_id: `session_${Date.now()}`,
    messages: [],
    connected: false
  })

  const pendingPatch = ref<ScenePatch | null>(null)
  const isProcessing = ref(false)
  const currentStep = ref<string>('')

  const hasMessages = computed(() => session.value.messages.length > 0)
  const hasPendingPatch = computed(() => pendingPatch.value !== null)

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

  function setConnected(connected: boolean) {
    session.value.connected = connected
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
    pendingPatch.value = null
    isProcessing.value = false
    currentStep.value = ''
  }

  return {
    session,
    pendingPatch,
    isProcessing,
    currentStep,
    hasMessages,
    hasPendingPatch,
    addMessage,
    addUserMessage,
    addAgentMessage,
    addSystemMessage,
    setProcessing,
    setPendingPatch,
    confirmPatch,
    rejectPatch,
    setConnected,
    clearMessages,
    resetSession
  }
})
