import * as THREE from 'three'
import type { MaterialParams } from './materialAdapter'

const uniforms = { time: { value: 0 }, enabled: { value: 1 } }
export function setWaterSurfaceTime(seconds: number): void { if (uniforms.enabled.value > 0) uniforms.time.value = seconds }
export function setWaterSurfaceAnimated(enabled: boolean): void { uniforms.enabled.value = enabled ? 1 : 0 }

/** 水的折射率区别于建筑玻璃；旧文件可用明确的 water/水面材质名兼容。 */
export function isWaterMaterial(params: MaterialParams, name: string): boolean {
  return (params.materialClass === 'glass' && Math.abs((params.ior ?? 1.5) - 1.333) < 0.005)
    || /^(water|water_surface|pool_water|pond_water|水|水面|池水|泳池水)$/i.test(name)
}

/** 保留 PBR 透射与环境反射，仅扰动朝上的表面法线；不移动几何体，池边不会穿模。 */
export function applyWaterSurfaceMaterial(material: THREE.MeshStandardMaterial): void {
  const previous = material.onBeforeCompile
  const cacheKey = material.customProgramCacheKey()
  material.userData.wildWaterSurface = true
  material.customProgramCacheKey = () => cacheKey + ':water-surface-v1'
  material.onBeforeCompile = (shader, renderer) => {
    previous.call(material, shader, renderer)
    shader.uniforms.wildWaterTime = uniforms.time
    shader.uniforms.wildWaterEnabled = uniforms.enabled
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
uniform float wildWaterEnabled;`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
float wildWaterMask = smoothstep(0.8, 0.98, vWildWaterUp) * wildWaterEnabled;
vec2 wildWaterP = vWildWaterPosition.xz;
vec2 wildWaterGradient = vec2(0.9, 0.35) * 0.14 * cos(dot(wildWaterP, vec2(3.5, 1.4)) + wildWaterTime * 1.15)
  + vec2(-0.4, 0.9) * 0.10 * cos(dot(wildWaterP, vec2(-2.4, 5.4)) - wildWaterTime * 0.85)
  + vec2(0.7, -0.7) * 0.03 * cos(dot(wildWaterP, vec2(12.0, -12.0)) + wildWaterTime * 1.7);
vec3 wildWaterNormal = normalize((viewMatrix * vec4(-wildWaterGradient.x, 1.0, -wildWaterGradient.y, 0.0)).xyz);
normal = normalize(mix(normal, wildWaterNormal, wildWaterMask));`)
      .replace('#include <color_fragment>', `#include <color_fragment>
float wildWaterShimmer = sin(dot(vWildWaterPosition.xz, vec2(7.0, 3.0)) + wildWaterTime)
  * sin(dot(vWildWaterPosition.xz, vec2(-4.0, 6.0)) - wildWaterTime * 0.7);
diffuseColor.rgb *= 1.0 + wildWaterShimmer * 0.12 * wildWaterEnabled * smoothstep(0.8, 0.98, vWildWaterUp);`)
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
vec2 wildWaterCausticP = vWildWaterPosition.xz + 0.17 * vec2(sin(vWildWaterPosition.z * 3.7 + wildWaterTime * 0.4), cos(vWildWaterPosition.x * 2.9 - wildWaterTime * 0.3));
float wildWaterCaustic = pow(max(0.0, 1.0 - abs(sin(dot(wildWaterCausticP, vec2(9.0, 3.0)) + wildWaterTime * 0.8)
  + sin(dot(wildWaterCausticP, vec2(-3.0, 8.0)) - wildWaterTime * 0.65)
  + 0.35 * sin(dot(wildWaterCausticP, vec2(5.0, -7.0)) + wildWaterTime * 0.5))), 10.0);
totalEmissiveRadiance += vec3(0.025, 0.045, 0.04) * wildWaterCaustic * wildWaterEnabled * smoothstep(0.8, 0.98, vWildWaterUp);`)
  }
  material.needsUpdate = true
}
