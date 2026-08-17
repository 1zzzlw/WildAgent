import * as THREE from 'three'
import { PROCEDURAL_NOISE_GLSL } from './proceduralMaterials/noise.glsl'
import { getWorldEffectUniforms } from './worldEffectRuntime'
import { getWorldEnvironmentUniforms } from './worldEnvironmentRuntime'

const GROUND_WEATHER_SHADER_VERSION = 'ground-weather-v3'

/**
 * 地面天气层：雨后低洼处积水，雨滴落在随机位置后波纹从落点向外扩散并消失，
 * 积水呈镜面反射环境并带水的冷色 tint。全部由共享 uniform 驱动，默认关闭。
 */
export function applyGroundWeatherMaterial(material: THREE.MeshStandardMaterial): void {
  const environment = getWorldEnvironmentUniforms()
  const effects = getWorldEffectUniforms()

  material.userData.wildGroundWeather = true
  material.userData.wildGroundWeatherShaderVersion = GROUND_WEATHER_SHADER_VERSION
  material.customProgramCacheKey = () => `wild-ground-weather:${GROUND_WEATHER_SHADER_VERSION}`
  material.onBeforeCompile = shader => installGroundWeatherShader(shader as MutableShader, {
    rain: environment.rain,
    time: effects.effectTime,
    puddles: effects.puddles,
    ripples: effects.ripples,
    reflections: effects.reflections,
  })
  material.needsUpdate = true
}

interface MutableShader {
  uniforms: Record<string, { value: unknown }>
  vertexShader: string
  fragmentShader: string
}

interface GroundWeatherUniforms {
  rain: { value: number }
  time: { value: number }
  puddles: { value: number }
  ripples: { value: number }
  reflections: { value: number }
}

function installGroundWeatherShader(shader: MutableShader, uniforms: GroundWeatherUniforms): void {
  Object.assign(shader.uniforms, {
    uGroundRain: uniforms.rain,
    uGroundTime: uniforms.time,
    uGroundPuddles: uniforms.puddles,
    uGroundRipples: uniforms.ripples,
    uGroundReflections: uniforms.reflections,
  })

  shader.vertexShader = shader.vertexShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec3 vGroundWorldPosition;`,
    )
    .replace(
      '#include <worldpos_vertex>',
      `#include <worldpos_vertex>
vec4 wildGroundWorldPosition = vec4(transformed, 1.0);
#ifdef USE_INSTANCING
  wildGroundWorldPosition = instanceMatrix * wildGroundWorldPosition;
#endif
vGroundWorldPosition = (modelMatrix * wildGroundWorldPosition).xyz;`,
    )

  shader.fragmentShader = shader.fragmentShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec3 vGroundWorldPosition;
uniform float uGroundRain;
uniform float uGroundTime;
uniform float uGroundPuddles;
uniform float uGroundRipples;
uniform float uGroundReflections;
${PROCEDURAL_NOISE_GLSL}

// 雨滴波纹：每个落点按自身相位周期性"落下一滴"，波纹从落点向外扩散并衰减。
float wildGroundRainRipple(vec2 p, float t) {
  float sum = 0.0;
  for (int i = 0; i < 5; i++) {
    vec2 cell = floor(p * 0.45 + float(i) * 3.9);
    float h1 = wildHash21(cell + float(i) * 13.7);
    float h2 = wildHash21(cell + float(i) * 29.3);
    vec2 center = cell + vec2(0.5) + (vec2(h1, h2) - 0.5) * 0.7;
    float d = length(p - center);
    float phase = fract(t * 0.7 + h1);      // 0→1：滴落→扩散→消失
    float radius = phase * 2.4;
    float ring = sin((d - radius) * 30.0) * exp(-abs(d - radius) * 5.0);
    float fade = smoothstep(0.0, 0.12, phase) * smoothstep(1.0, 0.45, phase);
    sum += ring * fade * exp(-radius * 1.1);
  }
  return clamp(sum, -1.0, 1.0);
}`,
    )
    .replace(
      '#include <map_fragment>',
      `#include <map_fragment>
float wildPuddleMask = 0.0;
if (uGroundPuddles * uGroundRain > 0.0) {
  float wildPuddleNoise = wildFbm(vGroundWorldPosition.xz * 0.05 + vec2(7.3, 3.1));
  wildPuddleMask = smoothstep(0.40, 0.72, 1.0 - wildPuddleNoise)
    * smoothstep(0.15, 0.5, uGroundRain) * uGroundPuddles;
}
// 积水：变暗并带水的冷色 tint
diffuseColor.rgb *= 1.0 - wildPuddleMask * 0.5;
diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * vec3(0.72, 0.84, 0.96), wildPuddleMask * 0.65);
float wildRippleWave = 0.0;
if (wildPuddleMask > 0.01 && uGroundRipples > 0.5) {
  wildRippleWave = wildGroundRainRipple(vGroundWorldPosition.xz, uGroundTime);
  diffuseColor.rgb += vec3(0.42, 0.56, 0.72) * wildRippleWave * wildPuddleMask;
}`,
    )
    .replace(
      '#include <roughnessmap_fragment>',
      `#include <roughnessmap_fragment>
roughnessFactor = clamp(roughnessFactor - wildPuddleMask * 0.9, 0.02, 1.0);`,
    )
    .replace(
      '#include <metalnessmap_fragment>',
      `#include <metalnessmap_fragment>
metalnessFactor = clamp(metalnessFactor + wildPuddleMask * uGroundReflections, 0.0, 1.0);`,
    )
    .replace(
      '#include <normal_fragment_maps>',
      `vec3 wildGroundBaseNormal = normal;
#include <normal_fragment_maps>
if (wildPuddleMask > 0.01 && uGroundRipples > 0.5) {
  vec2 p = vGroundWorldPosition.xz;
  float h0 = wildGroundRainRipple(p, uGroundTime);
  float hx = wildGroundRainRipple(p + vec2(0.03, 0.0), uGroundTime);
  float hz = wildGroundRainRipple(p + vec2(0.0, 0.03), uGroundTime);
  vec3 wildRippleNormal = normalize(vec3((h0 - hx) * 26.0, 1.0, (h0 - hz) * 26.0));
  normal = normalize(mix(normal, wildRippleNormal, wildPuddleMask * 0.6));
}`,
    )
}
