/**
 * Agent WebSocket 通信桥接
 *
 * 管理前后端 WebSocket 连接和消息收发：
 *
 * 核心功能：
 * - connect(): 连接到 Agent WebSocket 服务
 * - disconnect(): 断开连接
 * - sendUserMessage(): 发送用户消息 + 场景上下文
 * - handleMessage(): 处理后端返回的消息
 *
 * 重连机制：
 * - 指数退避（1s → 2s → 4s → 8s → 16s → 30s 上限）
 * - ±25% 随机抖动避免惊群效应
 * - 最大重试 10 次，超出后停止
 * - 连接成功后重置重试计数
 *
 * 心跳机制：
 * - 每 15 秒发送 ping
 * - 10 秒内未收到 pong 则判定连接断开
 * - 主动关闭并触发重连
 * - 监听页面可见性变化：恢复可见时立即检测连接状态并补发心跳，避免浏览器后台节流导致误断连
 *
 * 连接状态：
 * - connecting / connected / disconnected / reconnecting
 * - 通过 agentStore 暴露给 UI 层
 *
 * 消息处理：
 * - agent_step: 更新执行步骤显示
 * - thinking_delta / thinking_status: 追加模型真实思考内容并更新状态
 * - patch_proposal: 设置待确认 Patch
 * - agent_reply: 添加 Agent 回复消息
 * - error: 显示错误信息
 * - network_error: 后端心跳超时通知 → 显示网络错误提示
 *
 * 用于：
 * - AI 对话面板的实时通信
 * - Agent 流式响应显示
 * - Patch 提案推送
 * 
 */

import { useAgentStore } from '../stores/agentStore'
import { useSceneStore } from '../stores/sceneStore'
import { useSelectionStore } from '../stores/selectionStore'
import { usePresenceStore } from '../extensions/presence/store'
import { PRESENCE_VISITOR_NAME_CHANGED_EVENT } from '../extensions/presence/types'
import { generateSceneSummary } from '../wild/sceneSummary'
import { AGENT_PROTOCOL_VERSION, createUserMessageRequest } from './protocol'
import type { AgentMessage, AgentReplyResponse, AgentTurn, BlueprintGeneratedResponse, ChatMessage } from '../types/agent'
import type { Blueprint } from '../types/blueprint'

/** 重连配置 */
const RECONNECT_CONFIG = {
  initialDelay: 1000,    // 初始重连延迟 1s
  maxDelay: 30000,       // 最大重连延迟 30s
  factor: 2,             // 指数退避因子
  jitter: 0.25,          // ±25% 随机抖动
  maxAttempts: 10        // 最大重试次数
} as const

/** 心跳配置 */
const HEARTBEAT_CONFIG = {
  interval: 15000,       // ping 间隔 15s
  timeout: 10000         // pong 超时 10s
} as const

/**
 * 将 meta.name 转换为安全的文件名片段（与后端 _safe_name_slug 对齐）。
 * 保留中文、字母、数字，其余替换为 _，最长 40 字符。
 */
function safeNameSlug(name: string): string {
  return name
    .replace(/[^\w\u4e00-\u9fff]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 40)
}

/**
 * 构建蓝图保存的相对路径：YYYY-MM-DD/{sessionId}_{nameSlug}.wild
 * 格式与后端存储结构对应，方便按日期浏览文件。
 *
 * 注意：日期必须使用浏览器本地时间（与后端 datetime.date.today() 对齐）。
 * 用 toISOString() 取的是 UTC 日期，在 UTC+8 凌晨 0-8 点会落到前一天，
 * 导致前端 PUT 与后端 GET/DELETE 的路径日期目录不一致。
 */
