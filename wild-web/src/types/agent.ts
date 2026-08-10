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

export type AgentProtocolVersion = '1.0'

export interface AgentProtocolEnvelope {
  protocol_version: AgentProtocolVersion
}

export type AgentMessage =
  | UserMessageRequest
  | AgentStepResponse
  | ThinkingDeltaResponse
  | ThinkingStatusResponse
  | PatchProposalResponse
  | AgentReplyResponse
  | BlueprintGeneratedResponse
  | DebugLogResponse
  | ErrorResponse
  | PingMessage
  | PongMessage
  | NetworkErrorResponse
  | PresenceUpdateResponse

export interface UserMessageRequest extends AgentProtocolEnvelope {
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
  precision_mode?: boolean             // 是否启用 LangGraph 精密模式（分片并行 + 详细日志）
}

export interface AgentStepResponse extends AgentProtocolEnvelope {
  type: 'agent_step'
  request_id: string
  session_id?: string
  stage: string
  step_id?: string
  node?: string
  status?: 'running' | 'done' | 'skipped' | 'error'
  label?: string
  detail?: string
  content: string
}

/** 模型接口实际返回的 reasoning_content 增量 */
export interface ThinkingDeltaResponse extends AgentProtocolEnvelope {
  type: 'thinking_delta'
  request_id: string
  session_id?: string
  node?: string  // 精密模式下，标识是哪个节点的思考内容
  channel?: 'reasoning' | 'progress'
  delta: string
}

export interface ThinkingStatusResponse extends AgentProtocolEnvelope {
  type: 'thinking_status'
  request_id: string
  session_id?: string
  status: 'thinking' | 'completed' | 'unsupported' | 'error'
  content?: string
}

export interface PatchProposalResponse extends AgentProtocolEnvelope {
  type: 'patch_proposal'
  request_id: string
  session_id?: string
  patch: ScenePatch
}

export interface AgentReplyResponse extends AgentProtocolEnvelope {
  type: 'agent_reply'
  request_id: string
  session_id?: string
  content: string
}

export interface ErrorResponse extends AgentProtocolEnvelope {
  type: 'error'
  request_id: string
  session_id?: string
  code?: string
  error: string
}

/** 心跳 ping（前端 → 后端） */
export interface PingMessage extends AgentProtocolEnvelope {
  type: 'ping'
  timestamp: number
}

/** 心跳 pong（后端 → 前端） */
export interface PongMessage extends AgentProtocolEnvelope {
  type: 'pong'
  timestamp: number
}

/** 心跳超时导致的网络错误（后端 → 前端） */
export interface NetworkErrorResponse extends AgentProtocolEnvelope {
  type: 'network_error'
  error: string
  reason: 'heartbeat_timeout' | 'connection_lost'
}

/** AI 生成的 Blueprint（后端 → 前端，通过 HTTP 拉取文件） */
export interface BlueprintGeneratedResponse extends AgentProtocolEnvelope {
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
  /** ScenePatch 提案只能被处理一次；用于禁用历史消息中的重复操作按钮。 */
  patch_status?: 'pending' | 'applying' | 'applied' | 'rejected' | 'expired'
  /** 将消息绑定到一次用户请求，保证过程、回复和产物保持在同一轮。 */
  request_id?: string
  turn_id?: string
}

export interface AgentTurnStep {
  node: string
  label: string
  stage: string
  status: 'running' | 'done' | 'skipped' | 'error'
  detail: string
  thinking: string
  thinking_channel?: 'reasoning' | 'progress'
  diagnostic?: NodeDiagnostic
}

export interface AgentTurn {
  turn_id: string
  request_id: string
  session_id: string
  user_message_id: string
  status: 'running' | 'completed' | 'error'
  started_at: number
  completed_at?: number
  interruption_reason?: string
  thinking_status?: 'thinking' | 'completed' | 'unsupported' | 'error'
  thinking_notice?: string
  steps: AgentTurnStep[]
  validation_steps: Array<{
    label: string
    status: 'ok' | 'warn' | 'error' | 'skip'
  }>
  metrics?: SessionMetrics
}

export interface AgentSession {
  session_id: string
  messages: ChatMessage[]
  connected: boolean
}

/** 精密模式：后端推送的节点诊断日志 */
export interface DebugLogResponse extends AgentProtocolEnvelope {
  type: 'debug_log'
  request_id: string
  session_id?: string
  category: 'node' | 'error' | 'session_metrics'
  data: NodeDiagnostic | ErrorDiagnostic | SessionMetrics
}

export interface NodeDiagnostic {
  node: string
  stage: 'done' | 'skipped'
  label?: string
  rag_chars?: number
  rag_ms?: number
  rag_hits?: Array<{
    source: string
    heading: string
    doc_type: string
    entity_type: string
  }>
  prompt_chars?: number
  llm_chars?: number
  llm_ms?: number
  token_usage?: { input: number; output: number; total: number } | null
  reasoning_chars?: number
  reasoning_preview?: string
  fragment_count?: number
  element_count?: number
  total_ms?: number
  reason?: string
  error?: string
}

export interface ErrorDiagnostic {
  node: string
  error: string
}

export interface SessionMetrics {
  node_count: number
  active_nodes: number
  skipped_nodes: number
  suggested_components?: string[]
  total_rag_ms: number
  total_llm_ms: number
  total_tokens: { input: number; output: number; total: number }
  fragment_total: number
  validation_steps: number
  validation_errors: number
  retry_count?: number
  max_retries?: number
  status: string
}

/** 精密模式：节点生成进度 */
export interface GeneratingNode {
  name: string
  label: string
  status: 'running' | 'done' | 'skipped' | 'error'
  detail: string
}

/** 会话列表项（由后端 storage/scenes 文件摘要生成） */
export interface SessionInfo {
  session_id: string
  /** 后端文件相对路径，如 "2026-08-02/session_xxx_名称.wild"，新格式含日期目录 */
  filename?: string
  name: string           // 从 blueprint.meta.name 提取
  building_type?: string // 建筑类型（如 "chinese_courtyard", "modern_house"）
  created_at: number
  updated_at: number
  elements_count: number
  components_count?: number  // 组件数量（区别于 elements）
  message_count?: number     // 消息数量
  turn_count?: number        // Agent 执行轮次数量
  status: 'saved' | 'draft' | 'generating'  // 会话状态
}
