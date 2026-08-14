import type {
  MaterialEnvironmentResponse,
  MaterialPackageChannel,
  MaterialPackageChannelResource,
  SurfaceFamily,
  SurfaceQuality,
  WildMaterialPackageManifest,
  WorldLookProfileManifest,
  WorldPackageManifest,
} from './contracts'

const SURFACE_FAMILIES = new Set<SurfaceFamily>([
  'neutral', 'mineral', 'masonry', 'wood', 'metal', 'glass',
])
const QUALITY_LEVELS = new Set<SurfaceQuality>(['low', 'medium', 'high', 'fallback'])
const CHANNEL_MIME_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/ktx2'])
const EXECUTABLE_KEYS = /^(shader(source|code)?|vertexshader|fragmentshader|glsl|wgsl|script|javascript|code)$/i

export class WorldPackageValidationError extends Error {
  readonly issues: string[]

  constructor(issues: string[]) {
    super(`Invalid WILD package: ${issues.join('; ')}`)
    this.name = 'WorldPackageValidationError'
    this.issues = issues
  }
}

export function parseWorldPackageManifest(input: string | unknown): WorldPackageManifest {
  const value = typeof input === 'string' ? parseJson(input) : input
  const issues: string[] = []
  rejectExecutableFields(value, '$', issues)
  const record = asRecord(value, '$', issues)
  const format = readString(record.format, '$.format', issues)
  if (issues.length > 0) throw new WorldPackageValidationError(issues)
  if (format === 'wild.material-package') return parseMaterialPackageManifest(record)
  if (format === 'wild.render-profile') return parseWorldLookProfileManifest(record)
  throw new WorldPackageValidationError([`$.format 不支持: ${format}`])
}

export function parseMaterialPackageManifest(input: unknown): WildMaterialPackageManifest {
  const issues: string[] = []
  rejectExecutableFields(input, '$', issues)
  const value = asRecord(input, '$', issues)
  const version = readVersion(value.version, issues)
  const materialId = readId(value.materialId, '$.materialId', issues)
  const packageId = readId(value.packageId ?? materialId, '$.packageId', issues)
  const channelsValue = asRecord(value.channels, '$.channels', issues)
  const baseColor = parseChannel(channelsValue.baseColor, '$.channels.baseColor', issues)
  const family = value.family === undefined
    ? undefined
    : SURFACE_FAMILIES.has(value.family as SurfaceFamily)
      ? value.family as SurfaceFamily
      : issue<SurfaceFamily | undefined>(issues, '$.family 不受支持', undefined)

  const result: WildMaterialPackageManifest = {
    format: 'wild.material-package',
    version,
    packageId,
    materialId,
    name: readString(value.name, '$.name', issues),
    contentHash: readHash(value.contentHash, '$.contentHash', issues),
    license: readString(value.license, '$.license', issues),
    channels: {
      baseColor,
      normal: optionalChannel(channelsValue.normal, '$.channels.normal', issues),
      roughness: optionalChannel(channelsValue.roughness, '$.channels.roughness', issues),
      metalness: optionalChannel(channelsValue.metalness, '$.channels.metalness', issues),
      ambientOcclusion: optionalChannel(
        channelsValue.ambientOcclusion,
        '$.channels.ambientOcclusion',
        issues,
      ),
    },
    family,
    defaults: parseMaterialDefaults(value.defaults, issues),
    environmentResponse: parseEnvironmentResponse(value.environmentResponse, issues),
    requiredFeatures: parseFeatureList(value.requiredFeatures, '$.requiredFeatures', issues),
    publisher: optionalString(value.publisher, '$.publisher', issues),
    signature: parseSignature(value.signature, issues),
    renderer: parseMaterialRenderer(value.renderer, issues),
  }
  if (issues.length > 0) throw new WorldPackageValidationError(issues)
  return result
}

