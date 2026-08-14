import type { MaterialDef } from '../../types'
import type {
  MaterialEnvironmentResponse,
  RenderMaterialDescriptor,
  SurfaceFamily,
  SurfaceSourceKind,
} from './contracts'

const FAMILY_DEFAULTS: Record<SurfaceFamily, MaterialEnvironmentResponse> = {
  neutral: {
    wetness: { absorption: 0.2, colorDarkening: 0.08, roughnessReduction: 0.12 },
    snow: { adhesion: 0.25 },
    dust: { adhesion: 0.3 },
  },
  mineral: {
    wetness: { absorption: 0.48, colorDarkening: 0.16, roughnessReduction: 0.24 },
    rainStreak: { strength: 0.2 },
    snow: { adhesion: 0.42 },
    dust: { adhesion: 0.5 },
  },
  masonry: {
    wetness: { absorption: 0.62, colorDarkening: 0.2, roughnessReduction: 0.28 },
    rainStreak: { strength: 0.28 },
    snow: { adhesion: 0.48 },
    dust: { adhesion: 0.55 },
  },
  wood: {
    wetness: { absorption: 0.36, colorDarkening: 0.14, roughnessReduction: 0.18 },
    rainStreak: { strength: 0.12 },
    snow: { adhesion: 0.28 },
    dust: { adhesion: 0.32 },
  },
  metal: {
    wetness: { absorption: 0.03, colorDarkening: 0.03, roughnessReduction: 0.38 },
    rainStreak: { strength: 0.08 },
    snow: { adhesion: 0.12 },
    dust: { adhesion: 0.16 },
  },
  glass: {
    wetness: { absorption: 0, colorDarkening: 0, roughnessReduction: 0.16 },
    rainStreak: { strength: 0.34 },
    snow: { adhesion: 0.04 },
    dust: { adhesion: 0.08 },
  },
}

export function createRenderMaterialDescriptor(
  materialRef: string,
  material: MaterialDef,
): RenderMaterialDescriptor {
  const family = resolveSurfaceFamily(materialRef, material)
  const source = resolveSurfaceSource(material)
  const specializedBrick = material.procedural?.type === 'brick'
  const usesDefaultSurface = source === 'constant' && family !== 'glass'

  return {
    family,
    source,
    implementation: specializedBrick
      ? 'masonry.brick.v1'
      : usesDefaultSurface
        ? 'surface.default.v1'
        : 'surface.pbr.v1',
    implementationVersion: 1,
    quality: 'low',
    requiredFeatures: specializedBrick
      ? ['surface.masonry.brick.v1']
      : usesDefaultSurface
        ? ['surface.micro-variation.v1']
        : [],
    environmentResponse: mergeEnvironmentResponse(
      FAMILY_DEFAULTS[family],
      material.environmentResponse,
    ),
  }
}

export function resolveSurfaceFamily(
  materialRef: string,
  material: MaterialDef,
): SurfaceFamily {
  if (material.surfaceFamily) return material.surfaceFamily
  if (material.procedural?.type === 'brick') return 'masonry'
  if (material.materialClass === 'glass' || material.transmission && material.transmission > 0.05) {
    return 'glass'
  }
  if (material.metallic >= 0.5) return 'metal'

  const semantic = materialRef.trim().toLowerCase()
  if (/(brick|masonry|mortar|tile|砖|砌体|砂浆)/.test(semantic)) return 'masonry'
  if (/(wood|timber|oak|pine|door|木|门)/.test(semantic)) return 'wood'
  if (/(metal|steel|iron|aluminium|aluminum|frame|railing|金属|钢|铁|栏杆)/.test(semantic)) {
    return 'metal'
  }
  if (/(glass|glazing|window|玻璃|窗)/.test(semantic)) return 'glass'
  if (/(wall|floor|roof|stone|concrete|plaster|cement|墙|地|屋面|石|混凝土|灰泥)/.test(semantic)) {
    return 'mineral'
  }
  return 'neutral'
}

function resolveSurfaceSource(material: MaterialDef): SurfaceSourceKind {
  const hasTexture = Boolean(
    material.textureSet
    || material.embeddedImage
    || material.textures && Object.values(material.textures).some(Boolean),
  )
  const hasProcedural = Boolean(material.procedural)
  if (hasTexture && hasProcedural) return 'hybrid'
  if (hasTexture) return 'texture-set'
  if (hasProcedural) return 'procedural'
  return 'constant'
}

function mergeEnvironmentResponse(
  fallback: MaterialEnvironmentResponse,
  override: MaterialEnvironmentResponse | undefined,
): MaterialEnvironmentResponse {
  return {
    wetness: mergeNumbers(fallback.wetness, override?.wetness),
    rainStreak: mergeNumbers(fallback.rainStreak, override?.rainStreak),
    snow: mergeNumbers(fallback.snow, override?.snow),
    dust: mergeNumbers(fallback.dust, override?.dust),
  }
}

function mergeNumbers<T extends Record<string, number | undefined>>(
  fallback: T | undefined,
  override: T | undefined,
): T | undefined {
  if (!fallback && !override) return undefined
  const result = { ...(fallback || {}) } as T
  if (override) {
    for (const [key, value] of Object.entries(override)) {
      if (typeof value === 'number' && Number.isFinite(value)) {
        result[key as keyof T] = Math.min(1, Math.max(0, value)) as T[keyof T]
      }
    }
  }
  return result
}

