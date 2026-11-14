import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

interface LoginUser { id?: string; username: string; email?: string; identity?: 1 | 2; role: 'editor' | 'guest' }

export const useAuthStore = defineStore('auth', () => {
  const user = ref<LoginUser | null>(null)
  const initialized = ref(false)
  const canEdit = computed(() => user.value?.role === 'editor')
  const isGuest = computed(() => user.value?.role === 'guest')

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
    user.value = await authRequest(email === undefined ? 'guest' : 'login',
      email === undefined ? undefined : { email, password })
    initialized.value = true
  }

  async function sendEmailCode(email: string): Promise<{ resend_after: number; expires_in: number }> {
    return await authRequest('email-code', { email })
  }

  async function register(body: { username: string; email: string; password: string; confirm_password: string; code: string }) {
    user.value = await authRequest('register', body)
    initialized.value = true
  }

  async function restore() {
    try {
      const response = await fetch('/api/auth/session', { cache: 'no-store', credentials: 'same-origin' })
      user.value = response.ok ? await response.json() : null
    } catch { user.value = null }
    initialized.value = true
  }

  async function logout() {
    const response = await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
    if (!response.ok) throw new Error('退出失败，请稍后重试')
    user.value = null
  }

  return { user, initialized, canEdit, isGuest, login, sendEmailCode, register, restore, logout }
})
