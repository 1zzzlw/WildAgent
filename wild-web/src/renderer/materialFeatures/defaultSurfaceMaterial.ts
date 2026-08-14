import * as THREE from 'three'
import type { RenderMaterialDescriptor, SurfaceFamily } from '../../wild-core/src/materials'
import { PROCEDURAL_NOISE_GLSL } from '../proceduralMaterials/noise.glsl'
import {
  getWorldEnvironmentUniforms,
  getWorldRenderingUniforms,
} from '../worldEnvironmentRuntime'

const SHADER_VERSION = 'default-surface-v1'

interface MutableShader {
  uniforms: Record<string, { value: unknown }>
  vertexShader: string
  fragmentShader: string
}

interface DefaultSurfaceParams {
  family: SurfaceFamily
  familyCode: number
  seed: number
  scale: number
  colorVariation: number
  roughnessVariation: number
  wetnessAbsorption: number
  wetnessDarkening: number
  wetnessRoughnessReduction: number
  wetnessNormalFlattening: number
  rainStreakStrength: number
  snowAdhesion: number
  dustAdhesion: number
}

const FAMILY_CODE: Record<SurfaceFamily, number> = {
  neutral: 0,
  mineral: 1,
  masonry: 1,
  wood: 2,
  metal: 3,
  glass: 4,
}

/**
 * 默认世界的低成本表面层。它只补充克制的微变化，不替代专用砖 Shader 或 PBR 贴图。
 * 所有表面族共用同一 GPU Program，差异仅通过 uniform 表达。
 */
export function applyDefaultSurfaceMaterial(
  material: THREE.MeshStandardMaterial,
  descriptor: RenderMaterialDescriptor,
  materialSeed: string,
): void {
  if (descriptor.family === 'glass' || descriptor.quality === 'fallback') return
  const params = createDefaultSurfaceParams(descriptor, materialSeed)
  material.userData.wildDefaultSurface = params
  material.userData.wildDefaultSurfaceShaderVersion = SHADER_VERSION
  material.customProgramCacheKey = () => `wild-surface:${SHADER_VERSION}`
  material.onBeforeCompile = shader => installDefaultSurfaceShader(shader as MutableShader, params)
  material.needsUpdate = true
}