function buildSceneRelPath(sessionId: string, blueprint: Record<string, unknown>): string {
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`  // 本地 YYYY-MM-DD
  const meta = blueprint.meta as Record<string, unknown> | undefined
  const name = typeof meta?.name === 'string' ? meta.name : ''
  const slug = safeNameSlug(name)
  const filename = slug ? `${sessionId}_${slug}.wild` : `${sessionId}.wild`
  return `${today}/${filename}`
}

export class AgentBridge {
  private ws: WebSocket | null = null
  private url: string

  // 重连状态
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectDelay: number = RECONNECT_CONFIG.initialDelay
  private reconnectAttempts: number = 0

  // 心跳状态
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private pongTimeoutTimer: ReturnType<typeof setTimeout> | null = null

  // 标记是否为主动断开（不触发重连）
  private manualDisconnect: boolean = false

  // 页面可见性变化处理（解决浏览器后台标签页节流 setInterval 导致心跳中断的问题）
  private visibilityChangeHandler: (() => void) | null = null
  private lastHiddenTime: number = 0
  private visitorNameChangeHandler: EventListener | null = null
  /** 将迟到事件路由回发起请求的会话，避免切换会话后串消息。 */
  private requestContexts = new Map<string, {
    sessionId: string
    turnId: string
    durable: boolean
  }>()
  /** 每个持久化请求最后处理的关键事件序号，用于补发去重。 */
  private lastEventSequences = new Map<string, number>()
  /** 产物加载与正式回复可能紧邻到达；回复必须等产物处理完再落盘。 */
  private artifactTasks = new Map<string, Promise<boolean>>()
  /** 同一会话的 Turn 快照必须串行提交，避免旧的 running 覆盖新的 completed。 */
  private turnSyncQueues = new Map<string, Promise<boolean>>()


  constructor(url?: string) {
    this.url = url ?? this.buildDefaultUrl()
  }

  /** 根据当前页面地址生成 WebSocket URL，通过 nginx /ws/ 代理 */
  private buildDefaultUrl(): string {
    if (typeof window === 'undefined') return 'ws://localhost/ws/agent'
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${wsProtocol}//${window.location.host}/ws/agent`
  }

  /** Presence 展示名只作为连接参数，不参与 Agent 请求。 */
  private buildConnectionUrl(visitorName: string): string {
    if (!visitorName) return this.url
    const separator = this.url.includes('?') ? '&' : '?'
    return `${this.url}${separator}visitor_name=${encodeURIComponent(visitorName)}`
  }

  /** 初始化连接 */
  connect() {
    const agentStore = useAgentStore()
    const presenceStore = usePresenceStore()

    this.manualDisconnect = false
    presenceStore.setConnectionStatus('connecting')
    agentStore.setConnectionStatus('connecting')

    try {
      this.setupVisitorNameListener()
      this.ws = new WebSocket(this.buildConnectionUrl(presenceStore.visitorName))

      this.ws.onopen = () => {
        console.log('[AgentBridge] WebSocket 已连接')
        presenceStore.setConnectionStatus('connected')
        agentStore.setConnectionStatus('connected')
        agentStore.clearNetworkError()

        // 重置重连计数器
        this.reconnectAttempts = 0
        this.reconnectDelay = RECONNECT_CONFIG.initialDelay

        // 启动心跳 + 页面可见性监听
        this.startHeartbeat()
        this.setupVisibilityListener()
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer)
          this.reconnectTimer = null
        }
        this.resumeActiveGenerations()
      }

      this.ws.onmessage = (event) => {
        try {
          const message: AgentMessage = JSON.parse(event.data)

          if (message.protocol_version !== AGENT_PROTOCOL_VERSION) {
            agentStore.addSystemMessage(
              `Agent 协议版本不兼容：收到 ${message.protocol_version || 'unknown'}，当前为 ${AGENT_PROTOCOL_VERSION}`,
            )
            return
          }

          // 优先处理心跳响应（不进入业务逻辑）
          if (message.type === 'pong') {
            this.handlePong(message.timestamp)
            return
          }

          if (message.type === 'network_error') {
            this.handleNetworkError(message.error)
            return
          }

          if (
            'request_id' in message
            && typeof message.request_id === 'string'
            && 'event_seq' in message
            && typeof message.event_seq === 'number'
          ) {
            const lastSequence = this.lastEventSequences.get(message.request_id) || 0
            if (message.event_seq <= lastSequence) return
            this.lastEventSequences.set(message.request_id, message.event_seq)
          }

          this.handleMessage(message)
        } catch (error) {
          console.error('[AgentBridge] 解析消息失败', error)
        }
      }

      this.ws.onerror = () => {
        console.error('[AgentBridge] WebSocket 错误')
      }

      this.ws.onclose = () => {
        console.log('[AgentBridge] WebSocket 已断开')
        this.stopHeartbeat()
        presenceStore.setConnectionStatus(
          this.manualDisconnect ? 'disconnected' : 'reconnecting',
        )
        this.interruptNonDurableTurns('Agent 连接中断，请重新发送请求')

        if (!this.manualDisconnect) {
          // 不在此处设 disconnected，交给 scheduleReconnect 统一管理状态
          this.scheduleReconnect()
        } else {
          agentStore.setConnectionStatus('disconnected')
        }
      }
    } catch (error) {
      console.error('[AgentBridge] 连接失败', error)
      if (!this.manualDisconnect) {
        this.scheduleReconnect()
      } else {
        agentStore.setConnectionStatus('disconnected')
      }
    }
  }

  /** 监听页面可见性变化 —— 解决浏览器后台标签页节流 setInterval 导致心跳中断 */
  private setupVisibilityListener() {
    this.removeVisibilityListener()

    this.visibilityChangeHandler = () => {
      if (document.hidden) {
        this.lastHiddenTime = Date.now()
        console.log('[AgentBridge] 页面隐藏，记录时间')
      } else {
        const hiddenDuration = Date.now() - this.lastHiddenTime
        console.log(`[AgentBridge] 页面恢复可见，隐藏时长: ${hiddenDuration}ms`)

        // 如果隐藏时间超过心跳间隔，立即检测连接状态
        if (hiddenDuration > HEARTBEAT_CONFIG.interval) {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            // 连接看起来还在，发一个 ping 确认
            this.sendPing()
            // 重置心跳定时器，避免旧定时器干扰
            this.stopHeartbeat()
            this.startHeartbeat()
            console.log('[AgentBridge] 页面恢复后已重置心跳')
          } else if (!this.manualDisconnect) {
            // 连接已断开，立即重连（不等定时器）
            console.log('[AgentBridge] 页面恢复后发现连接断开，立即重连')
            this.reconnectAttempts = 0
            this.reconnectDelay = RECONNECT_CONFIG.initialDelay
            this.connect()
          }
        }
      }
    }

    document.addEventListener('visibilitychange', this.visibilityChangeHandler)
  }

  /** 移除页面可见性监听 */
  private removeVisibilityListener() {
    if (this.visibilityChangeHandler) {
      document.removeEventListener('visibilitychange', this.visibilityChangeHandler)
      this.visibilityChangeHandler = null
    }
  }

  /** 名称修改后只更新 Presence 快照，不重建 Agent 会话。 */
  private setupVisitorNameListener() {
    this.removeVisitorNameListener()
    this.visitorNameChangeHandler = (event: Event) => {
      const visitorName = (event as CustomEvent<unknown>).detail
      if (
        typeof visitorName !== 'string'
        || !this.ws
        || this.ws.readyState !== WebSocket.OPEN
      ) return
      this.ws.send(JSON.stringify({
        protocol_version: AGENT_PROTOCOL_VERSION,
        type: 'presence_identify',
        display_name: visitorName,
      }))
    }
    window.addEventListener(
      PRESENCE_VISITOR_NAME_CHANGED_EVENT,
      this.visitorNameChangeHandler,
    )
  }

  private removeVisitorNameListener() {
    if (!this.visitorNameChangeHandler) return
    window.removeEventListener(
      PRESENCE_VISITOR_NAME_CHANGED_EVENT,
      this.visitorNameChangeHandler,
    )
    this.visitorNameChangeHandler = null
  }

  /** 断开连接（主动，不触发重连） */
  disconnect() {
    this.manualDisconnect = true

    // 清除所有定时器 + 页面可见性监听
    this.clearAllTimers()
    this.removeVisibilityListener()
    this.removeVisitorNameListener()

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    const agentStore = useAgentStore()
    const presenceStore = usePresenceStore()
    agentStore.setConnectionStatus('disconnected')
    presenceStore.setConnectionStatus('disconnected')
    agentStore.clearNetworkError()
  }

  /** 发送用户消息 */
  sendUserMessage(message: string): string | null {
    const agentStore = useAgentStore()
    const sceneStore = useSceneStore()
    const selectionStore = useSelectionStore()

    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      agentStore.addSystemMessage('未连接到 Agent 服务')
      return null
    }

    const pendingReview = [...agentStore.currentTurns]
      .reverse()
      .find(turn => turn.status === 'waiting_review')
    if (pendingReview) {
      if (pendingReview.execution_plan_review_status === 'pending') {
        return this.submitExecutionPlanReview(pendingReview.request_id, 'revise', message)
      }
      if (pendingReview.style_review_status === 'pending') {
        return this.submitStyleReview(pendingReview.request_id, 'revise', '', message)
      }
      if (pendingReview.floor_plan_review_status === 'pending') {
        return this.submitFloorPlanReview(pendingReview.request_id, 'revise', message)
      }
    }

    const activePlanTurn = [...agentStore.currentTurns]
      .reverse()
      .find(turn => turn.status === 'running' && turn.plan_mode && turn.execution_plan)
    if (activePlanTurn) {
      return this.submitExecutionFeedback(activePlanTurn.request_id, message)
    }

    if (!sceneStore.document) {
      agentStore.addSystemMessage('无场景文档')
      return null
    }

    const sceneSummary = generateSceneSummary(sceneStore.document.blueprint)
    const selection = [...selectionStore.selectedIds]
    const recentMessages: Array<{ role: 'user' | 'assistant'; content: string }> = agentStore
      .getMessagesForSession(agentStore.session.session_id)
      .filter(item => item.role === 'user' || item.role === 'agent')
      .slice(-4)
      .map(item => ({
        role: item.role === 'agent' ? 'assistant' : 'user',
        content: item.content.slice(0, 500),
      }))

    const request = createUserMessageRequest(
      message,
      agentStore.session.session_id,
      sceneStore.document.id,
      sceneStore.document.revision,
      sceneSummary,
      selection,
      sceneStore.document.blueprint as Record<string, unknown>,
      agentStore.thinkingMode,
      agentStore.precisionMode,
      agentStore.proceduralMaterialsEnabled,
      agentStore.planMode,
      recentMessages,
    )

    agentStore.clearPipelineSteps()
    agentStore.clearThinkingState()
    agentStore.clearPrecisionState()
    this.requestContexts.set(request.request_id, {
      sessionId: request.session_id,
      turnId: request.request_id,
      // 快速与精密模式都由服务端持久图托管；断线后都应恢复而不是标记失败。
      durable: true,
    })
    this.lastEventSequences.set(request.request_id, 0)
    agentStore.startTurn(
      request.request_id,
      request.session_id,
      message,
      agentStore.planMode,
    )
    void this.syncTurnsToServer(
      request.session_id,
      agentStore.getTurnsForSession(request.session_id),
    )
    this.ws.send(JSON.stringify(request))
    agentStore.setProcessing(true)
    return request.request_id
  }

  /** 提交平面审核。确认后才继续三维；修改意见仍归属于原生成轮次。 */
  submitFloorPlanReview(
    requestId: string,
    action: 'confirm' | 'revise',
    feedback = '',
  ): string | null {
    const agentStore = useAgentStore()
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      agentStore.addSystemMessage('未连接到 Agent 服务')
      return null
    }
    const turn = agentStore.currentTurns.find(item => item.request_id === requestId)
    if (!turn || turn.status !== 'waiting_review') {
      agentStore.addSystemMessage('当前没有可提交的平面审核任务')
      return null
    }
    this.requestContexts.set(requestId, {
      sessionId: turn.session_id,
      turnId: requestId,
      durable: true,
    })
    agentStore.markFloorPlanReviewSubmitted(
      turn.session_id,
      requestId,
      action,
      feedback,
    )
    this.ws.send(JSON.stringify({
      protocol_version: AGENT_PROTOCOL_VERSION,
      type: 'floor_plan_review',
      request_id: requestId,
      session_id: turn.session_id,
      action,
      feedback: action === 'revise' ? feedback : undefined,
    }))
    agentStore.setProcessing(true, action === 'confirm' ? '平面已确认，开始生成三维…' : '正在根据修改意见重做平面…')
    void this.syncTurnsToServer(
      turn.session_id,
      agentStore.getTurnsForSession(turn.session_id),
    )
    return requestId
  }

  /** 提交第二次风格审核；主体已完成，但只有确认后才装配装饰并交付。 */
  submitStyleReview(
    requestId: string,
    action: 'confirm' | 'revise',
    stylePackageId = '',
    feedback = '',
  ): string | null {
    const agentStore = useAgentStore()
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      agentStore.addSystemMessage('未连接到 Agent 服务')
      return null
    }
    const turn = agentStore.currentTurns.find(item => item.request_id === requestId)
    if (!turn || turn.status !== 'waiting_review' || turn.style_review_status !== 'pending') {
      agentStore.addSystemMessage('当前没有可提交的风格审核任务')
      return null
    }
    const selectedStyleId = stylePackageId || turn.selected_style_id || ''
    this.requestContexts.set(requestId, {
      sessionId: turn.session_id,
      turnId: requestId,
      durable: true,
    })
    agentStore.markStyleReviewSubmitted(
      turn.session_id,
      requestId,
      action,
      selectedStyleId,
      feedback,
    )
    this.ws.send(JSON.stringify({
      protocol_version: AGENT_PROTOCOL_VERSION,
      type: 'style_review',
      request_id: requestId,
      session_id: turn.session_id,
      action,
      style_package_id: action === 'confirm' ? selectedStyleId : undefined,
      feedback: action === 'revise' ? feedback : undefined,
    }))
    agentStore.setProcessing(
      true,
      action === 'confirm' ? '风格已确认，正在装配装饰…' : '正在根据意见调整风格选择…',
    )
    void this.syncTurnsToServer(
      turn.session_id,
      agentStore.getTurnsForSession(turn.session_id),
    )
    return requestId
  }

  /** 批准执行计划，或提交意见后重新研究与规划。 */
  submitExecutionPlanReview(
    requestId: string,
    action: 'confirm' | 'revise',
    feedback = '',
  ): string | null {
    const agentStore = useAgentStore()
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      agentStore.addSystemMessage('未连接到 Agent 服务')
      return null
    }
    const turn = agentStore.currentTurns.find(item => item.request_id === requestId)
    if (
      !turn
      || turn.status !== 'waiting_review'
      || turn.execution_plan_review_status !== 'pending'
    ) {
      agentStore.addSystemMessage('当前没有可提交的执行计划')
      return null
    }
    this.requestContexts.set(requestId, {
      sessionId: turn.session_id,
      turnId: requestId,
      durable: true,
    })
    agentStore.markExecutionPlanReviewSubmitted(
      turn.session_id,
      requestId,
      action,
      feedback,
    )
    this.ws.send(JSON.stringify({
      protocol_version: AGENT_PROTOCOL_VERSION,
      type: 'execution_plan_review',
      request_id: requestId,
      session_id: turn.session_id,
      action,
      feedback: action === 'revise' ? feedback : undefined,
    }))
    agentStore.setProcessing(
      true,
      action === 'confirm' ? '计划已批准，开始执行…' : '正在根据意见重新规划…',
    )
    void this.syncTurnsToServer(
      turn.session_id,
      agentStore.getTurnsForSession(turn.session_id),
    )
    return requestId
  }

  /** 运行期间的新意见不启动第二个任务，而是排队到下一节点边界。 */
  submitExecutionFeedback(requestId: string, feedback: string): string | null {
    const agentStore = useAgentStore()
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      agentStore.addSystemMessage('未连接到 Agent 服务')
      return null
    }
    const turn = agentStore.currentTurns.find(item => item.request_id === requestId)
    if (!turn || turn.status !== 'running' || !turn.plan_mode) {
      agentStore.addSystemMessage('当前没有可调整的运行中计划')
      return null
    }
    agentStore.addMessageToSession(turn.session_id, {
      id: `msg_${requestId}_feedback_${Date.now()}`,
      role: 'user',
      content: feedback,
      timestamp: Date.now(),
      request_id: requestId,
      turn_id: requestId,
    })
    this.ws.send(JSON.stringify({
      protocol_version: AGENT_PROTOCOL_VERSION,
      type: 'execution_feedback',
      request_id: requestId,
      session_id: turn.session_id,
      feedback,
    }))
    agentStore.setProcessing(true, '修改意见已发送，将在下一节点边界处理…')
    void this.syncConversationState(turn.session_id)
    return requestId
  }

  /** 从 WebSocket URL 提取 HTTP Base URL */
  private get httpBaseUrl(): string {
    return this.url
      .replace(/\/ws\/agent$/, '')
      .replace(/^ws:\/\//, 'http://')
      .replace(/^wss:\/\//, 'https://')
  }

  /** 处理后端返回的业务消息 */
  private handleMessage(message: AgentMessage) {
    const agentStore = useAgentStore()
    const presenceStore = usePresenceStore()

    switch (message.type) {
      case 'generation_resumed':
        this.requestContexts.set(message.request_id, {
          sessionId: message.session_id,
          turnId: message.request_id,
          durable: true,
        })
        if (
          message.status === 'running'
          && message.session_id === agentStore.currentSessionId
        ) {
          agentStore.setProcessing(true, '正在恢复后台生成任务...')
        }
        break

      case 'agent_step':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        agentStore.setProcessing(true, message.content)
        const nodeName = message.node || message.step_id || message.stage
        const nodeStatus = message.status || (message.stage === 'finished' ? 'done' : 'running')
        const detail = message.detail || message.content
        const label = message.label || this.stageLabel(message.stage)

        // callback 后会再次进入 final_validate；每轮以最新完整结果替换上一轮，
        // 避免把 18 步重复累计成 36/54/72 步和多个相同错误。
        if (message.stage === 'generating' && nodeName === 'final_validate') {
          agentStore.clearPipelineSteps()
          agentStore.clearTurnValidationSteps(sessionId, message.request_id)
        }

        // validating 阶段的步骤单独存入流水线列表。
        if (message.stage === 'validating') {
          const validationStatus = nodeStatus === 'error' ? 'error'
            : nodeStatus === 'skipped' ? 'skip'
              : detail.startsWith('警告') || detail.includes('⚠️') ? 'warn'
                : 'ok'
          agentStore.addPipelineStep(`${label}: ${detail}`, validationStatus)
          agentStore.addTurnValidationStep(
            sessionId,
            message.request_id,
            `${label}: ${detail}`,
            validationStatus,
          )
        }

        if (message.stage === 'generating') {
          agentStore.updateGeneratingNode(nodeName, nodeStatus, detail, label)
          if (nodeStatus !== 'running') agentStore.completeNodeThinking(nodeName)
        }
        agentStore.updateTurnStep(sessionId, message.request_id, {
          node: nodeName,
          label,
          stage: message.stage,
          status: nodeStatus,
          detail,
        })
        if (message.stage === 'finished') {
          agentStore.completeTurn(
            sessionId,
            message.request_id,
            message.status === 'error' ? 'error' : 'completed',
          )
          if (sessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
          void this.syncTurnsToServer(
            sessionId,
            agentStore.getTurnsForSession(sessionId),
          )
        }
        break
        }

      case 'debug_log':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        if (message.category === 'session_metrics') {
          agentStore.setSessionMetrics(message.data as any)
          agentStore.setTurnMetrics(sessionId, message.request_id, message.data as any)
        } else {
          agentStore.addDebugLog(message.category, message.data)
          if (message.category === 'node') {
            agentStore.setTurnDiagnostic(sessionId, message.request_id, message.data as any)
          }
        }
        break
        }

      case 'execution_plan_ready':
        agentStore.setExecutionPlan(
          message.session_id,
          message.request_id,
          message.plan,
        )
        break

      case 'execution_plan_review_required':
        agentStore.setExecutionPlanReviewRequired(
          message.session_id,
          message.request_id,
          message.plan,
        )
        if (message.session_id === agentStore.currentSessionId) {
          agentStore.setProcessing(false)
        }
        void this.syncTurnsToServer(
          message.session_id,
          agentStore.getTurnsForSession(message.session_id),
        )
        break

      case 'execution_feedback_queued':
        agentStore.setExecutionFeedbackQueued(
          message.session_id,
          message.request_id,
          message.queued_count,
        )
        break

      case 'floor_plan_ready':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        agentStore.setTurnFloorPlan(
          sessionId,
          message.request_id,
          message.floor_plan,
          message.svg,
          message.svgs || { '1': message.svg },
          message.validation,
          message.notice || '',
        )
        break
        }

      case 'floor_plan_review_required':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        agentStore.setFloorPlanReviewRequired(
          sessionId,
          message.request_id,
          message.revision,
          message.can_confirm,
          message.fallback_reason || '',
          message.notice || '',
        )
        if (sessionId === agentStore.currentSessionId) {
          agentStore.setProcessing(false)
        }
        void this.syncTurnsToServer(
          sessionId,
          agentStore.getTurnsForSession(sessionId),
        )
        break
        }

      case 'style_review_required':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        agentStore.setStyleReviewRequired(
          sessionId,
          message.request_id,
          message.revision,
          message.selected_style_id,
          message.options,
        )
        if (sessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
        void this.syncTurnsToServer(
          sessionId,
          agentStore.getTurnsForSession(sessionId),
        )
        break
        }

      case 'thinking_delta':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        const visibleProgress = message.channel === 'progress'
        if (agentStore.thinkingMode || agentStore.precisionMode) {
          agentStore.appendThinkingContent(message.delta, message.node)
        }
        if (visibleProgress || agentStore.thinkingMode || agentStore.precisionMode) {
          agentStore.appendTurnThinking(
            sessionId,
            message.request_id,
            message.node || 'reasoning',
            message.delta,
            message.channel || 'reasoning',
          )
        }
        break
        }

      case 'thinking_status':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        if (agentStore.thinkingMode || agentStore.precisionMode) {
          agentStore.setThinkingStatus(message.status, message.content || '')
          agentStore.setTurnThinkingStatus(
            sessionId,
            message.request_id,
            message.status,
            message.content || '',
          )
        }
        if (message.status === 'completed') {
          agentStore.completeAllGeneratingNodes()
        }
        if (message.status === 'error' || message.status === 'unsupported') {
          agentStore.setProcessing(false)
        }
        break
        }

      case 'patch_proposal':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        agentStore.addAgentMessageForTurn(
          sessionId,
          message.request_id,
          message.patch.summary || 'AI 提出了修改建议',
          message.patch
        )
        if (sessionId === agentStore.currentSessionId) {
          agentStore.setPendingPatch(message.patch)
          agentStore.setProcessing(false)
        }
        agentStore.completeTurn(sessionId, message.request_id)
        void this.syncConversationState(sessionId)
        this.requestContexts.delete(message.request_id)
        break
        }

      case 'blueprint_generated':
        {
          const task = this.handleBlueprintGenerated(message)
          this.artifactTasks.set(message.request_id, task)
        }
        break

      case 'agent_reply':
        void this.handleAgentReply(message)
        break

      case 'presence_update':
        presenceStore.updatePresence(message.online_count, message.clients)
        break

      case 'error':
        {
        const context = this.requestContexts.get(message.request_id)
        const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
        if (message.code === 'floor_plan_review_rejected') {
          agentStore.restoreFloorPlanReviewAfterError(sessionId, message.request_id)
          agentStore.addSystemMessageForTurn(
            sessionId,
            message.request_id,
            `平面审核提交失败：${message.error}。按钮已恢复，可以重新提交。`,
          )
          if (sessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
          void this.syncConversationState(sessionId)
          break
        }
        if (message.code === 'style_review_rejected') {
          agentStore.restoreStyleReviewAfterError(sessionId, message.request_id)
          agentStore.addSystemMessageForTurn(
            sessionId,
            message.request_id,
            `风格审核提交失败：${message.error}。选项已恢复，可以重新提交。`,
          )
          if (sessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
          void this.syncConversationState(sessionId)
          break
        }
        if (message.code === 'execution_plan_review_rejected') {
          agentStore.restoreExecutionPlanReviewAfterError(sessionId, message.request_id)
          agentStore.addSystemMessageForTurn(
            sessionId,
            message.request_id,
            `执行计划提交失败：${message.error}。按钮已恢复。`,
          )
          if (sessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
          void this.syncConversationState(sessionId)
          break
        }
        if (message.code === 'execution_feedback_rejected') {
          agentStore.addSystemMessageForTurn(
            sessionId,
            message.request_id,
            `运行中意见未接收：${message.error}`,
          )
          break
        }
        agentStore.addSystemMessageForTurn(sessionId, message.request_id, `错误: ${message.error}`)
        agentStore.completeTurn(sessionId, message.request_id, 'error')
        if (sessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
        void this.syncConversationState(sessionId)
        this.requestContexts.delete(message.request_id)
        break
        }
    }
  }

  private stageLabel(stage: string): string {
    return ({
      analyzing: '理解需求',
      generating: '生成方案',
      validating: '校验结果',
      saving: '保存蓝图',
      finished: '处理完成',
    } as Record<string, string>)[stage] || stage
  }

  private interruptNonDurableTurns(reason: string) {
    if (this.requestContexts.size === 0) return
    const agentStore = useAgentStore()
    const affectedSessions = new Set<string>()
    for (const [requestId, context] of this.requestContexts) {
      if (context.durable) continue
      agentStore.addSystemMessageForTurn(context.sessionId, requestId, `错误: ${reason}`)
      agentStore.completeTurn(context.sessionId, requestId, 'error', reason)
      affectedSessions.add(context.sessionId)
      this.requestContexts.delete(requestId)
      this.artifactTasks.delete(requestId)
    }
    if (![...this.requestContexts.values()].some(context => context.durable)) {
      agentStore.setProcessing(false)
    }
    for (const sessionId of affectedSessions) void this.syncConversationState(sessionId)
  }

  /** 重连后重新附着后台任务，并从最后已处理序号继续补发关键事件。 */
  private resumeActiveGenerations() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return

    const agentStore = useAgentStore()
    const targets = new Map<string, { requestId?: string; lastEventSeq: number }>()
    for (const [requestId, context] of this.requestContexts) {
      if (!context.durable) continue
      targets.set(context.sessionId, {
        requestId,
        lastEventSeq: this.lastEventSequences.get(requestId) || 0,
      })
    }
    if (!targets.has(agentStore.currentSessionId)) {
      // 页面刷新后从持久化 Turn 找回 request_id；即使服务端已经完成，也能精确补发。
      const runningTurn = [...agentStore.getTurnsForSession(agentStore.currentSessionId)]
        .reverse()
        .find(turn => turn.status === 'running' || turn.status === 'waiting_review')
      targets.set(agentStore.currentSessionId, {
        requestId: runningTurn?.request_id,
        lastEventSeq: 0,
      })
    }

    for (const [sessionId, target] of targets) {
      if (!sessionId) continue
      this.ws.send(JSON.stringify({
        protocol_version: AGENT_PROTOCOL_VERSION,
        type: 'resume_generation',
        request_id: target.requestId,
        session_id: sessionId,
        last_event_seq: target.lastEventSeq,
      }))
    }
  }

  /** 处理后端推送的网络错误（心跳超时等） */
  private handleNetworkError(error: string) {
    console.warn('[AgentBridge] 收到网络错误:', error)
    const agentStore = useAgentStore()
    const presenceStore = usePresenceStore()
    agentStore.setNetworkError(error)
    presenceStore.setConnectionStatus('disconnected')
    agentStore.addSystemMessage(`⚠️ 网络异常: ${error}`)
  }

  /** 处理 AI 正式回复；Blueprint/ScenePatch 只通过独立产物事件处理。 */
  private async handleAgentReply(message: AgentReplyResponse) {
    const agentStore = useAgentStore()
    const context = this.requestContexts.get(message.request_id)
    const sessionId = message.session_id || context?.sessionId || agentStore.currentSessionId
    const artifactSucceeded = await (this.artifactTasks.get(message.request_id) || Promise.resolve(true))
    agentStore.addAgentMessageForTurn(
      sessionId,
      message.request_id,
      message.content,
      undefined,
      {
        cited_chunk_ids: message.cited_chunk_ids,
        evidence_status: message.evidence_status,
      },
    )
    agentStore.completeTurn(sessionId, message.request_id, artifactSucceeded ? 'completed' : 'error')
    if (sessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
    await this.syncConversationState(sessionId)
    this.artifactTasks.delete(message.request_id)
    this.requestContexts.delete(message.request_id)
  }

  /** 处理 AI 生成的 Blueprint：绕过缓存读取服务端文件并等待重建完成。 */
  private async handleBlueprintGenerated(message: BlueprintGeneratedResponse): Promise<boolean> {
    const sceneStore = useSceneStore()
    const agentStore = useAgentStore()
    const { filename, file_url: fileUrl } = message
    // session_id 优先取消息里的字段，回退时从 filename basename 里精确提取
    const basename = filename.split('/').pop()?.replace(/\.wild$/, '') ?? ''
    const match = basename.match(/^(session_\d+)/)
    const targetSessionId = message.session_id || (match ? match[1] : basename)

    if (!fileUrl) {
      agentStore.addSystemMessageForTurn(targetSessionId, message.request_id, '错误: 未收到蓝图文件地址')
      if (targetSessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
      return false
    }

    try {
      // 禁用缓存，避免同名会话文件从空 Blueprint 更新后仍返回旧内容。
      const separator = fileUrl.includes('?') ? '&' : '?'
      const response = await fetch(
        `${this.httpBaseUrl}${fileUrl}${separator}request_id=${encodeURIComponent(message.request_id)}`,
        { cache: 'no-store' },
      )
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const blueprint = await response.json()

      if (!blueprint || typeof blueprint !== 'object' || !('meta' in blueprint) || !('geometry' in blueprint)) {
        throw new Error('响应不是有效的 Blueprint 对象')
      }

      const typedBlueprint = blueprint as unknown as Blueprint
      const name = typedBlueprint.meta?.name
        ? `AI 生成 - ${typedBlueprint.meta.name}`
        : 'AI 生成'

      // 更新会话信息（含组件数和建筑类型）
      const elementsCount = (typedBlueprint.geometry?.elements?.length || 0)
      const componentsCount = (typedBlueprint.geometry?.components?.length || 0)
      const displayName = typedBlueprint.meta?.name || '未命名建筑'
      agentStore.updateSessionInfo(targetSessionId, displayName, elementsCount + componentsCount, componentsCount)
      agentStore.setSessionSaved(targetSessionId)

      // 用户在生成期间切换了会话时，不允许迟到结果覆盖当前画布。
      if (targetSessionId !== agentStore.currentSessionId) {
        agentStore.addSystemMessageForTurn(
          targetSessionId,
          message.request_id,
          `✅ ${displayName} 已生成；切换到该会话后查看`,
        )
        return true
      }

      const reconstructed = await sceneStore.loadBlueprint(
        typedBlueprint, name, sceneStore.document?.revision)
      if (!reconstructed) {
        const entity = sceneStore.reconstructed
        const reconstructionErrors = entity?.diagnostics.filter(item => item.level === 'error') || []
        if (entity?.meshes.length && reconstructionErrors.length) {
          const details = reconstructionErrors
            .slice(0, 3)
            .map(item => item.elementId ? `${item.elementId}: ${item.message}` : item.message)
            .join('；')
          agentStore.addSystemMessageForTurn(
            targetSessionId,
            message.request_id,
            `⚠️ Blueprint 已部分加载：${reconstructionErrors.length} 个构件重建失败（${details}）`,
          )
          agentStore.setBlueprintLoaded(filename)
          return true
        }
        throw new Error('Blueprint 已读取，但场景重建失败')
      }

      agentStore.addSystemMessageForTurn(
        targetSessionId,
        message.request_id,
        `✅ Blueprint 已加载（${filename}）`,
      )
      agentStore.setBlueprintLoaded(filename)
      return true
    } catch (err) {
      console.error('[AgentBridge] 拉取蓝图失败:', err)
      agentStore.addSystemMessageForTurn(
        targetSessionId,
        message.request_id,
        `❌ 加载蓝图失败: ${filename}`,
      )
      return false
    } finally {
      if (targetSessionId === agentStore.currentSessionId) agentStore.setProcessing(false)
    }
  }

  /** 同步当前 Blueprint 到后端（PUT 覆盖写入，日期子目录格式） */
  async syncBlueprintToBackend(blueprint: Record<string, unknown>): Promise<boolean> {
    const agentStore = useAgentStore()
    const sceneStore = useSceneStore()
    const sessionId = agentStore.currentSessionId

    try {
      // 写入当前 revision 到 editor 元数据，重新加载会话时恢复版本连续性
      const payload = { ...blueprint } as Record<string, unknown>
      const editor = (payload.editor && typeof payload.editor === 'object')
        ? { ...(payload.editor as Record<string, unknown>) }
        : {}
      editor.revision = sceneStore.document?.revision ?? 1
      payload.editor = editor

      const baseUrl = this.httpBaseUrl
      const relPath = buildSceneRelPath(sessionId, payload)
      const response = await fetch(`${baseUrl}/api/scenes/${relPath}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) {
        console.error('[AgentBridge] 同步蓝图失败:', response.status)
        return false
      }
      return true
    } catch (err) {
      console.error('[AgentBridge] 同步蓝图异常:', err)
      return false
    }
  }

  /** 从后端加载会话对应的蓝图 */
  async loadSessionBlueprint(sessionId: string): Promise<Record<string, unknown> | null> {
    try {
      const baseUrl = this.httpBaseUrl
      // 优先从 sessions 列表找已知的带日期路径 filename，兼容旧格式
      const agentStore = useAgentStore()
      const session = agentStore.sessions.find(s => s.session_id === sessionId)
      let relPath = session?.filename
      // 草稿/失败会话本来就没有场景文件，不应请求一个猜测路径制造 404。
      if (!relPath && session?.status === 'draft') return null
      if (!relPath) {
        const info = await fetch(`${baseUrl}/api/sessions/${encodeURIComponent(sessionId)}`, {
          cache: 'no-store',
        })
        if (!info.ok) return null
        const sessionInfo = await info.json()
        relPath = sessionInfo?.filename || undefined
      }
      if (!relPath) return null
      const response = await fetch(`${baseUrl}/api/scenes/${relPath}`)
      if (!response.ok) {
        return null
      }
      return await response.json()
    } catch (err) {
      console.error('[AgentBridge] 加载会话蓝图失败:', err)
      return null
    }
  }

  /** 删除后端会话蓝图文件 */
  async deleteSessionBlueprint(sessionId: string) {
    try {
      const baseUrl = this.httpBaseUrl
      const agentStore = useAgentStore()

      // 先查权威 filename：优先服务端记录的路径，避免本地缓存缺失时
      // 回退到根目录 {sessionId}.wild 导致日期子目录文件删不掉。
      let relPath: string | undefined = agentStore.sessions.find(s => s.session_id === sessionId)?.filename
      if (!relPath) {
        try {
          const info = await fetch(`${baseUrl}/api/sessions/${sessionId}`, { cache: 'no-store' })
          if (info.ok) {
            const sessionInfo = await info.json()
            relPath = sessionInfo?.filename || undefined
          }
        } catch {
          // 会话信息拉取失败时继续走 scenes 删除，让后端按 session_id 精确匹配
        }
      }

      if (relPath) {
        const response = await fetch(`${baseUrl}/api/scenes/${relPath}`, {
          method: 'DELETE',
        })
        return response.ok || response.status === 404
      }

      // 未保存的新会话没有服务端文件，删除客户端会话同样视为成功。
      return true
    } catch (err) {
      console.error('[AgentBridge] 删除蓝图失败:', err)
      return false
    }
  }

  /** 从后端获取所有会话列表（优先新接口，fallback 旧接口） */
  async fetchSessionList(): Promise<Array<{ session_id?: string; filename?: string; name: string; elements_count: number; updated_at: number; created_at?: number; components_count?: number; message_count?: number; status?: string; building_type?: string }> | null> {
    try {
      const baseUrl = this.httpBaseUrl

      // 优先使用新 sessions API
      let response = await fetch(`${baseUrl}/api/sessions`)
      if (response.ok) {
        return await response.json()
      }

      // fallback: 旧 scenes 文件列表
      // （旧接口返回格式不含 status/building_type/components_count 等新字段）
      response = await fetch(`${baseUrl}/api/scenes`)
      if (!response.ok) {
        return null
      }
      const scenes = await response.json()
      return scenes.map((s: any) => ({ ...s, status: 'saved' }))
    } catch (err) {
      console.error('[AgentBridge] 获取会话列表失败:', err)
      return null
    }
  }

  /** 从服务端恢复会话消息；本地未同步消息由 Store 按 id 合并。 */
  async fetchSessionMessages(sessionId: string): Promise<ChatMessage[] | null> {
    try {
      const response = await fetch(
        `${this.httpBaseUrl}/api/sessions/${encodeURIComponent(sessionId)}/messages`,
        { cache: 'no-store' },
      )
      if (!response.ok) return null
      return await response.json()
    } catch (err) {
      console.error('[AgentBridge] 获取会话消息失败:', err)
      return null
    }
  }

  /**
   * 将用户对 RAG 回答的评价写入对应 RAGTrace。
   * 回复事件与 Trace 文件落盘时间非常接近，因此 404 时做两次短暂重试。
   */
  async submitRagFeedback(
    sessionId: string,
    requestId: string,
    rating: 'up' | 'down',
  ): Promise<boolean> {
    const retryDelays = [0, 150, 400]
    for (const delay of retryDelays) {
      if (delay > 0) await new Promise(resolve => window.setTimeout(resolve, delay))
      try {
        const response = await fetch(`${this.httpBaseUrl}/api/rag/feedback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            request_id: requestId,
            rating,
          }),
        })
        if (response.ok) return true
        if (response.status !== 404) return false
      } catch (err) {
        console.error('[AgentBridge] 提交 RAG 反馈失败:', err)
        return false
      }
    }
    return false
  }

  /** 从服务端恢复按请求归档的 Agent Turn。 */
  async fetchSessionTurns(sessionId: string): Promise<AgentTurn[] | null> {
    try {
      const response = await fetch(
        `${this.httpBaseUrl}/api/sessions/${encodeURIComponent(sessionId)}/turns`,
        { cache: 'no-store' },
      )
      if (!response.ok) return null
      return await response.json()
    } catch (err) {
      console.error('[AgentBridge] 获取 Agent Turn 失败:', err)
      return null
    }
  }

  /** 同步消息到后端 */
  async syncMessagesToServer(sessionId: string, messages: Array<{ id: string; role: string; content: string; timestamp: number }>): Promise<boolean> {
    try {
      const baseUrl = this.httpBaseUrl
      const response = await fetch(`${baseUrl}/api/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(messages),
      })
      return response.ok
    } catch (err) {
      console.error('[AgentBridge] 同步消息失败:', err)
      return false
    }
  }

  /** 用当前快照替换服务端 Turn 历史。 */
  async syncTurnsToServer(sessionId: string, turns: AgentTurn[]): Promise<boolean> {
    const body = JSON.stringify({ turns })
    const previous = this.turnSyncQueues.get(sessionId) || Promise.resolve(true)
    const current = previous.catch(() => false).then(async () => {
      try {
        const response = await fetch(
          `${this.httpBaseUrl}/api/sessions/${encodeURIComponent(sessionId)}/turns`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body,
          },
        )
        return response.ok
      } catch (err) {
        console.error('[AgentBridge] 同步 Agent Turn 失败:', err)
        return false
      }
    })
    this.turnSyncQueues.set(sessionId, current)
    try {
      return await current
    } finally {
      if (this.turnSyncQueues.get(sessionId) === current) {
        this.turnSyncQueues.delete(sessionId)
      }
    }
  }

  private async syncConversationState(sessionId: string): Promise<void> {
    const agentStore = useAgentStore()
    await Promise.all([
      this.syncMessagesToServer(sessionId, agentStore.getMessagesForSession(sessionId)),
      this.syncTurnsToServer(sessionId, agentStore.getTurnsForSession(sessionId)),
    ])
  }

  /** 更新会话元数据（名称等） */
  async updateSessionMeta(sessionId: string, updates: { name?: string; building_type?: string }): Promise<boolean> {
    try {
      const baseUrl = this.httpBaseUrl
      const response = await fetch(`${baseUrl}/api/sessions/${sessionId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      return response.ok
    } catch (err) {
      console.error('[AgentBridge] 更新会话元数据失败:', err)
      return false
    }
  }

  /** 启动心跳 */
  private startHeartbeat() {
    this.stopHeartbeat()

    this.heartbeatTimer = setInterval(() => {
      this.sendPing()

      // 设置 pong 超时
      this.pongTimeoutTimer = setTimeout(() => {
        console.warn('[AgentBridge] 心跳超时，未收到 pong 响应')
        this.onHeartbeatTimeout()
      }, HEARTBEAT_CONFIG.timeout)
    }, HEARTBEAT_CONFIG.interval)
  }

  /** 停止心跳 */
  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    if (this.pongTimeoutTimer) {
      clearTimeout(this.pongTimeoutTimer)
      this.pongTimeoutTimer = null
    }
  }

  /** 发送 ping */
  private sendPing() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return

    const pingMsg = {
      protocol_version: AGENT_PROTOCOL_VERSION,
      type: 'ping' as const,
      timestamp: Date.now()
    }
    this.ws.send(JSON.stringify(pingMsg))
  }

  /** 处理 pong 响应 */
  private handlePong(_timestamp: number) {
    // 清除 pong 超时定时器
    if (this.pongTimeoutTimer) {
      clearTimeout(this.pongTimeoutTimer)
      this.pongTimeoutTimer = null
    }
  }

  /** 心跳超时处理 */
  private onHeartbeatTimeout() {
    // 判定连接已死，强制关闭并重连
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.stopHeartbeat()

    const agentStore = useAgentStore()
    agentStore.setNetworkError('连接超时，正在重新连接...')
  }

  /** 调度自动重连 */
  private scheduleReconnect() {
    if (this.manualDisconnect) return
    if (this.reconnectTimer) return

    if (this.reconnectAttempts >= RECONNECT_CONFIG.maxAttempts) {
      console.warn('[AgentBridge] 已达最大重试次数，停止重连')
      const agentStore = useAgentStore()
      const presenceStore = usePresenceStore()
      agentStore.setConnectionStatus('disconnected')
      presenceStore.setConnectionStatus('disconnected')
      agentStore.setNetworkError('无法连接到服务器，请检查网络后手动重连')
      return
    }

    const agentStore = useAgentStore()
    const presenceStore = usePresenceStore()
    agentStore.setConnectionStatus('reconnecting')
    presenceStore.setConnectionStatus('reconnecting')

    // 指数退避 + 抖动
    const delay = Math.min(
      this.reconnectDelay,
      RECONNECT_CONFIG.maxDelay
    )
    const jitter = delay * RECONNECT_CONFIG.jitter * (Math.random() * 2 - 1)
    const actualDelay = Math.round(delay + jitter)

    console.log(
      `[AgentBridge] 将在 ${actualDelay}ms 后尝试第 ${this.reconnectAttempts + 1} 次重连...`
    )

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.reconnectAttempts++
      this.reconnectDelay *= RECONNECT_CONFIG.factor
      this.connect()
    }, actualDelay)
  }

  /** 清除所有定时器 */
  private clearAllTimers() {
    this.stopHeartbeat()
    this.removeVisibilityListener()

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}

/** 全局单例 */
export const agentBridge = new AgentBridge()
