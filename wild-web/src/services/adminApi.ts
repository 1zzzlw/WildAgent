import type { AccountUsage } from '../stores/authStore'

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface AdminUser {
  id: string; username: string; email: string; identity: 1 | 2; status: 'active' | 'blocked'
  created_at: number; usage: AccountUsage
  operations_remaining: number; ai_remaining: number
  operations_daily_limit: number; ai_daily_limit: number
}
export interface AuditLog {
  id: string; actor_id: string; actor_name: string; action: string; resource: string
  session_id?: string; request_id?: string; details: Record<string, unknown>; created_at: number
}
export interface AdminBlueprint {
  filename: string; name: string; owner_id?: string; owner_name?: string; session_id?: string
  elements_count: number; components_count: number; locked: boolean; updated_at: number; created_at: number
}
export interface BlueprintMetrics {
  footprint_area: number | null; footprint_width: number | null; footprint_depth: number | null
  footprint_kind: 'floor_union' | 'bounds' | 'unavailable'
}
export interface AdminStats {
  users: number; active_users: number; blocked_users: number; deleted_users: number; administrators: number
  new_users_7d: number; active_users_24h: number; blueprints: number; locked_blueprints: number; operations: number
}

export async function apiRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method, credentials: 'same-origin', cache: 'no-store',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data.detail
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('；') : '请求失败，请稍后重试')
  }
  return data as T
}

export function adminQuery(path: string, filters: Record<string, string | number | boolean | undefined>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  return `/api/admin/${path}?${params}`
}

export function sceneUrl(filename: string) {
  return '/api/scenes/' + filename.split('/').map(encodeURIComponent).join('/')
}

export function displayTime(value: number) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
export const actionLabels: Record<string, string> = {
  'blueprint.edit': '编辑蓝图', 'blueprint.save': '保存蓝图', 'blueprint.view': '查看蓝图',
  'blueprint.delete': '删除蓝图', 'blueprint.lock': '锁定蓝图', 'blueprint.unlock': '解锁蓝图',
  'user.update': '调整账号或额度', 'user.delete': '删除账号', 'config.update': '修改 AI API 配置',
  'ai.request': 'AI 对话请求', 'ai.generate': 'AI 生成', 'ai.edit': 'AI 修改', 'ai.chat': 'AI 问答',
  'ai.agent_reply': 'AI 回复', 'ai.error': 'AI 执行失败', 'ai.blueprint_generated': 'AI 蓝图交付',
  'ai.patch_proposal': 'AI 修改建议', 'ai.generation_stopped': '停止 AI 任务',
  'ai.usage': 'AI 每日额度消费',
  'blueprint.ai_apply': '应用 AI 修改', 'auth.login': '登录账号', 'auth.logout': '退出登录', 'auth.register': '注册账号',
  'http.post': '创建或提交资料', 'http.put': '更新会话资料', 'http.patch': '修订设计', 'http.delete': '删除会话',
}
