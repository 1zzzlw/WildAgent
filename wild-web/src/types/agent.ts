/**
 * Agent 通信协议类型定义
 * 
 * 定义前后端 WebSocket 通信的消息格式：
 * 
 * 前端发送：
 * - UserMessageRequest: 用户输入的消息 + 场景上下文
 * 
 * 后端返回：
 * - AgentStepResponse: Agent 执行步骤（可选，用于显示进度）
 * - PatchProposalResponse: 场景修改提案
 * - AgentReplyResponse: 文本回复
 * - ErrorResponse: 错误信息
 * 
 * 会话管理：
 * - ChatMessage: 聊天消息（用户/Agent/系统）
 * - AgentSession: 会话状态（session_id, messages, connected）
 */

import type { ScenePatch } from './scenePatch'
import type { SceneSummary } from './scene'

// 重新导出SceneSummary以便在protocol.ts中使用
export type { SceneSummary }

export type AgentMessage =
  | UserMessageRequest
  | AgentStepResponse
  | PatchProposalResponse
  | AgentReplyResponse
  | ErrorResponse

export interface UserMessageRequest {
  type: 'user_message'
  request_id: string
  session_id: string
  scene_id?: string
  scene_revision: number
  message: string
  scene_summary?: SceneSummary
  selection: string[]
}

export interface AgentStepResponse {
  type: 'agent_step'
  request_id: string
  stage: string
  content: string
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
