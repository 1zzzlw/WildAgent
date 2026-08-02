import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  OnlineClientInfo,
  PresenceConnectionStatus,
} from './types'
import {
  MAX_VISITOR_NAME_LENGTH,
  PRESENCE_VISITOR_NAME_CHANGED_EVENT,
} from './types'

const VISITOR_NAME_STORAGE_KEY = 'wild_presence_visitor_name'

export function normalizeVisitorName(value: unknown): string {
  if (typeof value !== 'string') return ''
  return value.trim().replace(/\s+/g, ' ').slice(0, MAX_VISITOR_NAME_LENGTH)
}

function loadVisitorName(): string {
  if (typeof localStorage === 'undefined') return ''
  try {
    return normalizeVisitorName(localStorage.getItem(VISITOR_NAME_STORAGE_KEY))
  } catch {
    return ''
  }
}

export const usePresenceStore = defineStore('presence', () => {
  const supported = ref(false)
  const connectionStatus = ref<PresenceConnectionStatus>('disconnected')
  const visitorName = ref(loadVisitorName())
  const onlineCount = ref(0)
  const onlineClients = ref<OnlineClientInfo[]>([])
  const hasVisitorName = computed(() => visitorName.value.length > 0)
  const isConnected = computed(() => connectionStatus.value === 'connected')

  function setVisitorName(value: string) {
    const normalized = normalizeVisitorName(value)
    if (!normalized) return false
    visitorName.value = normalized
    try {
      localStorage.setItem(VISITOR_NAME_STORAGE_KEY, normalized)
    } catch {
      // 浏览器禁止本地存储时仍允许本次页面使用该名称。
    }
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent(
        PRESENCE_VISITOR_NAME_CHANGED_EVENT,
        { detail: normalized },
      ))
    }
    return true
  }

  function setConnectionStatus(status: PresenceConnectionStatus) {
    connectionStatus.value = status
    if (status !== 'connected') clearSnapshot()
  }

  function updatePresence(count: number, clients: OnlineClientInfo[] = []) {
    supported.value = true
    onlineCount.value = Number.isFinite(count)
      ? Math.max(0, Math.floor(count))
      : 0
    onlineClients.value = Array.isArray(clients) ? clients : []
  }

  function clearSnapshot() {
    onlineCount.value = 0
    onlineClients.value = []
  }

  return {
    supported,
    connectionStatus,
    visitorName,
    hasVisitorName,
    onlineCount,
    onlineClients,
    isConnected,
    setVisitorName,
    setConnectionStatus,
    updatePresence,
    clearSnapshot,
  }
})
