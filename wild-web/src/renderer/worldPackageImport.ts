import { BlobReader, Uint8ArrayWriter, ZipReader } from '@zip.js/zip.js'
import type {
  MaterialPackageChannel,
  WildMaterialPackageManifest,
  WorldPackageManifest,
} from '../wild-core/src/materials'
import { parseWorldPackageManifest } from '../wild-core/src/materials'

export interface WorldPackageFile {
  name: string
  size: number
  type?: string
  text(): Promise<string>
  arrayBuffer?(): Promise<ArrayBuffer>
  slice?(start?: number, end?: number): Blob
}

export type WorldPackageKind = 'material' | 'look'

export function getWorldPackageKind(manifest: WorldPackageManifest): WorldPackageKind {
  return manifest.format === 'wild.material-package' ? 'material' : 'look'
}

export function assertWorldPackageKind(
  manifest: WorldPackageManifest,
  expectedKind: WorldPackageKind,
): void {
  if (getWorldPackageKind(manifest) === expectedKind) return
  throw new Error(expectedKind === 'material'
    ? '素材面板只允许导入 wild.material-package 清单'
    : '光影设置只允许导入 wild.render-profile 清单')
}

export interface DecodedWorldPackage {
  manifest: WorldPackageManifest
  source: 'json' | 'zip'
  /** 包内稳定 URI 到当前会话 Blob URL 的映射。 */
  resources: Record<string, string>
  dispose(): void
}

export interface WorldPackageDecoder {
  id: string
  priority?: number
  canDecode(file: WorldPackageFile): boolean | Promise<boolean>
  decode(file: WorldPackageFile): Promise<DecodedWorldPackage>
}

const MAX_JSON_PACKAGE_BYTES = 2 * 1024 * 1024
const MAX_ZIP_PACKAGE_BYTES = 128 * 1024 * 1024
const MAX_ZIP_ENTRY_BYTES = 64 * 1024 * 1024
const MAX_ZIP_TOTAL_BYTES = 256 * 1024 * 1024
const MAX_ZIP_ENTRIES = 512
const decoders: WorldPackageDecoder[] = []

export function registerWorldPackageDecoder(decoder: WorldPackageDecoder): () => void {
  if (!decoder.id.trim()) throw new Error('World package decoder id cannot be empty')
  if (decoders.some(item => item.id === decoder.id)) {
    throw new Error(`World package decoder already registered: ${decoder.id}`)
  }
  decoders.push(decoder)
  decoders.sort((left, right) => (right.priority || 0) - (left.priority || 0))
  return () => {
    const index = decoders.indexOf(decoder)
    if (index >= 0) decoders.splice(index, 1)
  }
}

export async function decodeWorldPackageBundle(file: WorldPackageFile): Promise<DecodedWorldPackage> {
  for (const decoder of decoders) {
    if (await decoder.canDecode(file)) return await decoder.decode(file)
  }
  throw new Error(`没有可用的包解码器: ${file.name}`)
}

/** 兼容既有调用；需要包内资源生命周期时应使用 decodeWorldPackageBundle。 */
export async function decodeWorldPackage(file: WorldPackageFile): Promise<WorldPackageManifest> {
  return (await decodeWorldPackageBundle(file)).manifest
}

export function getWorldPackageDecoderIds(): string[] {
  return decoders.map(decoder => decoder.id)
}

registerWorldPackageDecoder({
  id: 'builtin:zip64-package-v1',
  priority: 100,
  async canDecode(file) {
    if (!file.arrayBuffer || file.size < 4 || file.size > MAX_ZIP_PACKAGE_BYTES) return false
    const header = file.slice ? await file.slice(0, 4).arrayBuffer() : await file.arrayBuffer()
    const bytes = new Uint8Array(header)
    return bytes[0] === 0x50 && bytes[1] === 0x4b
      && ((bytes[2] === 0x03 && bytes[3] === 0x04)
        || (bytes[2] === 0x05 && bytes[3] === 0x06)
        || (bytes[2] === 0x07 && bytes[3] === 0x08))
  },
  async decode(file) {
    if (!file.arrayBuffer) throw new Error('当前文件对象不支持二进制读取')
    if (file.size > MAX_ZIP_PACKAGE_BYTES) throw new Error('WILD 包超过 128 MB 限制')
    const blob = new Blob([await file.arrayBuffer()], { type: 'application/zip' })
    const reader = new ZipReader(new BlobReader(blob), { useWebWorkers: false })
    const resourceUrls: string[] = []
    try {
      const rawEntries = await reader.getEntries()
      if (rawEntries.length > MAX_ZIP_ENTRIES) throw new Error('WILD 包文件数量超过 512 个限制')
      const entries = rawEntries.filter(entry => !entry.directory)
      let totalSize = 0
      const byPath = new Map<string, (typeof entries)[number]>()
      for (const entry of entries) {
        const path = normalizeArchivePath(entry.filename)
        if (entry.encrypted) throw new Error(`不支持加密的包内文件: ${path}`)
        const size = Number(entry.uncompressedSize || 0)
        if (!Number.isSafeInteger(size) || size < 0 || size > MAX_ZIP_ENTRY_BYTES) {
          throw new Error(`包内文件大小不安全: ${path}`)
        }
        totalSize += size
        if (totalSize > MAX_ZIP_TOTAL_BYTES) throw new Error('WILD 包解压后超过 256 MB 限制')
        if (byPath.has(path)) throw new Error(`包内路径重复: ${path}`)
        byPath.set(path, entry)
      }

      const manifests = entries.filter(entry => /(^|\/)(manifest\.json|[^/]+\.(wildmat|wildlook))$/i.test(entry.filename))
      if (manifests.length !== 1) throw new Error('ZIP 包必须且只能包含一个 manifest.json/.wildmat/.wildlook 清单')
      const manifestBytes = await readEntry(manifests[0])
      if (manifestBytes.byteLength > MAX_JSON_PACKAGE_BYTES) throw new Error('包清单超过 2 MB 限制')
      const manifest = parseWorldPackageManifest(new TextDecoder().decode(manifestBytes))
      const resources: Record<string, string> = {}

      if (manifest.format === 'wild.material-package') {
        for (const channel of Object.values(manifest.channels)) {
          if (!channel) continue
          const candidates = [channel, ...Object.values(channel.variants || {}).filter(Boolean)]
          for (const resource of candidates) {
            if (!resource.uri.startsWith('package:/')) continue
            const path = normalizeArchivePath(resource.uri.slice('package:/'.length))
            const entry = byPath.get(path)
            if (!entry) throw new Error(`包内资源不存在: ${path}`)
            const bytes = await readEntry(entry)
            if (resource.byteSize !== undefined && resource.byteSize !== bytes.byteLength) {
              throw new Error(`包内资源字节数不匹配: ${path}`)
            }
            await verifyChannel(bytes, resource, path)
            const objectUrl = URL.createObjectURL(new Blob([ownedArrayBuffer(bytes)], { type: resource.mimeType }))
            resources[resource.uri] = objectUrl
            resourceUrls.push(objectUrl)
          }
        }
      }

      return {
        manifest,
        source: 'zip',
        resources,
        dispose: () => resourceUrls.splice(0).forEach(url => URL.revokeObjectURL(url)),
      }
    } catch (error) {
      resourceUrls.splice(0).forEach(url => URL.revokeObjectURL(url))
      throw error
    } finally {
      await reader.close()
    }
  },
})

