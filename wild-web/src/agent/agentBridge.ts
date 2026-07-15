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
 * - scheduleReconnect(): 自动重连（断线后 5 秒重试）
 * 
 * 消息处理：
 * - agent_step: 更新执行步骤显示
 * - patch_proposal: 设置待确认 Patch
 * - agent_reply: 添加 Agent 回复消息
 * - error: 显示错误信息
 * 
 * 连接状态：
 * - 自动连接和重连
 * - 更新 agentStore.connected 状态
 * - 显示连接状态提示
 * 
 * 用于：
 * - AI 对话面板的实时通信
 * - Agent 流式响应显示
 * - Patch 提案推送
 */

import { useAgentStore } from '../stores/agentStore'
import { useSceneStore } from '../stores/sceneStore'
import { generateSceneSummary } from '../wild/sceneSummary'
import { createUserMessageRequest } from './protocol'
import type { AgentMessage } from '../types/agent'

export class AgentBridge {
  private ws: WebSocket | null = null
  private url: string
  private reconnectTimer: number | null = null

  constructor(url: string = 'ws://localhost:8000/ws/agent') {
    this.url = url
  }

  connect() {
    const agentStore = useAgentStore()

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        console.log('Agent WebSocket 已连接')
        agentStore.setConnected(true)
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer)
          this.reconnectTimer = null
        }
      }

      this.ws.onmessage = (event) => {
        try {
          const message: AgentMessage = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('解析 Agent 消息失败', error)
        }
      }

      this.ws.onerror = (error) => {
        console.error('Agent WebSocket 错误', error)
      }

      this.ws.onclose = () => {
        console.log('Agent WebSocket 已断开')
        agentStore.setConnected(false)
        this.scheduleReconnect()
      }
    } catch (error) {
      console.error('连接 Agent 失败', error)
      agentStore.setConnected(false)
      this.scheduleReconnect()
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    const agentStore = useAgentStore()
    agentStore.setConnected(false)
  }

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
    agentStore.setProcessing(true)
  }

  private handleMessage(message: AgentMessage) {
    const agentStore = useAgentStore()

    switch (message.type) {
      case 'agent_step':
        agentStore.setProcessing(true, message.content)
        break

      case 'patch_proposal':
        agentStore.setPendingPatch(message.patch)
        agentStore.setProcessing(false)
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

  private scheduleReconnect() {
    if (this.reconnectTimer) return

    this.reconnectTimer = window.setTimeout(() => {
      console.log('尝试重新连接 Agent...')
      this.connect()
    }, 5000)
  }
}
