import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type UsageKind = 'operations' | 'modifications' | 'generations'
export type AccountUsage = Record<UsageKind, { remaining: number | null; used: number }>
export interface LoginUser {
  id?: string
  username: string
  email?: string
  identity?: 1 | 2
  role: 'editor' | 'guest'
  is_admin?: boolean
  usage?: AccountUsage
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<LoginUser | null>(null)
  const initialized = ref(false)
  const canEdit = computed(() => user.value?.role === 'editor')
  const isGuest = computed(() => user.value?.role === 'guest')
  const isAdmin = computed(() => canEdit.value && user.value?.identity === 2)
  let refreshRequest: Promise<void> | null = null
  let stateRevision = 0

  function adoptUser(value: LoginUser | null) { stateRevision++; user.value = value }

  function updateUsage(accountId: string, usage: AccountUsage) {
    if (user.value?.id === accountId) adoptUser({ ...user.value, usage })
  }

  function hasQuota(kind: UsageKind) {
    return canEdit.value && (isAdmin.value || (user.value?.usage?.[kind].remaining ?? 0) > 0)
  }

  async function refresh() {
    if (refreshRequest) return refreshRequest
    refreshRequest = (async () => {
      const revision = stateRevision
      try {
        const response = await fetch('/api/auth/session', { cache: 'no-store', credentials: 'same-origin' })
        const value = response.ok ? await response.json() : undefined
        if (value !== undefined && revision === stateRevision) adoptUser(value)
      } finally { refreshRequest = null }
    })()
    return refreshRequest
  }

  async function authRequest(path: string, body?: unknown) {
    const response = await fetch(`/api/auth/${path}`, {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = data.detail
      throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail)
        ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('；') : '请求失败，请稍后重试')
    }
    return data
  }

  async function login(email?: string, password?: string) {
    adoptUser(await authRequest(email === undefined ? 'guest' : 'login',
      email === undefined ? undefined : { email, password }))
    initialized.value = true
  }

  async function sendEmailCode(email: string): Promise<{ resend_after: number; expires_in: number }> {
    return await authRequest('email-code', { email })
  }

  async function register(body: { username: string; email: string; password: string; confirm_password: string; code: string }) {
    adoptUser(await authRequest('register', body))
    initialized.value = true
  }

  async function restore() {
    const revision = stateRevision
    try {
      const response = await fetch('/api/auth/session', { cache: 'no-store', credentials: 'same-origin' })
      const value = response.ok ? await response.json() : null
      if (revision === stateRevision) adoptUser(value)
    } catch { if (revision === stateRevision) adoptUser(null) }
    initialized.value = true
  }

  async function logout() {
    const response = await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
    if (!response.ok) throw new Error('退出失败，请稍后重试')
    adoptUser(null)
  }

  return { user, initialized, canEdit, isGuest, isAdmin, hasQuota, updateUsage, refresh, login, sendEmailCode, register, restore, logout }
})
