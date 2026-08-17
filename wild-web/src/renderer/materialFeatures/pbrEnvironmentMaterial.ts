import * as THREE from 'three'
import type { RenderMaterialDescriptor } from '../../wild-core/src/materials'
import { PROCEDURAL_NOISE_GLSL } from '../proceduralMaterials/noise.glsl'
import {
  getWorldEnvironmentUniforms,
  getWorldRenderingUniforms,
} from '../worldEnvironmentRuntime'

const SHADER_VERSION = 'pbr-environment-v1'

interface MutableShader {
  uniforms: Record<string, { value: unknown }>
  vertexShader: string
  fragmentShader: string
}

/** PBR 贴图负责基础表面；天气层由世界统一控制，避免每个材质包复制天气代码。 */
export function applyPbrEnvironmentMaterial(
  material: THREE.MeshStandardMaterial,
  descriptor: RenderMaterialDescriptor,
  materialSeed: string,
): void {
  const environment = getWorldEnvironmentUniforms()
  const rendering = getWorldRenderingUniforms()
  const response = descriptor.environmentResponse
  material.userData.wildEnvironmentSurface = true
  material.userData.wildEnvironmentShaderVersion = SHADER_VERSION
  material.customProgramCacheKey = () => `wild-surface:${SHADER_VERSION}`
  material.onBeforeCompile = rawShader => {
    const shader = rawShader as MutableShader
    Object.assign(shader.uniforms, {
      wildPbrSeed: { value: hashString(materialSeed) % 65521 },
      wildWorldWetness: environment.wetness,
      wildWorldRain: environment.rain,
      wildWorldSnow: environment.snow,
      wildWorldDust: environment.dust,
      wildWeatherEnabled: rendering.weatherEnabled,
      wildWeatherQuality: rendering.weatherQuality,
      wildWetnessAbsorption: { value: response.wetness?.absorption ?? 0 },
      wildWetnessDarkening: { value: response.wetness?.colorDarkening ?? 0 },
      wildWetnessRoughnessReduction: { value: response.wetness?.roughnessReduction ?? 0 },
      wildWetnessNormalFlattening: { value: response.wetness?.normalFlattening ?? 0.24 },
      wildRainStreakStrength: { value: response.rainStreak?.strength ?? 0 },
      wildSnowAdhesion: { value: response.snow?.adhesion ?? 0 },
      wildDustAdhesion: { value: response.dust?.adhesion ?? 0 },
    })
    installPbrEnvironmentShader(shader)
  }
  material.needsUpdate = true
}

function installPbrEnvironmentShader(shader: MutableShader): void {
  shader.vertexShader = shader.vertexShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec3 vWildPbrWorldNormal;
varying vec3 vWildPbrWorldPosition;`,
    )
    .replace(
      '#include <defaultnormal_vertex>',
      '#include <defaultnormal_vertex>\nvWildPbrWorldNormal = normalize(mat3(modelMatrix) * transformedNormal);',
    )
    .replace(
      '#include <worldpos_vertex>',
      `#include <worldpos_vertex>
vec4 wildPbrWorldPosition = vec4(transformed, 1.0);
#ifdef USE_INSTANCING
  wildPbrWorldPosition = instanceMatrix * wildPbrWorldPosition;
#endif
vWildPbrWorldPosition = (modelMatrix * wildPbrWorldPosition).xyz;`,
    )

  shader.fragmentShader = shader.fragmentShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec3 vWildPbrWorldNormal;
varying vec3 vWildPbrWorldPosition;
uniform float wildPbrSeed;
uniform float wildWorldWetness;
uniform float wildWorldRain;
uniform float wildWorldSnow;
uniform float wildWorldDust;
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
float wildPbrWeatherAmount = wildWeatherEnabled * wildWeatherQuality;
float wildPbrWetness = wildWorldWetness * wildWetnessAbsorption * wildPbrWeatherAmount;
diffuseColor.rgb *= 1.0 - wildPbrWetness * wildWetnessDarkening;`,
    )
    .replace(
      '#include <color_fragment>',
      `#include <color_fragment>
vec3 wildPbrNormal = normalize(vWildPbrWorldNormal);
float wildPbrUpward = smoothstep(0.28, 0.82, wildPbrNormal.y);
float wildPbrNoise = 0.5;
if (wildPbrWeatherAmount * (wildWorldSnow + wildWorldDust) > 0.0) {
  wildPbrNoise = wildFbm(vWildPbrWorldPosition.xz * 1.35 + vec2(wildPbrSeed * 0.001));
}
float wildPbrRainMask = 0.0;
if (wildPbrWeatherAmount * wildWorldRain * wildRainStreakStrength > 0.0) {
  float wildPbrColumns = wildFbm(vec2(
    vWildPbrWorldPosition.x * 1.7 + vWildPbrWorldPosition.z * 0.9,
    vWildPbrWorldPosition.y * 0.12 + wildPbrSeed * 0.002
  ));
  wildPbrRainMask = smoothstep(0.56, 0.84, wildPbrColumns)
    * (1.0 - abs(wildPbrNormal.y)) * wildWorldRain * wildRainStreakStrength * wildPbrWeatherAmount;
}
diffuseColor.rgb *= 1.0 - wildPbrRainMask * 0.16;
float wildPbrSnowMask = wildPbrUpward * wildWorldSnow * wildSnowAdhesion * wildPbrWeatherAmount
  * smoothstep(0.2, 0.72, wildPbrNoise);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.9, 0.93, 0.95), clamp(wildPbrSnowMask, 0.0, 0.82));
float wildPbrDustMask = wildPbrUpward * wildWorldDust * wildDustAdhesion * wildPbrWeatherAmount
  * smoothstep(0.18, 0.8, 1.0 - wildPbrNoise);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.52, 0.44, 0.32), clamp(wildPbrDustMask * 0.42, 0.0, 0.38));`,
    )
    .replace(
      '#include <roughnessmap_fragment>',
      `#include <roughnessmap_fragment>
roughnessFactor = clamp(
  roughnessFactor - wildPbrWetness * wildWetnessRoughnessReduction,
  0.04,
  1.0
);`,
    )
    .replace(
      '#include <normal_fragment_maps>',
      `vec3 wildPbrBaseNormal = normal;
#include <normal_fragment_maps>
normal = normalize(mix(
  normal,
  wildPbrBaseNormal,
  clamp(wildPbrWetness * wildWetnessNormalFlattening, 0.0, 0.7)
));`,
    )
}

function hashString(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}