export function parseWorldLookProfileManifest(input: unknown): WorldLookProfileManifest {
  const issues: string[] = []
  rejectExecutableFields(input, '$', issues)
  const value = asRecord(input, '$', issues)
  const featureRecord = asRecord(value.features, '$.features', issues)
  const features: Record<string, string> = {}
  for (const [role, feature] of Object.entries(featureRecord)) {
    if (!/^[a-z][a-zA-Z0-9_.-]{0,63}$/.test(role)) {
      issues.push(`$.features.${role} 的角色名非法`)
      continue
    }
    features[role] = readId(feature, `$.features.${role}`, issues)
  }
  if (Object.keys(features).length === 0) issues.push('$.features 至少需要一个功能')

  const appearanceValue = optionalRecord(value.appearance, '$.appearance', issues)
  const qualityValue = optionalRecord(value.quality, '$.quality', issues)
  const rendererValue = optionalRecord(value.renderer, '$.renderer', issues)
  const result: WorldLookProfileManifest = {
    format: 'wild.render-profile',
    version: readVersion(value.version, issues),
    profileId: readId(value.profileId, '$.profileId', issues),
    name: readString(value.name, '$.name', issues),
    contentHash: value.contentHash === undefined
      ? undefined
      : readHash(value.contentHash, '$.contentHash', issues),
    license: optionalString(value.license, '$.license', issues),
    publisher: optionalString(value.publisher, '$.publisher', issues),
    signature: parseSignature(value.signature, issues),
    features,
    appearance: appearanceValue && {
      directLightScale: optionalNumber(appearanceValue.directLightScale, 0, 4, '$.appearance.directLightScale', issues),
      ambientLightScale: optionalNumber(appearanceValue.ambientLightScale, 0, 4, '$.appearance.ambientLightScale', issues),
      exposureScale: optionalNumber(appearanceValue.exposureScale, 0.1, 4, '$.appearance.exposureScale', issues),
      shadowOpacity: optionalNumber(appearanceValue.shadowOpacity, 0, 1, '$.appearance.shadowOpacity', issues),
      fogScale: optionalNumber(appearanceValue.fogScale, 0.1, 8, '$.appearance.fogScale', issues),
    },
    quality: qualityValue && {
      shadowTier: optionalQuality(qualityValue.shadowTier, '$.quality.shadowTier', issues),
      weatherTier: optionalQuality(qualityValue.weatherTier, '$.quality.weatherTier', issues),
      postProcessingTier: optionalQuality(
        qualityValue.postProcessingTier,
        '$.quality.postProcessingTier',
        issues,
      ),
    },
    renderer: rendererValue && {
      minVersion: optionalString(rendererValue.minVersion, '$.renderer.minVersion', issues),
      fallbackProfile: optionalId(rendererValue.fallbackProfile, '$.renderer.fallbackProfile', issues),
    },
  }
  if (issues.length > 0) throw new WorldPackageValidationError(issues)
  return result
}

function parseChannel(value: unknown, path: string, issues: string[]): MaterialPackageChannel {
  const channel = asRecord(value, path, issues)
  const resource = parseChannelResource(channel, path, issues)
  const variantsValue = optionalRecord(channel.variants, `${path}.variants`, issues)
  const variants: MaterialPackageChannel['variants'] = {}
  if (variantsValue) {
    for (const quality of ['low', 'medium', 'high'] as const) {
      if (variantsValue[quality] !== undefined) {
        variants[quality] = parseChannelResource(
          asRecord(variantsValue[quality], `${path}.variants.${quality}`, issues),
          `${path}.variants.${quality}`,
          issues,
        )
      }
    }
    for (const key of Object.keys(variantsValue)) {
      if (!['low', 'medium', 'high'].includes(key)) issues.push(`${path}.variants.${key} 画质档位不受支持`)
    }
  }
  return {
    ...resource,
    variants: Object.keys(variants).length ? variants : undefined,
  }
}

function parseChannelResource(
  channel: Record<string, unknown>,
  path: string,
  issues: string[],
): MaterialPackageChannelResource {
  const mimeType = readString(channel.mimeType, `${path}.mimeType`, issues)
  if (!CHANNEL_MIME_TYPES.has(mimeType)) issues.push(`${path}.mimeType 不支持: ${mimeType}`)
  const colorSpace = channel.colorSpace === 'srgb' || channel.colorSpace === 'linear'
    ? channel.colorSpace
    : issue<'srgb' | 'linear'>(issues, `${path}.colorSpace 必须是 srgb 或 linear`, 'linear')
  return {
    uri: readSafeUri(channel.uri, `${path}.uri`, issues),
    mimeType: CHANNEL_MIME_TYPES.has(mimeType) ? mimeType as MaterialPackageChannel['mimeType'] : 'image/png',
    sha256: readHash(channel.sha256, `${path}.sha256`, issues),
    colorSpace,
    byteSize: optionalNumber(channel.byteSize, 1, 512 * 1024 * 1024, `${path}.byteSize`, issues),
  }
}

