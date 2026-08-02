export type PresenceConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting'

export interface OnlineClientInfo {
  id: string
  masked_ip: string
  region: string
  connected_at: number
}

export interface PresenceUpdateResponse {
  type: 'presence_update'
  online_count: number
  clients: OnlineClientInfo[]
}
