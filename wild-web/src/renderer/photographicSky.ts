import * as THREE from 'three'
import type { TimeOfDay, TimePreset } from './defaultWorldLook'
import type { WorldAtmosphereAppearance } from './worldWeatherRuntime'

// 实际 CC0 全景的来源和处理记录见 public/skies/sources.json。
const SUN_U: Record<TimeOfDay, number> = { day: .599609375, dawn: .5986328125, sunset: .673828125, night: .619140625 }
const BRIGHTNESS: Record<TimeOfDay, number> = { day: 1, dawn: .75, sunset: .75, night: .24 }

/** 一次采样的静态照片天空。画面与 IBL 共用朝向、天气色和亮度。 */
export class PhotographicSky {
  readonly mesh: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>
  readonly environmentMesh: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>
  private readonly textures = new Map<TimeOfDay, THREE.Texture>()
  private readonly loading = new Set<TimeOfDay>()
  private desired: TimeOfDay = 'day'
  private disposed = false
  private visible = true
  private readonly onLoaded: () => void

  constructor(onLoaded: () => void) {
    this.onLoaded = onLoaded
    const material = new THREE.ShaderMaterial({
      name: 'PhotographicSky', side: THREE.BackSide, depthWrite: false,
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
          vec3 color = mix(texture2D(panorama, uv).rgb, tint, haze);
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

  get ready(): boolean { return this.textures.has(this.desired) }

  update(preset: TimePreset, atmosphere: WorldAtmosphereAppearance, sun: THREE.Vector3): void {
    this.desired = preset.sky
    const uniforms = this.mesh.material.uniforms
    uniforms.rotation.value = SUN_U[this.desired] - .5 - Math.atan2(sun.z,sun.x) / (Math.PI*2)
    uniforms.brightness.value = BRIGHTNESS[this.desired] / preset.exposure
    uniforms.tint.value.setHex(atmosphere.backgroundTint)
    uniforms.haze.value = Math.min(.94, atmosphere.tintStrength + atmosphere.cloud * .35)
    const texture = this.textures.get(this.desired)
    if (texture) {
      this.textures.delete(this.desired)
      this.textures.set(this.desired, texture)
      uniforms.panorama.value = texture
    } else if (!this.loading.has(this.desired)) {
      const time = this.desired
      this.loading.add(time)
      new THREE.TextureLoader().load(`${import.meta.env.BASE_URL}skies/${time}.webp`, loaded => {
        this.loading.delete(time)
        if (this.disposed) { loaded.dispose(); return }
        loaded.colorSpace = THREE.SRGBColorSpace
        loaded.wrapS = THREE.RepeatWrapping
        this.textures.set(time, loaded)
        // 只常驻当前一张高清全景，限制显存；再次切换复用浏览器的 HTTP 缓存。
        while (this.textures.size > 1) {
          const oldest = [...this.textures.keys()].find(key => key !== this.desired)!
          this.textures.get(oldest)!.dispose()
          this.textures.delete(oldest)
        }
        if (this.desired === time) this.onLoaded()
      }, undefined, () => {
        // 失败沿用程序化天空，保留失败标记以免渲染期间重复请求。
        if (!this.disposed && this.desired === time) this.onLoaded()
      })
    }
    this.mesh.visible = this.ready && this.visible
    this.environmentMesh.visible = this.ready
  }

  setVisible(visible: boolean): void {
    this.visible = visible
    this.mesh.visible = visible && this.ready
  }

  dispose(): void {
    this.disposed = true
    this.mesh.removeFromParent()
    this.environmentMesh.removeFromParent()
    this.mesh.geometry.dispose()
    this.mesh.material.dispose()
    this.textures.forEach(texture => texture.dispose())
    this.textures.clear()
  }
}
