import * as THREE from 'three'
import { getWorldEnvironmentUniforms } from './worldEnvironmentRuntime'
export { isWaterMaterial } from 'wild-core/materials'

const uniforms = { time: { value: 0 }, enabled: { value: 1 }, transparency: { value: 1 }, waveStrength: { value: 0.65 } }
export function getWaterReflectionUniforms(material: THREE.Material) {
  return material.userData.waterReflectionUniforms ??= {
    map: { value: null as THREE.Texture | null },
    matrix: { value: new THREE.Matrix4() },
    strength: { value: 0 },
    height: { value: 0 },
    texel: { value: new THREE.Vector2(1 / 512, 1 / 512) },
  }
}
export function setWaterSurfaceTime(seconds: number): void { if (uniforms.enabled.value > 0) uniforms.time.value = seconds }
export function setWaterSurfaceAnimated(enabled: boolean): void { uniforms.enabled.value = enabled ? 1 : 0 }
export function setWaterSurfaceAppearance(transparency: number, waveStrength: number): void {
  uniforms.transparency.value = THREE.MathUtils.clamp(transparency, 0, 1)
  uniforms.waveStrength.value = THREE.MathUtils.clamp(waveStrength, 0, 1)
}

/** 保留 PBR 透射与环境反射，仅扰动朝上的表面法线；不移动几何体，池边不会穿模。 */
export function applyWaterSurfaceMaterial(material: THREE.MeshStandardMaterial): void {
  const previous = material.onBeforeCompile
  const cacheKey = material.customProgramCacheKey()
  material.userData.wildWaterSurface = true
  const reflection = getWaterReflectionUniforms(material)
  material.customProgramCacheKey = () => cacheKey + ':water-surface-v3'
  material.onBeforeCompile = (shader, renderer) => {
    previous.call(material, shader, renderer)
    shader.uniforms.wildWaterTime = uniforms.time
    shader.uniforms.wildWaterEnabled = uniforms.enabled
    shader.uniforms.wildWaterTransparency = uniforms.transparency
    shader.uniforms.wildWaterWaveStrength = uniforms.waveStrength
    shader.uniforms.wildWaterWind = getWorldEnvironmentUniforms().wind
    shader.uniforms.wildWaterReflection = reflection.map
    shader.uniforms.wildWaterReflectionMatrix = reflection.matrix
    shader.uniforms.wildWaterReflectionStrength = reflection.strength
    shader.uniforms.wildWaterReflectionHeight = reflection.height
    shader.uniforms.wildWaterReflectionTexel = reflection.texel
    shader.vertexShader = shader.vertexShader.replace('#include <common>', `#include <common>
varying vec3 vWildWaterPosition;
varying float vWildWaterUp;`)
      .replace('#include <defaultnormal_vertex>', `#include <defaultnormal_vertex>
vWildWaterUp = max(0.0, inverseTransformDirection(transformedNormal, viewMatrix).y);`)
      .replace('#include <worldpos_vertex>', `#include <worldpos_vertex>
vec4 wildWaterPosition = vec4(transformed, 1.0);
#ifdef USE_INSTANCING
wildWaterPosition = instanceMatrix * wildWaterPosition;
#endif
vWildWaterPosition = (modelMatrix * wildWaterPosition).xyz;`)
    shader.fragmentShader = shader.fragmentShader.replace('#include <common>', `#include <common>
varying vec3 vWildWaterPosition;
varying float vWildWaterUp;
uniform float wildWaterTime;
uniform float wildWaterTransparency;
uniform float wildWaterWaveStrength;
uniform float wildWaterWind;
uniform sampler2D wildWaterReflection;
uniform mat4 wildWaterReflectionMatrix;
uniform float wildWaterReflectionStrength;
uniform float wildWaterReflectionHeight;
uniform vec2 wildWaterReflectionTexel;`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
float wildWaterMask = smoothstep(0.8, 0.98, vWildWaterUp);
vec2 wildWaterP = vWildWaterPosition.xz;
float wildWaterT = wildWaterTime;
// 缓慢扭曲相位，避免几组正弦波形成整齐重复的交叉网纹。
wildWaterP += 0.35 * vec2(sin(wildWaterP.y * 0.51 + wildWaterT * 0.09), cos(wildWaterP.x * 0.43 - wildWaterT * 0.07));
float wildWaterDetail = 1.0 - smoothstep(0.035, 0.16, length(fwidth(wildWaterP)));
vec2 wildWaterGradient = vec2(0.92, 0.39) * 0.12 * cos(dot(wildWaterP, vec2(1.6, 0.7)) + wildWaterT * 0.75)
  + vec2(-0.24, 0.97) * 0.075 * cos(dot(wildWaterP, vec2(-0.8, 3.2)) - wildWaterT * 1.05)
  + vec2(0.8, -0.6) * 0.035 * cos(dot(wildWaterP, vec2(5.4, -4.1)) + wildWaterT * 1.45)
  + vec2(0.85, 0.52) * 0.018 * wildWaterDetail * cos(dot(wildWaterP, vec2(18.0, 11.0)) - wildWaterT * 2.1);
wildWaterGradient *= wildWaterWaveStrength * mix(0.7, 1.7, wildWaterWind);
vec3 wildWaterNormalDelta = (viewMatrix * vec4(-wildWaterGradient.x, 0.0, -wildWaterGradient.y, 0.0)).xyz;
normal = normalize(normal + wildWaterNormalDelta * wildWaterMask);`)
      .replace('#include <color_fragment>', `#include <color_fragment>
#ifdef USE_TRANSMISSION
// 水色主要由体积吸收表达，避免深色底色再次乘进透射光而看成不透明色板。
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0), 0.15 * wildWaterTransparency);
#endif`)
      .replace('#include <transmission_fragment>', THREE.ShaderChunk.transmission_fragment.replace(
        'material.transmission = transmission;',
        'material.transmission = transmission * wildWaterTransparency;',
      ))
      .replace('#include <opaque_fragment>', `
if (wildWaterReflectionStrength > 0.0 && wildWaterMask > 0.0 && abs(vWildWaterPosition.y - wildWaterReflectionHeight) < 0.025) {
  vec4 reflectionPosition = wildWaterReflectionMatrix * vec4(vWildWaterPosition, 1.0);
  vec2 reflectionUv = reflectionPosition.xy / max(reflectionPosition.w, 0.0001);
  reflectionUv += wildWaterGradient * 0.025;
  if (reflectionPosition.w > 0.0 && all(greaterThan(reflectionUv, vec2(0.0))) && all(lessThan(reflectionUv, vec2(1.0)))) {
    vec2 blur = wildWaterReflectionTexel * (1.0 + roughnessFactor * 8.0);
    vec3 reflectionColor = texture2D(wildWaterReflection, reflectionUv).rgb * 0.4;
    reflectionColor += texture2D(wildWaterReflection, reflectionUv + vec2(blur.x, 0.0)).rgb * 0.15;
    reflectionColor += texture2D(wildWaterReflection, reflectionUv - vec2(blur.x, 0.0)).rgb * 0.15;
    reflectionColor += texture2D(wildWaterReflection, reflectionUv + vec2(0.0, blur.y)).rgb * 0.15;
    reflectionColor += texture2D(wildWaterReflection, reflectionUv - vec2(0.0, blur.y)).rgb * 0.15;
    float fresnel = 0.02 + 0.98 * pow(1.0 - clamp(dot(normal, normalize(vViewPosition)), 0.0, 1.0), 5.0);
    outgoingLight = mix(outgoingLight, reflectionColor, wildWaterReflectionStrength * wildWaterMask * fresnel * (1.0 - roughnessFactor));
  }
}
#include <opaque_fragment>`)
  }
  material.needsUpdate = true
}
