import { watch } from 'vue'
import { useAgentStore } from '../../stores/agentStore'
import { useAuthStore } from '../../stores/authStore'
import { usePresenceStore } from './store'
import type { SessionActivityState } from './types'

export const SESSION_IDLE_MS = 60_000
const ACTIVITY_REPORT_INTERVAL_MS = 10_000

/** 每条连接维护一份活动跟踪；心跳只续报状态，不计作用户操作。 */
export function trackSessionActivity(send: (state: SessionActivityState) => void) {
  const agent = useAgentStore(), auth = useAuthStore(), presence = usePresenceStore()
  let lastInput = Date.now(), lastReport = 0
  let lastActivity: SessionActivityState['activity'] = 'idle'
  let idleTimer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  const busy = () => agent.isProcessing || agent.currentTurns.some(turn => turn.status === 'running')

  function publish() {
    if (disposed) return
    const sessionId = auth.canEdit && presence.workspaceActive ? agent.currentSessionId || null : null
    lastActivity = !sessionId ? 'idle' : busy() ? 'generating'
      : document.hidden || Date.now() - lastInput >= SESSION_IDLE_MS ? 'idle' : 'active'
    lastReport = Date.now()
    send({ session_id: sessionId, activity: lastActivity })
  }

  function scheduleIdle() {
    const remaining = SESSION_IDLE_MS - (Date.now() - lastInput)
    if (remaining <= 0 || disposed || idleTimer !== undefined) return
    idleTimer = setTimeout(() => {
      idleTimer = undefined
      publish()
      scheduleIdle()
    }, remaining)
  }

  function onInput() {
    lastInput = Date.now()
    scheduleIdle()
    if (lastActivity === 'idle' || lastInput - lastReport >= ACTIVITY_REPORT_INTERVAL_MS) publish()
  }
  const events = ['pointerdown', 'pointermove', 'keydown', 'input', 'wheel'] as const
  for (const event of events) window.addEventListener(event, onInput, { passive: true })
  document.addEventListener('visibilitychange', publish)
  const stopSession = watch(() => [agent.currentSessionId, auth.user?.id, auth.canEdit, presence.workspaceActive], () => {
    lastInput = Date.now()
    scheduleIdle()
    publish()
  }, { flush: 'sync' })
  const stopBusy = watch(busy, publish, { flush: 'sync' })
  scheduleIdle()
  publish()

  return {
    publish,
    dispose() {
      disposed = true
      stopSession(); stopBusy()
      clearTimeout(idleTimer)
      for (const event of events) window.removeEventListener(event, onInput)
      document.removeEventListener('visibilitychange', publish)
    },
  }
}
