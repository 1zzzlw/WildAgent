import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  WildMaterialPackageManifest,
  WorldEnvironmentState,
  WorldLookProfileManifest,
} from '../wild-core/src/materials'
import type { WorldRenderingState } from '../renderer/worldEnvironmentRuntime'
import {
  getWorldEnvironmentState,
  getWorldRenderingState,
  updateWorldEnvironmentState,
  updateWorldRenderingState,
} from '../renderer/worldEnvironmentRuntime'
import { worldLookRuntime } from '../renderer/worldLookRuntime'
import {
  type RegisteredMaterialPackage,
  worldMaterialRuntime,
} from '../renderer/worldMaterialRuntime'
import {
  assertWorldPackageKind,
  decodeWorldPackageBundle,
  type DecodedWorldPackage,
  type WorldPackageKind,
} from '../renderer/worldPackageImport'
import {
  listPersistedWorldPackages,
  persistWorldPackage,
  removePersistedWorldPackage,
} from '../renderer/worldPackagePersistence'
import {
  resolveWorldAsset,
  verifyWorldPackageSignature,
} from '../renderer/worldAssetResolver'

const ACTIVE_LOOK_KEY = 'wild_world_active_look_v1'
const ENVIRONMENT_KEY = 'wild_world_environment_v1'
const RENDERING_KEY = 'wild_world_rendering_v1'