function parseSignature(value: unknown, issues: string[]) {
  const signature = optionalRecord(value, '$.signature', issues)
  if (!signature) return undefined
  const algorithm = readString(signature.algorithm, '$.signature.algorithm', issues)
  if (algorithm !== 'Ed25519') issues.push('$.signature.algorithm 当前只支持 Ed25519')
  return {
    algorithm: 'Ed25519' as const,
    publicKey: readBase64(signature.publicKey, '$.signature.publicKey', issues),
    value: readBase64(signature.value, '$.signature.value', issues),
  }
}

function optionalChannel(
  value: unknown,
  path: string,
  issues: string[],
): MaterialPackageChannel | undefined {
  return value === undefined ? undefined : parseChannel(value, path, issues)
}

function parseMaterialDefaults(value: unknown, issues: string[]) {
  const defaults = optionalRecord(value, '$.defaults', issues)
  if (!defaults) return undefined
  return {
    baseColorTint: optionalColor(defaults.baseColorTint, '$.defaults.baseColorTint', issues),
    roughness: optionalNumber(defaults.roughness, 0, 1, '$.defaults.roughness', issues),
    metallic: optionalNumber(defaults.metallic, 0, 1, '$.defaults.metallic', issues),
    normalScale: optionalNumber(defaults.normalScale, 0, 4, '$.defaults.normalScale', issues),
    uvScale: optionalVec2(defaults.uvScale, 0.01, 64, '$.defaults.uvScale', issues),
  }
}

function parseEnvironmentResponse(
  value: unknown,
  issues: string[],
): MaterialEnvironmentResponse | undefined {
  const response = optionalRecord(value, '$.environmentResponse', issues)
  if (!response) return undefined
  const wetness = optionalRecord(response.wetness, '$.environmentResponse.wetness', issues)
  const rainStreak = optionalRecord(response.rainStreak, '$.environmentResponse.rainStreak', issues)
  const snow = optionalRecord(response.snow, '$.environmentResponse.snow', issues)
  const dust = optionalRecord(response.dust, '$.environmentResponse.dust', issues)
  return {
    wetness: wetness && {
      absorption: optionalNumber(wetness.absorption, 0, 1, '$.environmentResponse.wetness.absorption', issues),
      colorDarkening: optionalNumber(wetness.colorDarkening, 0, 1, '$.environmentResponse.wetness.colorDarkening', issues),
      roughnessReduction: optionalNumber(wetness.roughnessReduction, 0, 1, '$.environmentResponse.wetness.roughnessReduction', issues),
      normalFlattening: optionalNumber(wetness.normalFlattening, 0, 1, '$.environmentResponse.wetness.normalFlattening', issues),
    },
    rainStreak: rainStreak && {
      strength: optionalNumber(rainStreak.strength, 0, 1, '$.environmentResponse.rainStreak.strength', issues),
    },
    snow: snow && {
      adhesion: optionalNumber(snow.adhesion, 0, 1, '$.environmentResponse.snow.adhesion', issues),
    },
    dust: dust && {
      adhesion: optionalNumber(dust.adhesion, 0, 1, '$.environmentResponse.dust.adhesion', issues),
    },
  }
}

function parseFeatureList(value: unknown, path: string, issues: string[]): string[] | undefined {
  if (value === undefined) return undefined
  if (!Array.isArray(value)) return issue(issues, `${path} 必须是数组`, undefined)
  return [...new Set(value.map((item, index) => readId(item, `${path}[${index}]`, issues)))]
}

function parseMaterialRenderer(value: unknown, issues: string[]) {
  const renderer = optionalRecord(value, '$.renderer', issues)
  if (!renderer) return undefined
  return {
    minVersion: optionalString(renderer.minVersion, '$.renderer.minVersion', issues),
    fallbackColor: optionalColor(renderer.fallbackColor, '$.renderer.fallbackColor', issues),
  }
}

