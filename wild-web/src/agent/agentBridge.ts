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
import { generateSceneSummary } from '../wild/sceneSummary'
import { createUserMessageRequest } from './protocol'
import type { AgentMessage } from '../types/agent'

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


  constructor(url: string = 'ws://localhost:8000/ws/agent') {
    this.url = url
  }

  /** 初始化连接 */
  connect() {
    const agentStore = useAgentStore()

    this.manualDisconnect = false
    agentStore.setConnectionStatus('connecting')

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        console.log('[AgentBridge] WebSocket 已连接')
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

  /** 断开连接（主动，不触发重连） */
  disconnect() {
    this.manualDisconnect = true

    // 清除所有定时器 + 页面可见性监听
    this.clearAllTimers()
    this.removeVisibilityListener()

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    const agentStore = useAgentStore()
    agentStore.setConnectionStatus('disconnected')
    agentStore.clearNetworkError()
  }

  /** 发送用户消息 */
  sendUserMessage(message: string) {
    const agentStore = useAgentStore()
    const sceneStore = useSceneStore()

    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      agentStore.addSystemMessage('未连接到 Agent 服务')
      return
    }

    if (!sceneStore.document) {
      agentStore.addSystemMessage('无场景文档')
      return
    }

    const sceneSummary = generateSceneSummary(sceneStore.document.blueprint)
    const selection: string[] = [] // TODO: 从 selectionStore 获取

    const request = createUserMessageRequest(
      message,
      agentStore.session.session_id,
      sceneStore.document.id,
      sceneStore.document.revision,
      sceneSummary,
      selection
    )

    this.ws.send(JSON.stringify(request))
    agentStore.clearPipelineSteps()
    agentStore.setProcessing(true)
  }

  /** 处理后端返回的业务消息 */
  private handleMessage(message: AgentMessage) {
    const agentStore = useAgentStore()

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

      case 'patch_proposal':
        agentStore.setPendingPatch(message.patch)
        agentStore.setProcessing(false)
        break

      case 'blueprint_generated':
        this.handleBlueprintGenerated(message.filename, message.file_url)
        break

      case 'agent_reply':
        agentStore.addAgentMessage(message.content)
        agentStore.setProcessing(false)
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
    agentStore.setNetworkError(error)
    agentStore.addSystemMessage(`⚠️ 网络异常: ${error}`)
  }

  /** 处理 AI 生成的 Blueprint：通过 HTTP 拉取文件 → 加载到场景 + 触发渲染 */
  private async handleBlueprintGenerated(filename: string, fileUrl: string) {
    const sceneStore = useSceneStore()
    const agentStore = useAgentStore()

    if (!fileUrl) {
      agentStore.addSystemMessage('错误: 未收到蓝图文件地址')
      agentStore.setProcessing(false)
      return
    }

    try {
      // 通过 HTTP 拉取蓝图 JSON
      const baseUrl = this.url.replace('/ws/agent', '').replace('ws://', 'http://')
      const response = await fetch(`${baseUrl}${fileUrl}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const blueprint = await response.json()

      const name = blueprint.meta?.name
        ? `AI 生成 - ${blueprint.meta.name}`
        : 'AI 生成'

      sceneStore.loadBlueprint(blueprint, name)
      agentStore.addSystemMessage(`✅ Blueprint 已加载（${filename}）`)
      agentStore.setBlueprintLoaded(filename)
    } catch (err) {
      console.error('[AgentBridge] 拉取蓝图失败:', err)
      agentStore.addSystemMessage(`❌ 加载蓝图失败: ${filename}`)
    } finally {
      agentStore.setProcessing(false)
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
      agentStore.setConnectionStatus('disconnected')
      agentStore.setNetworkError('无法连接到服务器，请检查网络后手动重连')
      return
    }

    const agentStore = useAgentStore()
    agentStore.setConnectionStatus('reconnecting')

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
