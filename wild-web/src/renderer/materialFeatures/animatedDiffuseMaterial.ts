import * as THREE from 'three'
import { getWorldRenderingUniforms } from '../worldEnvironmentRuntime'

/** 只分级直射漫反射；贴图、灯光颜色、阴影、镜面和自发光仍走原材质管线。 */
export function applyAnimatedDiffuseMaterial(material: THREE.MeshStandardMaterial): void {
  const previous = material.onBeforeCompile
  const cacheKey = material.customProgramCacheKey()
  material.onBeforeCompile = (shader, renderer) => {
    previous.call(material, shader, renderer)
    shader.uniforms.wildToonEnabled = getWorldRenderingUniforms().toonEnabled
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
uniform float wildToonEnabled;
float wildAnimatedDiffuse(float cosine) {
  // 色阶边缘按像素覆盖范围平滑，拖动相机时避免硬阈值闪烁。
  float aa = clamp(fwidth(cosine), 0.003, 0.04);
  return smoothstep(0.04 - aa, 0.04 + aa, cosine) * (
    0.26
    + 0.20 * smoothstep(0.25 - aa, 0.25 + aa, cosine)
    + 0.22 * smoothstep(0.50 - aa, 0.50 + aa, cosine)
    + 0.19 * smoothstep(0.75 - aa, 0.75 + aa, cosine)
    + 0.13 * smoothstep(0.95 - aa, 0.95 + aa, cosine)
  );
}`)
      .replace('#include <lights_physical_pars_fragment>', THREE.ShaderChunk.lights_physical_pars_fragment.replace(
        'reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );',
        `vec3 wildDiffuseIrradiance = irradiance;
  if (wildToonEnabled > 0.5) {
    wildDiffuseIrradiance = wildAnimatedDiffuse(dotNL) * directLight.color;
  }
  reflectedLight.directDiffuse += wildDiffuseIrradiance * BRDF_Lambert( material.diffuseColor );`,
      ))
  }
  material.customProgramCacheKey = () => `${cacheKey}|wild-animated-diffuse-v1`
}
