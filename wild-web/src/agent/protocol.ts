/**
 * Agent 通信协议工具函数
 * 
 * 提供构建 Agent 通信消息的辅助函数：
 * 
 * - createUserMessageRequest(): 创建用户消息请求
 *   - 自动生成 request_id
 *   - 包含场景上下文（scene_summary, selection）
 *   - 包含当前 revision
 * 
 * 消息包含的信息：
 * - message: 用户输入的文本
 * - scene_summary: 场景摘要（元素数量、类型、边界等）
 * - selection: 当前选中的构件 ID
 * - scene_revision: 当前场景版本号
 * - thinking_mode: 是否让模型开启思考并流式返回 reasoning_content
 * - procedural_materials_enabled: 是否允许 AI 自动生成程序化 Shader
 * 
 * 这些上下文信息帮助 Agent：
 * - 快速了解场景状态
 * - 理解用户指代（"这个"、"右边"等）
 * - 生成合适的修改建议
 * - 避免冲突（通过 revision）
 */

import type { UserMessageRequest, SceneSummary } from '../types/agent'

export const AGENT_PROTOCOL_VERSION = '1.0' as const

export function createUserMessageRequest(
  message: string,
  sessionId: string,
  sceneId: string | undefined,
  sceneRevision: number,
  sceneSummary: SceneSummary,
  selection: string[],
  blueprint?: Record<string, unknown>,
  thinkingMode: boolean = false,
  precisionMode: boolean = false,
  proceduralMaterialsEnabled: boolean = false,
  planMode: boolean = false,
  recentMessages: Array<{ role: 'user' | 'assistant'; content: string }> = [],
): UserMessageRequest {
  return {
    protocol_version: AGENT_PROTOCOL_VERSION,
    type: 'user_message',
    request_id: `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    session_id: sessionId,
    scene_id: sceneId,
    scene_revision: sceneRevision,
    message,
    scene_summary: sceneSummary,
    selection,
    blueprint,
    thinking_mode: thinkingMode,
    precision_mode: precisionMode,
    procedural_materials_enabled: proceduralMaterialsEnabled,
    plan_mode: planMode,
    recent_messages: recentMessages,
  }
}
