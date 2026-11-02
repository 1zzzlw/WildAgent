import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

interface LoginUser { username: string; role: 'editor' | 'guest' }

export const useAuthStore = defineStore('auth', () => {
  const user = ref<LoginUser | null>(null)
  const initialized = ref(false)
  const canEdit = computed(() => user.value?.role === 'editor')
  const isGuest = computed(() => user.value?.role === 'guest')

  async function login(username?: string, password?: string) {
    const response = await fetch(`/api/auth/${username === undefined ? 'guest' : 'login'}`, {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: username === undefined ? undefined : JSON.stringify({ username, password }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(typeof data.detail === 'string' ? data.detail : '登录失败，请稍后重试')
    }
    user.value = await response.json()
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

  return { user, initialized, canEdit, isGuest, login, restore, logout }
})