export const useWorldPackageStore = defineStore('worldPackages', () => {
  const materialPackages = ref<RegisteredMaterialPackage[]>([])
  const lookProfiles = ref<WorldLookProfileManifest[]>(worldLookRuntime.listProfiles())
  const activeProfileId = ref(worldLookRuntime.getActiveProfile().profileId)
  const environment = ref({ ...getWorldEnvironmentState() })
  const rendering = ref({ ...getWorldRenderingState() })
  const loading = ref(false)
  const initialized = ref(false)
  const error = ref('')
  const bundles = new Map<string, DecodedWorldPackage>()
  let subscribed = false

  async function initialize(): Promise<void> {
    if (initialized.value || loading.value) return
    loading.value = true
    error.value = ''
    subscribeRuntime()
    restoreSettings()
    try {
      const records = await listPersistedWorldPackages()
      for (const record of records) {
        try {
          const file = new File([record.blob], record.name, { type: record.type })
          await decodeAndRegister(file, false)
        } catch (cause) {
          console.warn(`恢复世界包失败: ${record.name}`, cause)
        }
      }
      initialized.value = true
      await restorePreferredLook()
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '恢复世界包失败'
    } finally {
      loading.value = false
    }
  }

  async function importFile(file: File, expectedKind?: WorldPackageKind): Promise<string> {
    loading.value = true
    error.value = ''
    try {
      const id = await decodeAndRegister(file, true, expectedKind)
      return id
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '世界包导入失败'
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function activateLook(profileId: string): Promise<void> {
    error.value = ''
    try {
      await worldLookRuntime.activateProfile(profileId)
      activeProfileId.value = profileId
      safeStorageSet(ACTIVE_LOOK_KEY, profileId)
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '光影包启用失败'
      throw cause
    }
  }

  async function restorePreferredLook(): Promise<void> {
    const preferred = safeStorageGet(ACTIVE_LOOK_KEY)
    if (!preferred || preferred === activeProfileId.value || !worldLookRuntime.getProfile(preferred)) return
    try {
      await activateLook(preferred)
    } catch {
      // 视口尚未初始化时保留默认光影；初始化完成后可再次调用。
    }
  }

  async function removeLook(profileId: string): Promise<boolean> {
    if (profileId === 'builtin:default') return false
    if (activeProfileId.value === profileId) {
      await worldLookRuntime.restoreDefault()
      activeProfileId.value = 'builtin:default'
      safeStorageSet(ACTIVE_LOOK_KEY, 'builtin:default')
    }
    const removed = worldLookRuntime.removeProfile(profileId)
    if (!removed) return false
    bundles.get(packageKey('look', profileId))?.dispose()
    bundles.delete(packageKey('look', profileId))
    await removePersistedWorldPackage(packageKey('look', profileId))
    lookProfiles.value = worldLookRuntime.listProfiles()
    return true
  }

  async function removeMaterial(packageId: string): Promise<boolean> {
    const removed = worldMaterialRuntime.removeMaterialPackage(packageId)
    if (!removed) return false
    bundles.delete(packageKey('material', packageId))
    await removePersistedWorldPackage(packageKey('material', packageId))
    materialPackages.value = worldMaterialRuntime.listMaterialPackages()
    return true
  }

  function setEnvironment(patch: Partial<WorldEnvironmentState>): void {
    environment.value = { ...updateWorldEnvironmentState(patch) }
    safeStorageSet(ENVIRONMENT_KEY, JSON.stringify(environment.value))
  }

  function setRendering(patch: Partial<WorldRenderingState>): void {
    rendering.value = { ...updateWorldRenderingState(patch) }
    safeStorageSet(RENDERING_KEY, JSON.stringify(rendering.value))
  }

  async function decodeAndRegister(
    file: File,
    persist: boolean,
    expectedKind?: WorldPackageKind,
  ): Promise<string> {
    const bundle = await decodeWorldPackageBundle(file)
    if (expectedKind) {
      try {
        assertWorldPackageKind(bundle.manifest, expectedKind)
      } catch (cause) {
        bundle.dispose()
        throw cause
      }
    }
    await hydrateExternalResources(bundle)
    const trust = await verifyWorldPackageSignature(bundle.manifest)
    try {
      if (bundle.manifest.format === 'wild.material-package') {
        const manifest = bundle.manifest as WildMaterialPackageManifest
        const existing = worldMaterialRuntime.getMaterialPackage(manifest.packageId)
        if (existing && normalizeHash(existing.manifest.contentHash) === normalizeHash(manifest.contentHash)) {
          bundle.dispose()
          return packageKey('material', manifest.packageId)
        }
        const registered = worldMaterialRuntime.registerMaterialPackage(manifest, {
          resources: bundle.resources,
          dispose: bundle.dispose,
          trust,
        })
        if (registered.manifest.packageId !== manifest.packageId) {
          bundle.dispose()
          return packageKey('material', registered.manifest.packageId)
        }
        const key = packageKey('material', manifest.packageId)
        bundles.set(key, bundle)
        if (persist) await persistFile(key, file)
        materialPackages.value = worldMaterialRuntime.listMaterialPackages()
        return key
      }

      const manifest = bundle.manifest as WorldLookProfileManifest
      const existing = worldLookRuntime.getProfile(manifest.profileId)
      if (existing && JSON.stringify(existing) === JSON.stringify(manifest)) {
        bundle.dispose()
        return packageKey('look', manifest.profileId)
      }
      worldLookRuntime.registerProfile(manifest)
      const key = packageKey('look', manifest.profileId)
      bundles.set(key, bundle)
      if (persist) await persistFile(key, file)
      lookProfiles.value = worldLookRuntime.listProfiles()
      return key
    } catch (cause) {
      bundle.dispose()
      throw cause
    }
  }

  async function hydrateExternalResources(bundle: DecodedWorldPackage): Promise<void> {
    if (bundle.manifest.format !== 'wild.material-package') return
    const objectUrls: string[] = []
    try {
      for (const channel of Object.values(bundle.manifest.channels)) {
        if (!channel) continue
        const resources = [channel, ...Object.values(channel.variants || {}).filter(Boolean)]
        for (const resource of resources) {
          if (bundle.resources[resource.uri]) continue
          const resolved = await resolveWorldAsset({
            uri: resource.uri,
            sha256: resource.sha256,
            mimeType: resource.mimeType,
            maxBytes: resource.byteSize,
          })
          const objectUrl = URL.createObjectURL(new Blob(
            [resolved.bytes.slice().buffer as ArrayBuffer],
            { type: resource.mimeType },
          ))
          bundle.resources[resource.uri] = objectUrl
          objectUrls.push(objectUrl)
        }
      }
    } catch (cause) {
      objectUrls.forEach(url => URL.revokeObjectURL(url))
      bundle.dispose()
      throw cause
    }
    if (!objectUrls.length) return
    const disposeBundle = bundle.dispose
    bundle.dispose = () => {
      objectUrls.splice(0).forEach(url => URL.revokeObjectURL(url))
      disposeBundle()
    }
  }

  async function persistFile(id: string, file: File): Promise<void> {
    await persistWorldPackage({
      id,
      name: file.name,
      type: file.type,
      blob: file,
      importedAt: Date.now(),
    })
  }

  function subscribeRuntime(): void {
    if (subscribed) return
    subscribed = true
    worldMaterialRuntime.subscribe(packages => { materialPackages.value = packages })
    worldLookRuntime.subscribe(profile => {
      activeProfileId.value = profile.profileId
      lookProfiles.value = worldLookRuntime.listProfiles()
    })
  }

  function restoreSettings(): void {
    const savedEnvironment = safeJson(safeStorageGet(ENVIRONMENT_KEY))
    if (savedEnvironment) setEnvironment(savedEnvironment as Partial<WorldEnvironmentState>)
    const savedRendering = safeJson(safeStorageGet(RENDERING_KEY))
    if (savedRendering) setRendering(savedRendering as Partial<WorldRenderingState>)
  }

  return {
    materialPackages,
    lookProfiles,
    activeProfileId,
    environment,
    rendering,
    loading,
    initialized,
    error,
    initialize,
    importFile,
    activateLook,
    restorePreferredLook,
    removeLook,
    removeMaterial,
    setEnvironment,
    setRendering,
  }
})

function packageKey(kind: 'material' | 'look', id: string): string {
  return `${kind}:${id}`
}

function safeStorageGet(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

function safeStorageSet(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* 当前会话仍可使用。 */ }
}

function safeJson(value: string | null): unknown {
  if (!value) return undefined
  try { return JSON.parse(value) } catch { return undefined }
}

function normalizeHash(value: string): string {
  return value.toLowerCase().replace(/^sha256:/, '')
}
