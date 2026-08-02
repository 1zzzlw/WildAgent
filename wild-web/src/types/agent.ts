/**
 * Agent 通信协议类型定义
 *
 * 定义前后端 WebSocket 通信的消息格式：
 *
 * 前端发送：
 * - UserMessageRequest: 用户输入的消息 + 场景上下文
 * - PingMessage: 心跳 ping
 *
 * 后端返回：
 * - AgentStepResponse: Agent 执行步骤（可选，用于显示进度）
 * - ThinkingDeltaResponse: 模型接口实际返回的思考内容片段
 * - ThinkingStatusResponse: 思考请求状态
 * - PatchProposalResponse: 场景修改提案
 * - AgentReplyResponse: 文本回复
 * - ErrorResponse: 错误信息
 * - PongMessage: 心跳 pong
 * - NetworkErrorResponse: 心跳超时导致的网络错误
 *
 * 会话管理：
 * - ChatMessage: 聊天消息（用户/Agent/系统）
 * - AgentSession: 会话状态（session_id, messages, connected）
 *
 * 连接状态：
 * - ConnectionStatus: 详细连接状态枚举
 */

import type { ScenePatch } from './scenePatch'
import type { SceneSummary } from './scene'
import type { PresenceUpdateResponse } from '../extensions/presence/types'

// 重新导出SceneSummary以便在protocol.ts中使用
export type { SceneSummary }

/** WebSocket 连接状态 */
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting'

export type AgentMessage =
  | UserMessageRequest
  | AgentStepResponse
  | ThinkingDeltaResponse
  | ThinkingStatusResponse
  | PatchProposalResponse
  | AgentReplyResponse
  | BlueprintGeneratedResponse
  | ErrorResponse
  | PingMessage
  | PongMessage
  | NetworkErrorResponse
  | PresenceUpdateResponse

export interface UserMessageRequest {
  type: 'user_message'
  request_id: string
  session_id: string
  scene_id?: string
  scene_revision: number
  message: string
  scene_summary?: SceneSummary
  selection: string[]
  blueprint?: Record<string, unknown>  // 当前场景的完整 Blueprint（增量修改时需要）
  thinking_mode?: boolean              // 是否让模型开启思考并流式返回 reasoning_content
}

export interface AgentStepResponse {
  type: 'agent_step'
  request_id: string
  stage: string
  content: string
}

/** 模型接口实际返回的 reasoning_content 增量 */
export interface ThinkingDeltaResponse {
  type: 'thinking_delta'
  request_id: string
  delta: string
}

export interface ThinkingStatusResponse {
  type: 'thinking_status'
  request_id: string
  status: 'thinking' | 'completed' | 'unsupported' | 'error'
  content?: string
}

export interface PatchProposalResponse {
  type: 'patch_proposal'
  request_id: string
  patch: ScenePatch
}

export interface AgentReplyResponse {
  type: 'agent_reply'
  request_id: string
  content: string
}

export interface ErrorResponse {
  type: 'error'
  request_id: string
  error: string
}

/** 心跳 ping（前端 → 后端） */
export interface PingMessage {
  type: 'ping'
  timestamp: number
}

/** 心跳 pong（后端 → 前端） */
export interface PongMessage {
  type: 'pong'
  timestamp: number
}

/** 心跳超时导致的网络错误（后端 → 前端） */
export interface NetworkErrorResponse {
  type: 'network_error'
  error: string
  reason: 'heartbeat_timeout' | 'connection_lost'
}

/** AI 生成的 Blueprint（后端 → 前端，通过 HTTP 拉取文件） */
export interface BlueprintGeneratedResponse {
  type: 'blueprint_generated'
  request_id: string
  /** 生成请求所属会话；旧后端可能不提供，前端会从 filename 回退推断。 */
  session_id?: string
  filename: string
  file_url: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'agent' | 'system'
  content: string
  timestamp: number
  patch?: ScenePatch
}

export interface AgentSession {
  session_id: string
  messages: ChatMessage[]
  connected: boolean
}

/** 会话列表项（由后端 storage/scenes 文件摘要生成） */
export interface SessionInfo {
  session_id: string
  /** 后端文件相对路径，如 "2026-08-02/session_xxx_名称.wild"，新格式含日期目录 */
  filename?: string
  name: string           // 从 blueprint.meta.name 提取
  created_at: number
  updated_at: number
  elements_count: number
}