registerWorldPackageDecoder({
  id: 'builtin:json-manifest-v1',
  priority: -100,
  canDecode: file => /\.(wildmat|wildlook|json)$/i.test(file.name),
  async decode(file) {
    if (file.size > MAX_JSON_PACKAGE_BYTES) {
      throw new Error(`JSON 清单超过 ${MAX_JSON_PACKAGE_BYTES} 字节限制`)
    }
    const manifest = parseWorldPackageManifest(await file.text())
    if (manifest.format === 'wild.material-package'
      && Object.values(manifest.channels).some(channel => channel && [
        channel,
        ...Object.values(channel.variants || {}).filter(Boolean),
      ].some(resource => resource.uri.startsWith('package:/')))) {
      throw new Error('JSON 清单不能引用包内路径；请使用标准 ZIP/ZIP64 .wildmat')
    }
    return {
      manifest,
      source: 'json',
      resources: {},
      dispose: () => {},
    }
  },
})

async function readEntry(entry: { getData?: (writer: Uint8ArrayWriter) => Promise<Uint8Array> }): Promise<Uint8Array> {
  if (!entry.getData) throw new Error('包内目录不能作为资源读取')
  return await entry.getData(new Uint8ArrayWriter())
}

function normalizeArchivePath(value: string): string {
  const normalized = value.replaceAll('\\', '/').replace(/^\.\//, '')
  if (!normalized || normalized.startsWith('/') || /^[a-zA-Z]:/.test(normalized)) {
    throw new Error(`包内路径非法: ${value}`)
  }
  const parts = normalized.split('/')
  if (parts.some(part => !part || part === '.' || part === '..')) {
    throw new Error(`包内路径包含穿越或空目录: ${value}`)
  }
  return parts.join('/')
}

async function verifyChannel(
  bytes: Uint8Array,
  channel: Omit<MaterialPackageChannel, 'variants'>,
  path: string,
): Promise<void> {
  const actualHash = await sha256Hex(bytes)
  const expectedHash = channel.sha256.toLowerCase().replace(/^sha256:/, '')
  if (actualHash !== expectedHash) throw new Error(`包内资源哈希不匹配: ${path}`)
  const detectedMime = detectImageMime(bytes)
  if (detectedMime !== channel.mimeType) {
    throw new Error(`包内资源类型与清单不一致: ${path} (${detectedMime || 'unknown'})`)
  }
}

function detectImageMime(bytes: Uint8Array): MaterialPackageChannel['mimeType'] | undefined {
  if (bytes.length >= 12
    && bytes[0] === 0xab && bytes[1] === 0x4b && bytes[2] === 0x54 && bytes[3] === 0x58
    && bytes[4] === 0x20 && bytes[5] === 0x32 && bytes[6] === 0x30 && bytes[7] === 0xbb) return 'image/ktx2'
  if (bytes.length >= 8
    && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) return 'image/png'
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'image/jpeg'
  if (bytes.length >= 12
    && String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF'
    && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP') return 'image/webp'
  return undefined
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', ownedArrayBuffer(bytes))
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('')
}

function ownedArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.slice().buffer as ArrayBuffer
}

export function materialPackageChannels(
  manifest: WildMaterialPackageManifest,
): Array<[keyof WildMaterialPackageManifest['channels'], MaterialPackageChannel]> {
  return Object.entries(manifest.channels)
    .filter((entry): entry is [keyof WildMaterialPackageManifest['channels'], MaterialPackageChannel] => Boolean(entry[1]))
}