function rejectExecutableFields(value: unknown, path: string, issues: string[]): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => rejectExecutableFields(item, `${path}[${index}]`, issues))
    return
  }
  if (!value || typeof value !== 'object') return
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (EXECUTABLE_KEYS.test(key)) issues.push(`${path}.${key} 不允许携带可执行代码`)
    rejectExecutableFields(child, `${path}.${key}`, issues)
  }
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    throw new WorldPackageValidationError(['JSON 解析失败'])
  }
}

function asRecord(value: unknown, path: string, issues: string[]): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  issues.push(`${path} 必须是对象`)
  return {}
}

function optionalRecord(value: unknown, path: string, issues: string[]) {
  return value === undefined ? undefined : asRecord(value, path, issues)
}

function readVersion(value: unknown, issues: string[]): '1.0' {
  if (value !== '1.0') issues.push('$.version 当前只支持 1.0')
  return '1.0'
}

function readString(value: unknown, path: string, issues: string[]): string {
  if (typeof value === 'string' && value.trim() && value.length <= 512) return value.trim()
  issues.push(`${path} 必须是非空字符串`)
  return ''
}

function optionalString(value: unknown, path: string, issues: string[]) {
  return value === undefined ? undefined : readString(value, path, issues)
}

function readId(value: unknown, path: string, issues: string[]): string {
  const id = readString(value, path, issues)
  if (id && !/^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,255}$/.test(id)) issues.push(`${path} 格式非法`)
  return id
}

function optionalId(value: unknown, path: string, issues: string[]) {
  return value === undefined ? undefined : readId(value, path, issues)
}

function readHash(value: unknown, path: string, issues: string[]): string {
  const hash = readString(value, path, issues)
  if (hash && !/^(sha256:)?[a-fA-F0-9]{8,128}$/.test(hash)) issues.push(`${path} 不是有效 SHA-256 标识`)
  return hash
}

function readSafeUri(value: unknown, path: string, issues: string[]): string {
  const uri = readString(value, path, issues)
  if (uri && !/^(https?:\/\/|ipfs:\/\/|\/|package:\/|data:image\/(png|jpeg|webp);base64,)/i.test(uri)) {
    issues.push(`${path} 只允许 HTTP(S)、IPFS、站内绝对路径、包内路径或安全图片 data URI`)
  }
  return uri
}

function readBase64(value: unknown, path: string, issues: string[]): string {
  const encoded = readString(value, path, issues)
  if (encoded && !/^[a-zA-Z0-9+/]+={0,2}$/.test(encoded)) issues.push(`${path} 不是有效 Base64`)
  return encoded
}

function optionalNumber(
  value: unknown,
  min: number,
  max: number,
  path: string,
  issues: string[],
): number | undefined {
  if (value === undefined) return undefined
  if (typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max) return value
  issues.push(`${path} 必须在 ${min}~${max} 范围内`)
  return undefined
}

function optionalQuality(value: unknown, path: string, issues: string[]): SurfaceQuality | undefined {
  if (value === undefined) return undefined
  if (QUALITY_LEVELS.has(value as SurfaceQuality)) return value as SurfaceQuality
  issues.push(`${path} 质量等级不支持`)
  return undefined
}

function optionalColor(value: unknown, path: string, issues: string[]) {
  if (value === undefined) return undefined
  if (Array.isArray(value) && value.length === 3 && value.every(item => (
    typeof item === 'number' && Number.isFinite(item) && item >= 0 && item <= 1
  ))) return value as [number, number, number]
  issues.push(`${path} 必须是 0~1 的 RGB 三元组`)
  return undefined
}

function optionalVec2(value: unknown, min: number, max: number, path: string, issues: string[]) {
  if (value === undefined) return undefined
  if (Array.isArray(value) && value.length === 2 && value.every(item => (
    typeof item === 'number' && Number.isFinite(item) && item >= min && item <= max
  ))) return value as [number, number]
  issues.push(`${path} 必须是 ${min}~${max} 的二元组`)
  return undefined
}

function issue<T>(issues: string[], message: string, fallback: T): T {
  issues.push(message)
  return fallback
}
