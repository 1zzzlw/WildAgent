export type PresenceConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting'

export const PRESENCE_VISITOR_NAME_CHANGED_EVENT = 'wild:presence-visitor-name-changed'

export const MAX_VISITOR_NAME_LENGTH = 24

export type SessionActivity = 'active' | 'idle' | 'generating'

export interface SessionActivityState {
  session_id: string | null
  activity: SessionActivity
}

export interface OnlineClientInfo {
  id: string
  display_name: string
  masked_ip: string
  region: string
  connected_at: number
  user_id?: string | null
  username?: string | null
  can_edit?: boolean
  session_id?: string | null
  activity?: SessionActivity
}

export interface PresenceUpdateResponse {
  protocol_version: '1.0'
  type: 'presence_update'
  online_count: number
  clients: OnlineClientInfo[]
  session_activity_supported?: boolean
}
