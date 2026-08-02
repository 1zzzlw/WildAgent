import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  OnlineClientInfo,
  PresenceConnectionStatus,
} from './types'


export const usePresenceStore = defineStore('presence', () => {
  const supported = ref(false)
  const connectionStatus = ref<PresenceConnectionStatus>('disconnected')
  const onlineCount = ref(0)
  const onlineClients = ref<OnlineClientInfo[]>([])
  const isConnected = computed(() => connectionStatus.value === 'connected')

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
    onlineCount,
    onlineClients,
    isConnected,
    setConnectionStatus,
    updatePresence,
    clearSnapshot,
  }
})
