import * as THREE from 'three'
import type { TimeOfDay, TimePreset } from './defaultWorldLook'
import type { WorldAtmosphereAppearance } from './worldWeatherRuntime'
import { loadSkyTexture } from './skyTextureLoader'
import type { SkyTextureQuality } from './skyTextureLoader'

// 实际 CC0 全景的来源和处理记录见 public/skies/sources.json。
const SUN_U: Record<TimeOfDay, number> = { day: .599609375, dawn: .5986328125, sunset: .673828125, night: .619140625 }
const BRIGHTNESS: Record<TimeOfDay, number> = { day: 1, dawn: .75, sunset: .75, night: .24 }

/** 一次采样的静态照片天空。画面与 IBL 共用朝向、天气色和亮度。 */
export class PhotographicSky {
  readonly mesh: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>
  readonly environmentMesh: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>
  private texture: THREE.Texture | null = null
  private quality: SkyTextureQuality | null = null
  private desired: TimeOfDay | null = null
  private generation = 0
  private failed = false
  private completion: Promise<void> = Promise.resolve()
  private completeLoad: () => void = () => {}
  private disposed = false
  private visible = true
  private readonly onLoaded: (quality: SkyTextureQuality | 'error') => void

  constructor(onLoaded: (quality: SkyTextureQuality | 'error') => void) {
    this.onLoaded = onLoaded
    const material = new THREE.ShaderMaterial({
      name: 'PhotographicSky', side: THREE.BackSide, depthWrite: false,
      extensions: { derivatives: true, shaderTextureLOD: true },
      uniforms: { panorama: {value: null}, rotation: {value: 0}, brightness: {value: 1},
        tint: {value: new THREE.Color()}, haze: {value: 0} },
      vertexShader: `varying vec3 direction;
        void main() {
          direction = position;
          gl_Position = projectionMatrix * vec4(mat3(viewMatrix) * position, 1.0);
          gl_Position.z = gl_Position.w;
        }`,
      fragmentShader: `uniform sampler2D panorama; uniform float rotation; uniform float brightness;
        uniform vec3 tint; uniform float haze; varying vec3 direction;
        void main() {
          vec3 d = normalize(direction);
          vec2 uv = vec2(atan(d.z,d.x) / 6.28318530718 + 0.5 + rotation, asin(clamp(d.y,-1.0,1.0)) / 3.14159265359 + 0.5);
          // atan 在经线接缝跨越一整圈；修正梯度，保留正常 mip/各向异性采样。
          vec2 dx = dFdx(uv), dy = dFdy(uv);
          dx.x -= floor(dx.x + 0.5); dy.x -= floor(dy.x + 0.5);
          #if __VERSION__ >= 300 || defined(GL_EXT_shader_texture_lod)
            vec3 sampleColor = texture2DGradEXT(panorama, uv, dx, dy).rgb;
          #else
            vec3 sampleColor = texture2D(panorama, uv).rgb;
          #endif
          vec3 color = mix(sampleColor, tint, haze);
          gl_FragColor = vec4(color * brightness, 1.0);
        }`,
    })
    this.mesh = new THREE.Mesh(new THREE.SphereGeometry(1,32,16), material)
    this.mesh.name = 'PhotographicSky'
    this.mesh.frustumCulled = false
    this.mesh.renderOrder = -1000
    this.mesh.visible = false
    this.environmentMesh = this.mesh.clone()
  }

  get ready(): boolean { return this.texture !== null }

  get highResolutionReady(): boolean { return this.quality === 'full' }

  async waitForHighResolution(): Promise<void> {
    let pending: Promise<void>
    do { pending = this.completion; await pending }
    while (!this.disposed && pending !== this.completion)
  }

  update(preset: TimePreset, atmosphere: WorldAtmosphereAppearance, sun: THREE.Vector3): void {
    if (this.disposed) return
    if (this.desired !== preset.sky) this.load(preset.sky)
    const uniforms = this.mesh.material.uniforms
    uniforms.rotation.value = SUN_U[preset.sky] - .5 - Math.atan2(sun.z,sun.x) / (Math.PI*2)
    uniforms.brightness.value = BRIGHTNESS[preset.sky] / preset.exposure
    uniforms.tint.value.setHex(atmosphere.backgroundTint)
    // 照片已含云层；云量只影响照明，不再次把照片混成低对比度灰色。
    uniforms.haze.value = Math.min(.88, Math.max(atmosphere.fog * .88, atmosphere.rain * .35,
      atmosphere.snow * .4, atmosphere.dust * .75))
    this.mesh.visible = this.ready && this.visible
    this.environmentMesh.visible = this.highResolutionReady
  }

  private load(time: TimeOfDay): void {
    this.completeLoad()
    this.completion = new Promise(resolve => { this.completeLoad = resolve })
    const complete = this.completeLoad
    this.desired = time
    this.failed = false
    const generation = ++this.generation
    this.texture?.dispose()
    this.texture = null
    this.quality = null
    this.mesh.material.uniforms.panorama.value = null
    const isCurrent = () => !this.disposed && !this.failed && generation === this.generation
    for (const quality of ['preview', 'full'] as const) {
      void loadSkyTexture(time, quality, isCurrent).then(texture => {
        if (!texture) return
        if (!isCurrent() || quality === 'preview' && this.highResolutionReady) { texture.dispose(); return }
        const previous = this.texture
        this.texture = texture
        this.quality = quality
        this.mesh.material.uniforms.panorama.value = texture
        this.mesh.visible = this.visible
        this.environmentMesh.visible = this.highResolutionReady
        previous?.dispose()
        this.onLoaded(quality)
      }).catch(() => {
        if (quality !== 'full' || !isCurrent()) return
        this.failed = true
        this.texture?.dispose()
        this.texture = null
        this.quality = null
        this.mesh.material.uniforms.panorama.value = null
        this.mesh.visible = this.environmentMesh.visible = false
        this.onLoaded('error')
      }).finally(() => { if (quality === 'full') complete() })
    }
  }

  setVisible(visible: boolean): void {
    this.visible = visible
    this.mesh.visible = visible && this.ready
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.completeLoad()
    this.mesh.removeFromParent()
    this.environmentMesh.removeFromParent()
    this.mesh.geometry.dispose()
    this.mesh.material.dispose()
    this.texture?.dispose()
    this.texture = null
    this.quality = null
    this.mesh.material.uniforms.panorama.value = null
    this.mesh.visible = this.environmentMesh.visible = false
  }
}
