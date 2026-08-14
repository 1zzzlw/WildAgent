export type SurfaceFamily =
  | 'neutral'
  | 'mineral'
  | 'masonry'
  | 'wood'
  | 'metal'
  | 'glass'

export type SurfaceSourceKind = 'constant' | 'procedural' | 'texture-set' | 'hybrid'

export type SurfaceQuality = 'low' | 'medium' | 'high' | 'fallback'

export interface MaterialEnvironmentResponse {
  wetness?: {
    absorption?: number
    colorDarkening?: number
    roughnessReduction?: number
    normalFlattening?: number
  }
  rainStreak?: {
    strength?: number
  }
  snow?: {
    adhesion?: number
  }
  dust?: {
    adhesion?: number
  }
}

/** core 输出给 renderer 的稳定材质中间表示，不包含任何 GPU 代码。 */
export interface RenderMaterialDescriptor {
  family: SurfaceFamily
  source: SurfaceSourceKind
  implementation: string
  implementationVersion: number
  quality: SurfaceQuality
  requiredFeatures: string[]
  environmentResponse: MaterialEnvironmentResponse
}

export interface WorldEnvironmentState {
  timeOfDay: number
  rain: number
  wetness: number
  snow: number
  dust: number
  wind: number
  cloudCoverage: number
  fog: number
}

export interface MaterialPackageChannelResource {
  uri: string
  mimeType: 'image/png' | 'image/jpeg' | 'image/webp' | 'image/ktx2'
  sha256: string
  colorSpace: 'srgb' | 'linear'
  byteSize?: number
}

export interface MaterialPackageChannel extends MaterialPackageChannelResource {
  /** 按画质选择资源；缺失档位会自动回退基础资源。KTX2 mipmap 负责观察距离 LOD。 */
  variants?: Partial<Record<'low' | 'medium' | 'high', MaterialPackageChannelResource>>
}

export interface WorldPackageSignature {
  algorithm: 'Ed25519'
  publicKey: string
  value: string
}

export interface WildMaterialPackageManifest {
  format: 'wild.material-package'
  version: '1.0'
  packageId: string
  materialId: string
  name: string
  contentHash: string
  license: string
  channels: {
    baseColor: MaterialPackageChannel
    normal?: MaterialPackageChannel
    roughness?: MaterialPackageChannel
    metalness?: MaterialPackageChannel
    ambientOcclusion?: MaterialPackageChannel
  }
  family?: SurfaceFamily
  defaults?: {
    baseColorTint?: [number, number, number]
    roughness?: number
    metallic?: number
    normalScale?: number
    uvScale?: [number, number]
  }
  environmentResponse?: MaterialEnvironmentResponse
  requiredFeatures?: string[]
  publisher?: string
  signature?: WorldPackageSignature
  renderer?: {
    minVersion?: string
    fallbackColor?: [number, number, number]
  }
}

export interface WorldLookProfileManifest {
  format: 'wild.render-profile'
  version: '1.0'
  profileId: string
  name: string
  contentHash?: string
  license?: string
  publisher?: string
  signature?: WorldPackageSignature
  features: Record<string, string>
  appearance?: {
    directLightScale?: number
    ambientLightScale?: number
    exposureScale?: number
    shadowOpacity?: number
    fogScale?: number
  }
  quality?: {
    shadowTier?: SurfaceQuality
    weatherTier?: SurfaceQuality
    postProcessingTier?: SurfaceQuality
  }
  renderer?: {
    minVersion?: string
    fallbackProfile?: string
  }
}

export type WorldPackageManifest = WildMaterialPackageManifest | WorldLookProfileManifest

export const DEFAULT_WORLD_ENVIRONMENT: Readonly<WorldEnvironmentState> = Object.freeze({
  timeOfDay: 12,
  rain: 0,
  wetness: 0,
  snow: 0,
  dust: 0,
  wind: 0.2,
  cloudCoverage: 0.15,
  fog: 0.02,
})
