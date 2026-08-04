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
import type {
  ChatMessage,
  AgentSession,
  ConnectionStatus,
  SessionInfo,
  GeneratingNode,
  NodeDiagnostic,
  ErrorDiagnostic,
  SessionMetrics,
} from '../types/agent'
import type { ScenePatch } from '../types/scenePatch'

type ThinkingStatus = 'idle' | 'thinking' | 'completed' | 'unsupported' | 'error'

const STORAGE_KEY_THINKING_MODE = 'wild_thinking_mode'
const STORAGE_KEY_PRECISION_MODE = 'wild_precision_mode'

function loadThinkingMode(): boolean {
  return localStorage.getItem(STORAGE_KEY_THINKING_MODE) === 'true'
}

function loadPrecisionMode(): boolean {
  return localStorage.getItem(STORAGE_KEY_PRECISION_MODE) === 'true'
}

export const useAgentStore = defineStore('agent', () => {
  // ── 会话列表（页面启动后由后端 storage/scenes 文件列表填充）──
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string>('')

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
  }

  // ── 会话管理 ──

  /** 用服务器场景文件摘要整体替换会话列表。 */
  function replaceSessions(serverSessions: SessionInfo[]) {
    sessions.value = serverSessions
  }

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

    // 重置当前会话状态（消息清空，蓝图由外部加载）
    session.value = {
      session_id: sessionId,
      messages: [],
      connected: session.value.connected,
    }
    pendingPatch.value = null
    pipelineSteps.value = []
    clearThinkingState()
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
  }

  function removeSession(sessionId: string) {
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)

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

  function updateGeneratingNode(content: string) {
    // 新格式: "{node_name}:{status}:{detail}"
    // 示例: "skeleton:done:骨架 25构件 | RAG 18000字 200ms | LLM 3000字 15000ms | 思考 3421字"
    //       "door:done:门 2个 | RAG 500字 50ms | LLM 800字 3000ms | 思考 856字"
    //       "chimney:skipped:烟囱 跳过 (用户未提及)"
    const parts = content.split(':')
    let nodeName = 'unknown'
    let status: GeneratingNode['status'] = 'running'
    let detail = content

    if (parts.length >= 3) {
      nodeName = parts[0]
      status = (parts[1] as GeneratingNode['status']) || 'running'
      detail = parts.slice(2).join(':')
    } else if (content.includes('✅')) {
      status = 'done'
    } else if (content.includes('❌')) {
      status = 'error'
    } else if (content.includes('⏭️')) {
      status = 'skipped'
    }

    const label = _NODE_LABELS[nodeName] || nodeName

    const existing = generatingNodes.value.find(n => n.name === nodeName)
    if (existing) {
      existing.status = status
      existing.detail = detail
      existing.label = label
    } else {
      generatingNodes.value.push({ name: nodeName, label, status, detail })
    }
  }

  // 节点名→中文标签（与后端 _NODE_LABELS 对应）
  const _NODE_LABELS: Record<string, string> = {
    skeleton: '骨架',
    door: '门', window: '窗', roof: '屋顶',
    railing: '栏杆', canopy: '雨棚', balcony: '阳台',
    light: '灯具', ramp: '坡道', bay_window: '凸窗',
    cornice: '檐口', chimney: '烟囱',
    merge: '合并', validate: '校验', callback: '修正',
  }

  function addDebugLog(category: string, data: any) {
    debugLogs.value.push({ category, data })
  }

  function setSessionMetrics(metrics: SessionMetrics) {
    sessionMetrics.value = metrics
  }

  function clearPrecisionState() {
    generatingNodes.value = []
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
    replaceSessions,
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
    thinkingMode,
    thinkingContent,
    thinkingStatus,
    thinkingNotice,
    nodeThinkingMap,
    setThinkingMode,
    appendThinkingContent,
    completeNodeThinking,
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