export function installDefaultSurfaceShader(
  shader: MutableShader,
  params: DefaultSurfaceParams,
): void {
  const environment = getWorldEnvironmentUniforms()
  const rendering = getWorldRenderingUniforms()
  Object.assign(shader.uniforms, {
    wildSurfaceFamily: { value: params.familyCode },
    wildSurfaceSeed: { value: params.seed },
    wildSurfaceScale: { value: params.scale },
    wildSurfaceColorVariation: { value: params.colorVariation },
    wildSurfaceRoughnessVariation: { value: params.roughnessVariation },
    wildWorldWetness: environment.wetness,
    wildWorldRain: environment.rain,
    wildWorldSnow: environment.snow,
    wildWorldDust: environment.dust,
    wildSurfaceEnabled: rendering.surfaceEnabled,
    wildSurfaceQuality: rendering.surfaceQuality,
    wildWeatherEnabled: rendering.weatherEnabled,
    wildWeatherQuality: rendering.weatherQuality,
    wildWetnessAbsorption: { value: params.wetnessAbsorption },
    wildWetnessDarkening: { value: params.wetnessDarkening },
    wildWetnessRoughnessReduction: { value: params.wetnessRoughnessReduction },
    wildWetnessNormalFlattening: { value: params.wetnessNormalFlattening },
    wildRainStreakStrength: { value: params.rainStreakStrength },
    wildSnowAdhesion: { value: params.snowAdhesion },
    wildDustAdhesion: { value: params.dustAdhesion },
  })

  shader.vertexShader = shader.vertexShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec2 vWildDefaultSurfaceUv;
varying vec3 vWildDefaultWorldNormal;
varying vec3 vWildDefaultWorldPosition;`,
    )
    .replace(
      '#include <uv_vertex>',
      '#include <uv_vertex>\nvWildDefaultSurfaceUv = uv;',
    )
    .replace(
      '#include <defaultnormal_vertex>',
      '#include <defaultnormal_vertex>\nvWildDefaultWorldNormal = normalize(mat3(modelMatrix) * transformedNormal);',
    )
    .replace(
      '#include <worldpos_vertex>',
      `#include <worldpos_vertex>
vec4 wildDefaultWorldPosition = vec4(transformed, 1.0);
#ifdef USE_INSTANCING
  wildDefaultWorldPosition = instanceMatrix * wildDefaultWorldPosition;
#endif
vWildDefaultWorldPosition = (modelMatrix * wildDefaultWorldPosition).xyz;`,
    )

  shader.fragmentShader = shader.fragmentShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec2 vWildDefaultSurfaceUv;
varying vec3 vWildDefaultWorldNormal;
varying vec3 vWildDefaultWorldPosition;
uniform int wildSurfaceFamily;
uniform float wildSurfaceSeed;
uniform float wildSurfaceScale;
uniform float wildSurfaceColorVariation;
uniform float wildSurfaceRoughnessVariation;
uniform float wildWorldWetness;
uniform float wildWorldRain;
uniform float wildWorldSnow;
uniform float wildWorldDust;
uniform float wildSurfaceEnabled;
uniform float wildSurfaceQuality;
uniform float wildWeatherEnabled;
uniform float wildWeatherQuality;
uniform float wildWetnessAbsorption;
uniform float wildWetnessDarkening;
uniform float wildWetnessRoughnessReduction;
uniform float wildWetnessNormalFlattening;
uniform float wildRainStreakStrength;
uniform float wildSnowAdhesion;
uniform float wildDustAdhesion;
${PROCEDURAL_NOISE_GLSL}`,
    )
    .replace(
      '#include <map_fragment>',
      `#include <map_fragment>
vec2 wildDefaultUv = vWildDefaultSurfaceUv * wildSurfaceScale;
float wildDefaultNoise = wildFbm(wildDefaultUv + vec2(wildSurfaceSeed * 0.0017));
float wildDefaultDetail = wildFbm(wildDefaultUv * 3.1 + vec2(wildSurfaceSeed * 0.0041));
float wildDefaultPattern = (wildDefaultNoise - 0.5) * 0.72 + (wildDefaultDetail - 0.5) * 0.28;
if (wildSurfaceFamily == 2) {
  float wildWoodWave = sin(
    wildDefaultUv.y * 7.0 + wildFbm(vec2(wildDefaultUv.x * 0.18, wildDefaultUv.y * 0.7)) * 5.0
  );
  wildDefaultPattern = wildDefaultPattern * 0.42 + wildWoodWave * 0.08;
} else if (wildSurfaceFamily == 3) {
  float wildMetalBrush = sin(wildDefaultUv.y * 42.0 + wildDefaultDetail * 2.0) * 0.035;
  wildDefaultPattern = wildDefaultPattern * 0.2 + wildMetalBrush;
}
float wildDefaultSurfaceAmount = wildSurfaceEnabled * wildSurfaceQuality;
diffuseColor.rgb *= 1.0 + wildDefaultPattern * wildSurfaceColorVariation * wildDefaultSurfaceAmount;
float wildWeatherAmount = wildWeatherEnabled * wildWeatherQuality;
float wildMaterialWetness = wildWorldWetness * wildWetnessAbsorption * wildWeatherAmount;
diffuseColor.rgb *= 1.0 - wildMaterialWetness * wildWetnessDarkening;`,
    )
    .replace(
      '#include <color_fragment>',
      `#include <color_fragment>
float wildVerticalMask = 1.0 - abs(normalize(vWildDefaultWorldNormal).y);
float wildRainColumns = wildFbm(vec2(
  vWildDefaultWorldPosition.x * 1.7 + vWildDefaultWorldPosition.z * 0.9,
  vWildDefaultWorldPosition.y * 0.12 + wildSurfaceSeed * 0.002
));
float wildRainMask = smoothstep(0.56, 0.84, wildRainColumns)
  * wildVerticalMask * wildWorldRain * wildRainStreakStrength * wildWeatherAmount;
diffuseColor.rgb *= 1.0 - wildRainMask * 0.16;
float wildUpward = smoothstep(0.28, 0.82, normalize(vWildDefaultWorldNormal).y);
float wildSnowMask = wildUpward * wildWorldSnow * wildSnowAdhesion * wildWeatherAmount
  * smoothstep(0.2, 0.72, wildDefaultDetail);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.9, 0.93, 0.95), clamp(wildSnowMask, 0.0, 0.82));
float wildDustMask = wildUpward * wildWorldDust * wildDustAdhesion * wildWeatherAmount
  * smoothstep(0.18, 0.8, 1.0 - wildDefaultNoise);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.52, 0.44, 0.32), clamp(wildDustMask * 0.42, 0.0, 0.38));`,
    )
    .replace(
      '#include <roughnessmap_fragment>',
      `#include <roughnessmap_fragment>
roughnessFactor = clamp(
  roughnessFactor
    + wildDefaultPattern * wildSurfaceRoughnessVariation * wildDefaultSurfaceAmount
    - wildMaterialWetness * wildWetnessRoughnessReduction,
  0.04,
  1.0
);`,
    )
    .replace(
      '#include <normal_fragment_maps>',
      `vec3 wildDefaultBaseNormal = normal;
#include <normal_fragment_maps>
normal = normalize(mix(
  normal,
  wildDefaultBaseNormal,
  clamp(wildMaterialWetness * wildWetnessNormalFlattening, 0.0, 0.7)
));`,
    )
}

function createDefaultSurfaceParams(
  descriptor: RenderMaterialDescriptor,
  materialSeed: string,
): DefaultSurfaceParams {
  const family = descriptor.family
  const base = family === 'mineral' || family === 'masonry'
    ? { scale: 2.1, color: 0.11, roughness: 0.13 }
    : family === 'wood'
      ? { scale: 5.2, color: 0.1, roughness: 0.085 }
      : family === 'metal'
        ? { scale: 8.5, color: 0.045, roughness: 0.065 }
        : { scale: 3.5, color: 0.04, roughness: 0.05 }
  return {
    family,
    familyCode: FAMILY_CODE[family],
    seed: hashString(materialSeed) % 65521,
    scale: base.scale,
    colorVariation: base.color,
    roughnessVariation: base.roughness,
    wetnessAbsorption: descriptor.environmentResponse.wetness?.absorption ?? 0,
    wetnessDarkening: descriptor.environmentResponse.wetness?.colorDarkening ?? 0,
    wetnessRoughnessReduction: descriptor.environmentResponse.wetness?.roughnessReduction ?? 0,
    wetnessNormalFlattening: descriptor.environmentResponse.wetness?.normalFlattening ?? 0.24,
    rainStreakStrength: descriptor.environmentResponse.rainStreak?.strength ?? 0,
    snowAdhesion: descriptor.environmentResponse.snow?.adhesion ?? 0,
    dustAdhesion: descriptor.environmentResponse.dust?.adhesion ?? 0,
  }
}

function hashString(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}
