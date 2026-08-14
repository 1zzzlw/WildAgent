import type { WorldPackageManifest, WorldPackageSignature } from '../wild-core/src/materials'

export type WorldAssetTrust = 'builtin' | 'verified' | 'unverified'

export interface WorldAssetRequest {
  uri: string
  sha256: string
  mimeType: string
  maxBytes?: number
}

export interface ResolvedWorldAsset {
  bytes: Uint8Array
  mimeType: string
  sourceId: string
  fromCache: boolean
}

export interface WorldAssetResolver {
  id: string
  priority?: number
  canResolve(uri: string): boolean
  resolve(request: WorldAssetRequest): Promise<ResolvedWorldAsset>
}

const DEFAULT_MAX_BYTES = 64 * 1024 * 1024
const CACHE_NAME = 'wild-world-assets-v1'
const resolvers: WorldAssetResolver[] = []
let decentralizedGateways = ['https://ipfs.io/ipfs/', 'https://cloudflare-ipfs.com/ipfs/']

export function registerWorldAssetResolver(resolver: WorldAssetResolver): () => void {
  if (!resolver.id.trim()) throw new Error('Asset resolver id cannot be empty')
  if (resolvers.some(item => item.id === resolver.id)) {
    throw new Error(`Asset resolver already registered: ${resolver.id}`)
  }
  resolvers.push(resolver)
  resolvers.sort((left, right) => (right.priority || 0) - (left.priority || 0))
  return () => {
    const index = resolvers.indexOf(resolver)
    if (index >= 0) resolvers.splice(index, 1)
  }
}

export async function resolveWorldAsset(request: WorldAssetRequest): Promise<ResolvedWorldAsset> {
  const cached = await readCachedAsset(request)
  if (cached) return cached
  const resolver = resolvers.find(item => item.canResolve(request.uri))
  if (!resolver) throw new Error(`没有资源解析器可以处理: ${request.uri}`)
  const resolved = await resolver.resolve(request)
  await verifyAsset(resolved.bytes, request)
  await cacheAsset(request, resolved)
  return resolved
}

export function getWorldAssetResolverIds(): string[] {
  return resolvers.map(item => item.id)
}

