import type * as THREE from 'three'
import { getWorldRenderingUniforms } from '../worldEnvironmentRuntime'

/** 在原 PBR 着色链中分级漫反射；保留纹理、发光、镜面及材质资源生命周期。 */
export function applyToonMaterial(material: THREE.MeshStandardMaterial): void {
  const previous = material.onBeforeCompile
  const cacheKey = material.customProgramCacheKey()
  material.onBeforeCompile = (shader, renderer) => {
    previous.call(material, shader, renderer)
    shader.uniforms.wildToonEnabled = getWorldRenderingUniforms().toonEnabled
    shader.fragmentShader = `uniform float wildToonEnabled;\n${shader.fragmentShader}`
    shader.fragmentShader = shader.fragmentShader.replace('#include <opaque_fragment>', `
      if (wildToonEnabled > 0.5) {
        vec3 wildDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
        vec3 wildLuma = vec3(0.2126, 0.7152, 0.0722);
        float wildIllumination = dot(wildDiffuse, wildLuma) / max(dot(diffuseColor.rgb, wildLuma), 0.0001);
        float wildBand = wildIllumination < 0.32 ? 0.18
          : wildIllumination < 0.7 ? 0.48 : wildIllumination < 1.15 ? 0.8 : 1.2;
        outgoingLight += wildDiffuse * (wildBand / max(wildIllumination, 0.0001) - 1.0);
      }
      #include <opaque_fragment>
    `)
  }
  material.customProgramCacheKey = () => `${cacheKey}|wild-toon-v1`
}
