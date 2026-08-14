import type { WorldLookProfileManifest } from '../wild-core/src/materials'

export interface DisposableWorldLookResource {
  dispose(): void
}

export interface WorldLookActivationContext {
  renderer: unknown
  scene: unknown
}

export interface ShaderFeatureModule {
  id: string
  activate?(
    context: WorldLookActivationContext,
    profile: WorldLookProfileManifest,
  ): void | DisposableWorldLookResource | Promise<void | DisposableWorldLookResource>
}

export interface WorldLookActivationResult {
  profile: WorldLookProfileManifest
  unsupportedFeatures: string[]
}

type ProfileListener = (profile: WorldLookProfileManifest) => void

const defaultWorldLook: WorldLookProfileManifest = {
  format: 'wild.render-profile',
  version: '1.0',
  profileId: 'builtin:default',
  name: 'WILD 默认世界光影',
  license: 'WILD Built-in',
  publisher: 'WildAgent',
  features: {
    lighting: 'lighting.pbr.v1',
    sky: 'environment.sky.v1',
    fog: 'environment.fog.v1',
    toneMapping: 'post.tonemap.v1',
    wetness: 'surface.wetness.v1',
    rainStreak: 'surface.rain-streak.v1',
    snow: 'surface.snow.v1',
    dust: 'surface.dust.v1',
  },
  appearance: {
    directLightScale: 1.08,
    ambientLightScale: 0.9,
    exposureScale: 1.03,
    shadowOpacity: 0.78,
    fogScale: 1.08,
  },
  quality: {
    shadowTier: 'medium',
    weatherTier: 'low',
    postProcessingTier: 'medium',
  },
  renderer: {
    fallbackProfile: 'builtin:default',
  },
}

export const DEFAULT_WORLD_LOOK: WorldLookProfileManifest = Object.freeze(defaultWorldLook)

class WorldLookRuntime {
  private profiles = new Map<string, WorldLookProfileManifest>()
  private features = new Map<string, ShaderFeatureModule>()
  private listeners = new Set<ProfileListener>()
  private active = DEFAULT_WORLD_LOOK
  private activeResources: DisposableWorldLookResource[] = []
  private activationContext: WorldLookActivationContext | undefined

  constructor() {
    this.registerProfile(DEFAULT_WORLD_LOOK)
    for (const id of [
      ...Object.values(DEFAULT_WORLD_LOOK.features),
      'surface.micro-variation.v1',
      'surface.masonry.brick.v1',
      'surface.pbr.v1',
      'texture.ktx2.v1',
      'asset.zip64.v1',
    ]) {
      this.registerShaderFeature({ id })
    }
  }

  registerProfile(profile: WorldLookProfileManifest): () => void {
    const existing = this.profiles.get(profile.profileId)
    if (existing && JSON.stringify(existing) === JSON.stringify(profile)) return () => {}
    if (existing) {
      throw new Error(`World look profile already registered: ${profile.profileId}`)
    }
    this.profiles.set(profile.profileId, profile)
    return () => {
      if (profile.profileId === 'builtin:default' || this.active.profileId === profile.profileId) return
      this.profiles.delete(profile.profileId)
    }
  }

  registerShaderFeature(feature: ShaderFeatureModule): () => void {
    if (this.features.has(feature.id)) {
      throw new Error(`Shader feature already registered: ${feature.id}`)
    }
    this.features.set(feature.id, feature)
    return () => {
      if (this.features.get(feature.id) === feature) this.features.delete(feature.id)
    }
  }

  getActiveProfile(): WorldLookProfileManifest {
    return this.active
  }

  getProfile(profileId: string): WorldLookProfileManifest | undefined {
    return this.profiles.get(profileId)
  }

  removeProfile(profileId: string): boolean {
    if (profileId === DEFAULT_WORLD_LOOK.profileId || this.active.profileId === profileId) return false
    return this.profiles.delete(profileId)
  }

  setActivationContext(context: WorldLookActivationContext | undefined): void {
    this.activationContext = context
  }

  getActiveResourceCount(): number {
    return this.activeResources.length
  }

  listProfiles(): WorldLookProfileManifest[] {
    return [...this.profiles.values()]
  }

  getUnsupportedFeatures(profile: WorldLookProfileManifest): string[] {
    return [...new Set(Object.values(profile.features))].filter(id => !this.features.has(id))
  }

  hasShaderFeature(id: string): boolean {
    return this.features.has(id)
  }

  async activateProfile(
    profileId: string,
    context: WorldLookActivationContext | undefined = this.activationContext,
  ): Promise<WorldLookActivationResult> {
    const profile = this.profiles.get(profileId)
    if (!profile) throw new Error(`Unknown world look profile: ${profileId}`)
    if (profile.profileId === this.active.profileId) {
      return { profile, unsupportedFeatures: this.getUnsupportedFeatures(profile) }
    }

    const unsupportedFeatures = this.getUnsupportedFeatures(profile)
    if (unsupportedFeatures.length > 0) {
      throw new Error(`Unsupported shader features: ${unsupportedFeatures.join(', ')}`)
    }
    if (!context) throw new Error('World look activation context is not ready')

    const prepared: DisposableWorldLookResource[] = []
    try {
      for (const id of new Set(Object.values(profile.features))) {
        const resource = await this.features.get(id)?.activate?.(context, profile)
        if (resource) prepared.push(resource)
      }
    } catch (error) {
      disposeResources(prepared)
      throw error
    }

    const previousResources = this.activeResources
    this.activeResources = prepared
    this.active = profile
    this.listeners.forEach(listener => listener(profile))
    disposeResources(previousResources)
    return { profile, unsupportedFeatures: [] }
  }

  async restoreDefault(context: WorldLookActivationContext | undefined = this.activationContext): Promise<void> {
    if (this.active.profileId === DEFAULT_WORLD_LOOK.profileId) return
    await this.activateProfile(DEFAULT_WORLD_LOOK.profileId, context)
  }

  dispose(): void {
    disposeResources(this.activeResources)
    this.activeResources = []
    this.active = DEFAULT_WORLD_LOOK
    this.activationContext = undefined
  }

  subscribe(listener: ProfileListener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }
}

function disposeResources(resources: DisposableWorldLookResource[]): void {
  for (let index = resources.length - 1; index >= 0; index--) {
    try {
      resources[index].dispose()
    } catch (error) {
      console.warn('释放光影运行时资源失败', error)
    }
  }
}

export const worldLookRuntime = new WorldLookRuntime()

export const registerWorldLookProfile = worldLookRuntime.registerProfile.bind(worldLookRuntime)
export const registerShaderFeature = worldLookRuntime.registerShaderFeature.bind(worldLookRuntime)