export function configureDecentralizedGateways(gateways: string[]): void {
  const normalized = gateways
    .filter(value => /^https:\/\//i.test(value))
    .map(value => value.endsWith('/') ? value : `${value}/`)
  if (!normalized.length) throw new Error('至少需要一个 HTTPS 去中心化网关')
  decentralizedGateways = [...new Set(normalized)]
}

/** 包清单只签名声明数据；GPU/脚本源码仍由解析器硬拒绝。 */
export async function verifyWorldPackageSignature(
  manifest: WorldPackageManifest,
): Promise<WorldAssetTrust> {
  const signature = manifest.signature
  if (!signature) return 'unverified'
  if (!globalThis.crypto?.subtle) return 'unverified'
  try {
    const publicKey = await crypto.subtle.importKey(
      'raw',
      ownedArrayBuffer(decodeBase64(signature.publicKey)),
      { name: signature.algorithm },
      false,
      ['verify'],
    )
    const valid = await crypto.subtle.verify(
      { name: signature.algorithm },
      publicKey,
      ownedArrayBuffer(decodeBase64(signature.value)),
      new TextEncoder().encode(canonicalManifest(manifest)),
    )
    return valid ? 'verified' : 'unverified'
  } catch {
    return 'unverified'
  }
}

registerWorldAssetResolver({
  id: 'builtin:http-cas-v1',
  priority: 0,
  canResolve: uri => /^https?:\/\//i.test(uri) || (/^\//.test(uri) && !/^\/\//.test(uri)),
  resolve: request => fetchHttpAsset(request, request.uri, 'builtin:http-cas-v1'),
})

registerWorldAssetResolver({
  id: 'builtin:ipfs-gateway-v1',
  priority: 10,
  canResolve: uri => /^ipfs:\/\/[a-zA-Z0-9]+(?:\/[a-zA-Z0-9._~-]+)*$/.test(uri),
  async resolve(request) {
    const path = request.uri.slice('ipfs://'.length)
    const failures: string[] = []
    for (const gateway of decentralizedGateways) {
      try {
        return await fetchHttpAsset(request, `${gateway}${path}`, 'builtin:ipfs-gateway-v1')
      } catch (error) {
        failures.push(error instanceof Error ? error.message : String(error))
      }
    }
    throw new Error(`IPFS 多来源恢复失败: ${failures.join(' | ')}`)
  },
})

registerWorldAssetResolver({
  id: 'builtin:data-image-v1',
  priority: -10,
  canResolve: uri => /^data:image\/(png|jpeg|webp);base64,/i.test(uri),
  async resolve(request) {
    const encoded = request.uri.slice(request.uri.indexOf(',') + 1)
    const decoded = atob(encoded)
    const bytes = Uint8Array.from(decoded, char => char.charCodeAt(0))
    if (bytes.byteLength > (request.maxBytes || DEFAULT_MAX_BYTES)) throw new Error('Data URI 资源过大')
    return { bytes, mimeType: request.mimeType, sourceId: 'builtin:data-image-v1', fromCache: false }
  },
})

async function verifyAsset(bytes: Uint8Array, request: WorldAssetRequest): Promise<void> {
  if (bytes.byteLength > (request.maxBytes || DEFAULT_MAX_BYTES)) throw new Error('资源超过大小限制')
  const actual = await sha256Hex(bytes)
  const expected = normalizeHash(request.sha256)
  if (actual !== expected) throw new Error(`资源哈希不匹配: ${request.uri}`)
}

async function fetchHttpAsset(
  request: WorldAssetRequest,
  uri: string,
  sourceId: string,
): Promise<ResolvedWorldAsset> {
  const sameOrigin = uri.startsWith('/')
    || typeof location !== 'undefined' && new URL(uri, location.href).origin === location.origin
  const response = await fetch(uri, {
    credentials: sameOrigin ? 'same-origin' : 'omit',
    redirect: 'error',
    cache: 'no-store',
  })
  if (!response.ok) throw new Error(`资源请求失败 (${response.status}): ${uri}`)
  const declaredSize = Number(response.headers.get('content-length') || 0)
  const limit = request.maxBytes || DEFAULT_MAX_BYTES
  if (declaredSize > limit) throw new Error(`资源超过 ${limit} 字节限制`)
  const bytes = new Uint8Array(await response.arrayBuffer())
  if (bytes.byteLength > limit) throw new Error(`资源超过 ${limit} 字节限制`)
  return {
    bytes,
    mimeType: response.headers.get('content-type')?.split(';')[0] || request.mimeType,
    sourceId,
    fromCache: false,
  }
}

async function readCachedAsset(request: WorldAssetRequest): Promise<ResolvedWorldAsset | undefined> {
  if (typeof caches === 'undefined') return undefined
  try {
    const cache = await caches.open(CACHE_NAME)
    const response = await cache.match(cacheKey(request.sha256))
    if (!response) return undefined
    const bytes = new Uint8Array(await response.arrayBuffer())
    await verifyAsset(bytes, request)
    return { bytes, mimeType: request.mimeType, sourceId: 'builtin:offline-cache-v1', fromCache: true }
  } catch {
    return undefined
  }
}

async function cacheAsset(request: WorldAssetRequest, asset: ResolvedWorldAsset): Promise<void> {
  if (typeof caches === 'undefined') return
  try {
    const cache = await caches.open(CACHE_NAME)
    await cache.put(cacheKey(request.sha256), new Response(ownedArrayBuffer(asset.bytes), {
      headers: { 'content-type': asset.mimeType },
    }))
  } catch {
    // 隐私模式或配额不足时不影响当前渲染。
  }
}

function cacheKey(hash: string): string {
  const origin = typeof location === 'undefined' ? 'https://wild.local' : location.origin
  return `${origin}/__wild_asset_cache__/${normalizeHash(hash)}`
}

function normalizeHash(value: string): string {
  return value.toLowerCase().replace(/^sha256:/, '')
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', ownedArrayBuffer(bytes))
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('')
}

function canonicalManifest(manifest: WorldPackageManifest): string {
  const value = structuredClone(manifest) as WorldPackageManifest & { signature?: WorldPackageSignature }
  delete value.signature
  return stableStringify(value)
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>)
      .filter(([, child]) => child !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, child]) => `${JSON.stringify(key)}:${stableStringify(child)}`)
      .join(',')}}`
  }
  return JSON.stringify(value)
}

function decodeBase64(value: string): Uint8Array {
  const decoded = atob(value)
  return Uint8Array.from(decoded, char => char.charCodeAt(0))
}

function ownedArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.slice().buffer as ArrayBuffer
}
