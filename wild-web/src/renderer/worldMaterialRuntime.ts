import type { WildMaterialPackageManifest } from '../wild-core/src/materials'
import { worldLookRuntime } from './worldLookRuntime'
import { getWorldRenderingState } from './worldEnvironmentRuntime'

export interface RegisteredMaterialPackage {
  manifest: WildMaterialPackageManifest
  unsupportedFeatures: string[]
  resources: Record<string, string>
  importedAt: number
  trust: 'builtin' | 'verified' | 'unverified'
}

type MaterialPackageListener = (packages: RegisteredMaterialPackage[]) => void

class WorldMaterialRuntime {
  private packages = new Map<string, RegisteredMaterialPackage>()
  private contentHashes = new Map<string, string>()
  private disposers = new Map<string, () => void>()
  private listeners = new Set<MaterialPackageListener>()

  registerMaterialPackage(
    manifest: WildMaterialPackageManifest,
    options: {
      resources?: Record<string, string>
      dispose?: () => void
      trust?: RegisteredMaterialPackage['trust']
    } = {},
  ): RegisteredMaterialPackage {
    const existing = this.packages.get(manifest.packageId)
    if (existing && contentKey(existing.manifest.contentHash) === contentKey(manifest.contentHash)) return existing
    if (existing) {
      throw new Error(`Material package id conflict: ${manifest.packageId}`)
    }
    const hashKey = contentKey(manifest.contentHash)
    const duplicateId = this.contentHashes.get(hashKey)
    if (duplicateId) return this.packages.get(duplicateId)!
    const registered = {
      manifest,
      unsupportedFeatures: (manifest.requiredFeatures || [])
        .filter(id => !worldLookRuntime.hasShaderFeature(id)),
      resources: options.resources || {},
      importedAt: Date.now(),
      trust: options.trust || 'unverified',
    }
    this.packages.set(manifest.packageId, registered)
    this.contentHashes.set(hashKey, manifest.packageId)
    if (options.dispose) this.disposers.set(manifest.packageId, options.dispose)
    this.emit()
    return registered
  }

  removeMaterialPackage(packageId: string): boolean {
    const registered = this.packages.get(packageId)
    const removed = Boolean(registered) && this.packages.delete(packageId)
    if (registered) this.contentHashes.delete(contentKey(registered.manifest.contentHash))
    this.disposers.get(packageId)?.()
    this.disposers.delete(packageId)
    if (removed) this.emit()
    return removed
  }

  getMaterialPackage(packageId: string): RegisteredMaterialPackage | undefined {
    return this.packages.get(packageId)
  }

  listMaterialPackages(): RegisteredMaterialPackage[] {
    return [...this.packages.values()]
  }

  /** 将 Blueprint 中稳定的 wildpkg URI 解析为当前会话真实资源地址。 */
  resolvePackageUri(uri: string): string | undefined {
    const match = /^wildpkg:\/\/([^/]+)\/([a-zA-Z][a-zA-Z0-9]*)$/.exec(uri)
    if (!match) return undefined
    const packageId = decodeURIComponent(match[1])
    const channelName = match[2] as keyof WildMaterialPackageManifest['channels']
    const registered = this.packages.get(packageId)
    const channel = registered?.manifest.channels[channelName]
    if (!registered || !channel) return undefined
    const quality = getWorldRenderingState().surfaceQuality
    const variant = quality === 'fallback' ? undefined : channel.variants?.[quality]
    const resource = variant || channel
    return registered.resources[resource.uri] || resource.uri
  }

  subscribe(listener: MaterialPackageListener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private emit(): void {
    const snapshot = this.listMaterialPackages()
    this.listeners.forEach(listener => listener(snapshot))
  }
}

export const worldMaterialRuntime = new WorldMaterialRuntime()
export const registerMaterialPackage = worldMaterialRuntime.registerMaterialPackage.bind(
  worldMaterialRuntime,
)

export function createWorldPackageChannelUri(packageId: string, channel: string): string {
  return `wildpkg://${encodeURIComponent(packageId)}/${channel}`
}

function contentKey(value: string): string {
  return value.toLowerCase().replace(/^sha256:/, '')
}
