import * as THREE from 'three'
import { PROCEDURAL_NOISE_GLSL } from './noise.glsl'
import type { NormalizedProceduralBrickMaterial } from './types'
import {
  getWorldEnvironmentUniforms,
  getWorldRenderingUniforms,
} from '../worldEnvironmentRuntime'

const SHADER_VERSION = 'brick-v1'

interface MutableShader {
  uniforms: Record<string, { value: unknown }>
  vertexShader: string
  fragmentShader: string
}

export function applyProceduralBrickMaterial(
  material: THREE.MeshStandardMaterial,
  params: NormalizedProceduralBrickMaterial,
): void {
  material.userData.wildProcedural = params
  material.userData.wildProceduralShaderVersion = SHADER_VERSION
  material.customProgramCacheKey = () => `wild-procedural:${SHADER_VERSION}`
  material.onBeforeCompile = (shader) => installBrickShader(shader as MutableShader, params)
  material.needsUpdate = true
}

export function installBrickShader(
  shader: MutableShader,
  params: NormalizedProceduralBrickMaterial,
): void {
  const weathering = params.weathering
  const environment = getWorldEnvironmentUniforms()
  const rendering = getWorldRenderingUniforms()
  Object.assign(shader.uniforms, {
    wildBrickSize: { value: new THREE.Vector2(...params.brickSize) },
    wildMortarWidth: { value: params.mortarWidth },
    wildMortarDepth: { value: params.mortarDepth },
    wildRunningBond: { value: params.bond === 'running' ? 1 : 0 },
    wildSeed: { value: params.seed % 65521 },
    wildSecondaryColor: {
      value: new THREE.Color().setRGB(...params.secondaryColor, THREE.SRGBColorSpace),
    },
    wildColorVariation: { value: params.colorVariation },
    wildRoughnessVariation: { value: params.roughnessVariation },
    wildEdgeWear: { value: params.edgeWear },
    wildWeatherAmount: { value: weathering.amount },
    wildWeatherScale: { value: weathering.scale },
    wildEfflorescence: { value: weathering.efflorescence },
    wildVerticalStreaks: { value: weathering.verticalStreaks },
    wildBaseDampness: { value: weathering.baseDampness },
    wildWorldWetness: environment.wetness,
    wildWorldRain: environment.rain,
    wildWorldSnow: environment.snow,
    wildWorldDust: environment.dust,
    wildWeatherEnabled: rendering.weatherEnabled,
    wildWeatherQuality: rendering.weatherQuality,
  })

  shader.vertexShader = shader.vertexShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec2 vWildSurfaceUv;
varying vec3 vWildBrickWorldNormal;
varying vec3 vWildBrickWorldPosition;`,
    )
    .replace(
      '#include <uv_vertex>',
      '#include <uv_vertex>\nvWildSurfaceUv = uv;',
    )
    .replace(
      '#include <defaultnormal_vertex>',
      '#include <defaultnormal_vertex>\nvWildBrickWorldNormal = normalize(mat3(modelMatrix) * transformedNormal);',
    )
    .replace(
      '#include <worldpos_vertex>',
      `#include <worldpos_vertex>
vec4 wildBrickWorldPosition = vec4(transformed, 1.0);
#ifdef USE_INSTANCING
  wildBrickWorldPosition = instanceMatrix * wildBrickWorldPosition;
#endif
vWildBrickWorldPosition = (modelMatrix * wildBrickWorldPosition).xyz;`,
    )

  shader.fragmentShader = shader.fragmentShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec2 vWildSurfaceUv;
varying vec3 vWildBrickWorldNormal;
varying vec3 vWildBrickWorldPosition;
uniform vec2 wildBrickSize;
uniform float wildMortarWidth;
uniform float wildMortarDepth;
uniform int wildRunningBond;
uniform float wildSeed;
uniform vec3 wildSecondaryColor;
uniform float wildColorVariation;
uniform float wildRoughnessVariation;
uniform float wildEdgeWear;
uniform float wildWeatherAmount;
uniform float wildWeatherScale;
uniform float wildEfflorescence;
uniform float wildVerticalStreaks;
uniform float wildBaseDampness;
uniform float wildWorldWetness;
uniform float wildWorldRain;
uniform float wildWorldSnow;
uniform float wildWorldDust;
uniform float wildWeatherEnabled;
uniform float wildWeatherQuality;
${PROCEDURAL_NOISE_GLSL}`,
    )
    .replace(
      '#include <map_fragment>',
      `#include <map_fragment>
vec2 wildSurfaceMeters = vWildSurfaceUv;
vec2 wildBrickUv = wildSurfaceMeters / wildBrickSize;
float wildRow = floor(wildBrickUv.y);
if (wildRunningBond == 1 && mod(wildRow, 2.0) > 0.5) wildBrickUv.x += 0.5;
vec2 wildCell = floor(wildBrickUv);
vec2 wildWithinBrick = fract(wildBrickUv);
vec2 wildEdgeDistance = min(wildWithinBrick, 1.0 - wildWithinBrick) * wildBrickSize;
float wildDistanceToEdge = min(wildEdgeDistance.x, wildEdgeDistance.y);
float wildMortarMask = 1.0 - smoothstep(
  wildMortarWidth * 0.45,
  wildMortarWidth * 0.58,
  wildDistanceToEdge
);
float wildCellTone = wildHash21(wildCell + vec2(wildSeed * 0.013, wildSeed * 0.021));
float wildFineNoise = wildFbm(wildSurfaceMeters * 18.0 + vec2(wildSeed * 0.001));
float wildVariation = (wildCellTone - 0.5) + (wildFineNoise - 0.5) * 0.35;
vec3 wildBrickColor = mix(
  diffuseColor.rgb,
  wildSecondaryColor,
  clamp(0.32 + wildVariation * 0.38, 0.0, 1.0) * wildColorVariation
);
wildBrickColor *= 1.0 + wildVariation * wildColorVariation * 0.32;
vec3 wildMortarColor = mix(vec3(0.38, 0.35, 0.31), diffuseColor.rgb, 0.16);
float wildWearBand = (1.0 - wildMortarMask)
  * (1.0 - smoothstep(wildMortarWidth, wildMortarWidth * 2.6, wildDistanceToEdge));
wildBrickColor = mix(wildBrickColor, min(vec3(1.0), wildBrickColor * 1.16), wildWearBand * wildEdgeWear);

float wildWeatherNoise = wildFbm(
  wildSurfaceMeters / max(wildWeatherScale, 0.1) + vec2(wildSeed * 0.003)
);
float wildWeatherMask = smoothstep(0.42, 0.78, wildWeatherNoise) * wildWeatherAmount;
float wildBaseMask = 1.0 - smoothstep(0.0, max(0.35, wildWeatherScale * 0.55), max(wildSurfaceMeters.y, 0.0));
float wildStreakNoise = wildFbm(vec2(wildSurfaceMeters.x * 1.7, wildSurfaceMeters.y * 0.11) + wildSeed * 0.007);
float wildStreakMask = smoothstep(0.58, 0.82, wildStreakNoise)
  * wildVerticalStreaks * wildWeatherAmount;
float wildEfflorescenceMask = wildBaseMask * smoothstep(0.48, 0.76, wildWeatherNoise)
  * wildEfflorescence * wildWeatherAmount;
float wildDampMask = wildBaseMask * wildBaseDampness * wildWeatherAmount;

vec3 wildAgedColor = mix(wildBrickColor, vec3(dot(wildBrickColor, vec3(0.299, 0.587, 0.114))), 0.28);
wildBrickColor = mix(wildBrickColor, wildAgedColor * 0.92 + vec3(0.035), wildWeatherMask * 0.55);
wildBrickColor *= 1.0 - wildStreakMask * 0.12;
wildBrickColor = mix(wildBrickColor, vec3(0.78, 0.75, 0.66), wildEfflorescenceMask * 0.68);
wildBrickColor *= 1.0 - wildDampMask * 0.24;
diffuseColor.rgb = mix(wildBrickColor, wildMortarColor, wildMortarMask);
float wildGlobalWeatherAmount = wildWeatherEnabled * wildWeatherQuality;
float wildGlobalWetness = wildWorldWetness * 0.62 * wildGlobalWeatherAmount;
diffuseColor.rgb *= 1.0 - wildGlobalWetness * 0.2;
vec3 wildBrickNormal = normalize(vWildBrickWorldNormal);
float wildGlobalRain = smoothstep(0.58, 0.84, wildStreakNoise)
  * (1.0 - abs(wildBrickNormal.y)) * wildWorldRain * 0.28 * wildGlobalWeatherAmount;
diffuseColor.rgb *= 1.0 - wildGlobalRain * 0.16;
float wildBrickUpward = smoothstep(0.28, 0.82, wildBrickNormal.y);
float wildGlobalSnow = wildBrickUpward * wildWorldSnow * 0.48 * wildGlobalWeatherAmount
  * smoothstep(0.2, 0.72, wildFineNoise);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.9, 0.93, 0.95), clamp(wildGlobalSnow, 0.0, 0.82));
float wildGlobalDust = wildBrickUpward * wildWorldDust * 0.55 * wildGlobalWeatherAmount
  * smoothstep(0.18, 0.8, 1.0 - wildFineNoise);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.52, 0.44, 0.32), clamp(wildGlobalDust * 0.42, 0.0, 0.38));`,
    )
    .replace(
      '#include <roughnessmap_fragment>',
      `#include <roughnessmap_fragment>
roughnessFactor = clamp(
  roughnessFactor
    + (wildFineNoise - 0.5) * wildRoughnessVariation
    + wildMortarMask * 0.12
    + wildWeatherMask * 0.1
    + wildEfflorescenceMask * 0.08
    - wildDampMask * 0.04
    - wildGlobalWetness * 0.28,
  0.04,
  1.0
);`,
    )
    .replace(
      '#include <normal_fragment_maps>',
      `vec3 wildBrickBaseNormal = normal;
#include <normal_fragment_maps>
float wildSurfaceHeight = 1.0 - wildMortarMask;
vec2 wildHeightDerivative = vec2(dFdx(wildSurfaceHeight), dFdy(wildSurfaceHeight));
vec3 wildPositionDx = dFdx(-vViewPosition);
vec3 wildPositionDy = dFdy(-vViewPosition);
vec2 wildUvDx = dFdx(vWildSurfaceUv);
vec2 wildUvDy = dFdy(vWildSurfaceUv);
float wildDeterminant = wildUvDx.x * wildUvDy.y - wildUvDx.y * wildUvDy.x;
if (abs(wildDeterminant) > 0.000001 && wildMortarDepth > 0.0) {
  vec3 wildTangent = normalize((wildPositionDx * wildUvDy.y - wildPositionDy * wildUvDx.y) / wildDeterminant);
  vec3 wildBitangent = normalize((-wildPositionDx * wildUvDy.x + wildPositionDy * wildUvDx.x) / wildDeterminant);
  normal = normalize(
    normal + (wildTangent * wildHeightDerivative.x + wildBitangent * wildHeightDerivative.y)
      * wildMortarDepth * 120.0
  );
}
normal = normalize(mix(normal, wildBrickBaseNormal, clamp(wildGlobalWetness * 0.24, 0.0, 0.7)));`,
    )
}
