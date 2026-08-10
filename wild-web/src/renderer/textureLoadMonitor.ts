export type TextureLoadState = 'loading' | 'loaded' | 'error'

export interface TextureLoadRecord {
  uri: string
  channel: string
  state: TextureLoadState
  detail?: string
  updatedAt: number
}

type Listener = (records: TextureLoadRecord[]) => void

const records = new Map<string, TextureLoadRecord>()
const listeners = new Set<Listener>()

export function recordTextureLoad(
  uri: string,
  channel: string,
  state: TextureLoadState,
  detail?: string,
): void {
  records.set(`${channel}:${uri}`, { uri, channel, state, detail, updatedAt: Date.now() })
  const snapshot = getTextureLoadRecords()
  for (const listener of listeners) listener(snapshot)
}

export function getTextureLoadRecords(): TextureLoadRecord[] {
  return [...records.values()].sort((a, b) => b.updatedAt - a.updatedAt)
}

export function subscribeTextureLoads(listener: Listener): () => void {
  listeners.add(listener)
  listener(getTextureLoadRecords())
  return () => listeners.delete(listener)
}

export function clearTextureLoadRecords(): void {
  records.clear()
  for (const listener of listeners) listener([])
}
