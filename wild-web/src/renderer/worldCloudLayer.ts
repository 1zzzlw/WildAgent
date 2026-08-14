import * as THREE from 'three'
import { PROCEDURAL_NOISE_GLSL } from './proceduralMaterials/noise.glsl'
import { getWorldEffectUniforms } from './worldEffectRuntime'
import { getWorldEnvironmentUniforms } from './worldEnvironmentRuntime'

/**
 * 程序化云层穹顶。叠在 THREE.Sky 之上，用 fbm 噪声生成云形，
 * ``cloudCoverage`` 控制覆盖度、``wind`` 控制漂移、``effectTime`` 推进动画。
 * 默认由 ``clouds`` 开关关闭；关闭时整层不绘制，零 GPU 成本。
 */
export class WorldCloudLayer {
  private readonly mesh: THREE.Mesh
  private readonly material: THREE.ShaderMaterial
  private readonly environment = getWorldEnvironmentUniforms()
  private readonly effects = getWorldEffectUniforms()

  constructor(scene: THREE.Scene) {
    const radius = 420
    this.material = new THREE.ShaderMaterial({
      name: 'WorldCloudLayer',
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      fog: false,
      uniforms: {
        uCloudCoverage: this.environment.cloudCoverage,
        uWind: this.environment.wind,
        uTime: this.effects.effectTime,
        uClouds: this.effects.clouds,
      },
      vertexShader: /* glsl */ `
        varying vec3 vWorldDirection;
        void main() {
          vec4 worldPosition = modelMatrix * vec4(position, 1.0);
          vWorldDirection = normalize(worldPosition.xyz);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform float uCloudCoverage;
        uniform float uWind;
        uniform float uTime;
        uniform float uClouds;
        varying vec3 vWorldDirection;
        ${PROCEDURAL_NOISE_GLSL}

        // 把方向映射到云平面；极点附近通过 y 压低避免聚成一点。
        vec2 cloudUv(vec3 dir) {
          float flat = max(length(dir.xz), 0.12);
          return vec2(dir.x / flat, dir.z / flat) * 0.55 + vec2(0.0, dir.y * 0.5);
        }

        void main() {
          if (uClouds < 0.5) { discard; return; }
          vec2 uv = cloudUv(vWorldDirection);
          // 两层不同频率的云，随时间和风漂移。
          float shape = wildFbm(uv * 1.7 + vec2(uTime * (0.006 + uWind * 0.01), uTime * 0.002));
          float detail = wildFbm(uv * 3.6 + vec2(uTime * (0.011 + uWind * 0.016), -uTime * 0.004));
          float cloud = shape * 0.7 + detail * 0.3;
          // 覆盖率越高，越低的阈值也能成云。
          float threshold = 1.0 - uCloudCoverage * 1.3;
          float coverage = smoothstep(threshold, threshold + 0.3, cloud);
          float density = coverage * smoothstep(0.0, 0.1, uCloudCoverage);
          if (density <= 0.001) { discard; return; }
          vec3 cloudColor = mix(vec3(0.7, 0.74, 0.8), vec3(1.0, 1.0, 1.0), smoothstep(0.24, 1.0, cloud));
          gl_FragColor = vec4(cloudColor, density * 0.95);
        }
      `,
    })

    this.mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 48, 24), this.material)
    this.mesh.name = 'WorldCloudLayer'
    this.mesh.renderOrder = 1
    this.mesh.frustumCulled = false
    scene.add(this.mesh)
  }

  setVisible(visible: boolean): void {
    this.mesh.visible = visible
  }

  dispose(): void {
    this.mesh.removeFromParent()
    this.mesh.geometry.dispose()
    this.material.dispose()
  }
}
