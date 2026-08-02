export type PresenceConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting'

export const PRESENCE_VISITOR_NAME_CHANGED_EVENT = 'wild:presence-visitor-name-changed'

export const MAX_VISITOR_NAME_LENGTH = 24

export interface OnlineClientInfo {
  id: string
  display_name: string
  masked_ip: string
  region: string
  connected_at: number
}

export interface PresenceUpdateResponse {
  type: 'presence_update'
  online_count: number
  clients: OnlineClientInfo[]
}
