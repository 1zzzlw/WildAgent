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
import { createUserMessageRequest } from './protocol'
import type { AgentMessage, BlueprintGeneratedResponse } from '../types/agent'
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
 */
function buildSceneRelPath(sessionId: string, blueprint: Record<string, unknown>): string {
  const today = new Date().toISOString().slice(0, 10)  // YYYY-MM-DD
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
      }

      this.ws.onmessage = (event) => {
        try {
          const message: AgentMessage = JSON.parse(event.data)

          // 优先处理心跳响应（不进入业务逻辑）
          if (message.type === 'pong') {
            this.handlePong(message.timestamp)
            return
          }

          if (message.type === 'network_error') {
            this.handleNetworkError(message.error)
            return
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
  sendUserMessage(message: string) {
    const agentStore = useAgentStore()
    const sceneStore = useSceneStore()
    const selectionStore = useSelectionStore()

    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      agentStore.addSystemMessage('未连接到 Agent 服务')
      return
    }

    if (!sceneStore.document) {
      agentStore.addSystemMessage('无场景文档')
      return
    }

    const sceneSummary = generateSceneSummary(sceneStore.document.blueprint)
    const selection = [...selectionStore.selectedIds]

    const request = createUserMessageRequest(
      message,
      agentStore.session.session_id,
      sceneStore.document.id,
      sceneStore.document.revision,
      sceneSummary,
      selection,
      sceneStore.document.blueprint as Record<string, unknown>,
      agentStore.thinkingMode
    )

    this.ws.send(JSON.stringify(request))
    agentStore.clearPipelineSteps()
    agentStore.clearThinkingState()
    agentStore.setProcessing(true)
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
      case 'agent_step':
        agentStore.setProcessing(true, message.content)
        // validating 阶段的步骤单独存入流水线列表
        if (message.stage === 'validating') {
          const content = message.content
          const status = content.startsWith('❌') ? 'error'
            : content.startsWith('⚠️') ? 'warn'
              : content.startsWith('⏭️') ? 'skip'
                : 'ok'
          agentStore.addPipelineStep(content, status)
        }
        break

      case 'thinking_delta':
        if (agentStore.thinkingMode) {
          agentStore.appendThinkingContent(message.delta)
        }
        break

      case 'thinking_status':
        if (agentStore.thinkingMode) {
          agentStore.setThinkingStatus(message.status, message.content || '')
        }
        break

      case 'patch_proposal':
        agentStore.addAgentMessage(
          message.patch.summary || 'AI 提出了修改建议',
          message.patch
        )
        agentStore.setPendingPatch(message.patch)
        agentStore.setProcessing(false)
        break

      case 'blueprint_generated':
        void this.handleBlueprintGenerated(message)
        break

      case 'agent_reply':
        agentStore.addAgentMessage(message.content)
        agentStore.setProcessing(false)
        break

      case 'presence_update':
        presenceStore.updatePresence(message.online_count, message.clients)
        break

      case 'error':
        agentStore.addSystemMessage(`错误: ${message.error}`)
        agentStore.setProcessing(false)
        break
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

  /** 处理 AI 生成的 Blueprint：绕过缓存读取服务端文件并等待重建完成。 */
  private async handleBlueprintGenerated(message: BlueprintGeneratedResponse) {
    const sceneStore = useSceneStore()
    const agentStore = useAgentStore()
    const { filename, file_url: fileUrl } = message
    const targetSessionId = message.session_id
      || filename.replace(/\.wild$/, '')

    if (!fileUrl) {
      agentStore.addSystemMessage('错误: 未收到蓝图文件地址')
      agentStore.setProcessing(false)
      return
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

      // 更新会话信息
      const elementsCount = (typedBlueprint.geometry?.elements?.length || 0)
        + (typedBlueprint.geometry?.components?.length || 0)
      const displayName = typedBlueprint.meta?.name || '未命名建筑'
      agentStore.updateSessionInfo(targetSessionId, displayName, elementsCount)

      // 用户在生成期间切换了会话时，不允许迟到结果覆盖当前画布。
      if (targetSessionId !== agentStore.currentSessionId) {
        agentStore.addSystemMessage(`✅ ${displayName} 已生成；切换到对应会话后查看`)
        return
      }

      const reconstructed = await sceneStore.loadBlueprint(typedBlueprint, name)
      if (!reconstructed) {
        throw new Error('Blueprint 已读取，但场景重建失败')
      }

      agentStore.addSystemMessage(`✅ Blueprint 已加载（${filename}）`)
      agentStore.setBlueprintLoaded(filename)
    } catch (err) {
      console.error('[AgentBridge] 拉取蓝图失败:', err)
      agentStore.addSystemMessage(`❌ 加载蓝图失败: ${filename}`)
    } finally {
      agentStore.setProcessing(false)
    }
  }

  /** 同步当前 Blueprint 到后端（PUT 覆盖写入，日期子目录格式） */
  async syncBlueprintToBackend(blueprint: Record<string, unknown>): Promise<boolean> {
    const agentStore = useAgentStore()
    const sessionId = agentStore.currentSessionId

    try {
      const baseUrl = this.httpBaseUrl
      const relPath = buildSceneRelPath(sessionId, blueprint)
      const response = await fetch(`${baseUrl}/api/scenes/${relPath}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(blueprint),
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
      const relPath = session?.filename ?? `${sessionId}.wild`
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
      const session = agentStore.sessions.find(s => s.session_id === sessionId)
      const relPath = session?.filename ?? `${sessionId}.wild`
      const response = await fetch(`${baseUrl}/api/scenes/${relPath}`, {
        method: 'DELETE',
      })
      // 未保存的新会话没有服务端文件，删除客户端会话同样视为成功。
      return response.ok || response.status === 404
    } catch (err) {
      console.error('[AgentBridge] 删除蓝图失败:', err)
      return false
    }
  }

  /** 从后端获取所有已保存的场景列表 */
  async fetchSessionList(): Promise<Array<{ filename: string; name: string; elements_count: number; updated_at: number }> | null> {
    try {
      const baseUrl = this.httpBaseUrl
      const response = await fetch(`${baseUrl}/api/scenes`)
      if (!response.ok) {
        return null
      }
      return await response.json()
    } catch (err) {
      console.error('[AgentBridge] 获取场景列表失败:', err)
      return null
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
