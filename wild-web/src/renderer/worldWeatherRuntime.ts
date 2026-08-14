import * as THREE from 'three'
import type { WorldEnvironmentState } from '../wild-core/src/materials'
import { getWorldEffectUniforms } from './worldEffectRuntime'

export const WORLD_WEATHER_PRESET_ORDER = [
  'clear',
  'cloudy',
  'rain',
  'fog',
  'snow',
  'dust',
] as const

export type WorldWeatherPresetId = typeof WORLD_WEATHER_PRESET_ORDER[number]

export interface WorldWeatherPreset {
  label: string
  icon: string
  description: string
  environment: Readonly<Omit<WorldEnvironmentState, 'timeOfDay'>>
}

export const WORLD_WEATHER_PRESETS: Record<WorldWeatherPresetId, WorldWeatherPreset> = {
  clear: {
    label: '晴天', icon: '☀️', description: '通透天空与清晰日照',
    environment: { rain: 0, wetness: 0.04, snow: 0, dust: 0, wind: 0.16, cloudCoverage: 0.08, fog: 0.02 },
  },
  cloudy: {
    label: '多云', icon: '☁️', description: '柔和阴影与较高云量',
    environment: { rain: 0, wetness: 0.12, snow: 0, dust: 0, wind: 0.28, cloudCoverage: 0.72, fog: 0.12 },
  },
  rain: {
    label: '雨天', icon: '🌧️', description: '降雨、湿润表面与低能见度',
    environment: { rain: 0.82, wetness: 0.88, snow: 0, dust: 0, wind: 0.56, cloudCoverage: 0.94, fog: 0.38 },
  },
  fog: {
    label: '雾天', icon: '🌫️', description: '低对比度与近距离空气透视',
    environment: { rain: 0.03, wetness: 0.42, snow: 0, dust: 0, wind: 0.06, cloudCoverage: 0.84, fog: 0.9 },
  },
  snow: {
    label: '雪天', icon: '🌨️', description: '飘雪、积雪响应与冷色天空',
    environment: { rain: 0, wetness: 0.32, snow: 0.78, dust: 0, wind: 0.3, cloudCoverage: 0.88, fog: 0.42 },
  },
  dust: {
    label: '沙尘', icon: '🌪️', description: '暖色尘雾与较低能见度',
    environment: { rain: 0, wetness: 0, snow: 0, dust: 0.82, wind: 0.76, cloudCoverage: 0.46, fog: 0.54 },
  },
}

export interface WorldAtmosphereAppearance {
  cloud: number
  rain: number
  snow: number
  dust: number
  fog: number
  directLightScale: number
  ambientLightScale: number
  exposureScale: number
  tintStrength: number
  backgroundTint: number
  fogColor: number
  groundTint: number
}

export function matchWorldWeatherPreset(
  state: Readonly<WorldEnvironmentState>,
): WorldWeatherPresetId | undefined {
  return WORLD_WEATHER_PRESET_ORDER.find(id => Object.entries(WORLD_WEATHER_PRESETS[id].environment)
    .every(([key, value]) => Math.abs(state[key as keyof WorldEnvironmentState] - value) < 0.001))
}

export function deriveWorldAtmosphere(
  state: Readonly<WorldEnvironmentState>,
  enabled = true,
): WorldAtmosphereAppearance {
  const factor = enabled ? 1 : 0
  const cloud = state.cloudCoverage * factor
  const rain = state.rain * factor
  const snow = state.snow * factor
  const dust = state.dust * factor
  const fog = Math.min(1, Math.max(state.fog, rain * 0.32, snow * 0.24, dust * 0.48) * factor)
  const tintStrength = Math.min(0.88, Math.max(cloud * 0.22, rain * 0.48, snow * 0.42, dust * 0.68, fog * 0.56))

  const dominant = dust >= Math.max(rain, snow)
    ? 'dust'
    : snow >= rain
      ? 'snow'
      : 'rain'
  const palette = dominant === 'dust'
    ? { background: 0x9c8061, fog: 0xb99a72, ground: 0x8a6f50 }
    : dominant === 'snow'
      ? { background: 0xaebdca, fog: 0xd7e0e5, ground: 0xcbd4d8 }
      : { background: 0x657281, fog: 0x8995a0, ground: 0x59636a }

  return {
    cloud,
    rain,
    snow,
    dust,
    fog,
    directLightScale: Math.max(0.24, 1 - cloud * 0.42 - rain * 0.18 - fog * 0.2 - dust * 0.16),
    ambientLightScale: Math.max(0.46, 1 - rain * 0.12 - fog * 0.08 + cloud * 0.05 + snow * 0.12),
    exposureScale: Math.max(0.7, 1 - rain * 0.08 - fog * 0.12 - dust * 0.1 + snow * 0.05),
    tintStrength,
    backgroundTint: palette.background,
    fogColor: palette.fog,
    groundTint: palette.ground,
  }
}

/** 全局雨雪粒子层；与 Blueprint 几何隔离，并被所有蓝图实例共享。 */
export class WorldWeatherVisuals {
  private readonly group = new THREE.Group()
  private readonly rain: THREE.LineSegments
  private readonly snow: THREE.Points
  private readonly dust: THREE.Points
  private readonly rainSeeds = createSeeds(260, 0x2f6e2b1)
  private readonly snowSeeds = createSeeds(220, 0x531ff09)
  private readonly dustSeeds = createSeeds(520, 0x7a3c1d1)
  private rainStrength = 0
  private snowStrength = 0
  private dustStrength = 0
  private wind = 0

  constructor(scene: THREE.Scene) {
    this.group.name = 'WorldWeatherVisuals'
    this.group.renderOrder = 4

    const rainGeometry = new THREE.BufferGeometry()
    rainGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.rainSeeds.length * 2), 3))
    this.rain = new THREE.LineSegments(rainGeometry, new THREE.LineBasicMaterial({
      color: 0xa9c9df,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      fog: true,
    }))
    this.rain.frustumCulled = false

    const snowGeometry = new THREE.BufferGeometry()
    snowGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.snowSeeds.length), 3))
    this.snow = new THREE.Points(snowGeometry, new THREE.PointsMaterial({
      color: 0xf3f7fa,
      size: 0.12,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      fog: true,
    }))
    this.snow.frustumCulled = false

    const dustGeometry = new THREE.BufferGeometry()
    dustGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.dustSeeds.length), 3))
    this.dust = new THREE.Points(dustGeometry, new THREE.PointsMaterial({
      color: 0xb99a72,
      size: 0.17,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      fog: true,
    }))
    this.dust.frustumCulled = false

    this.group.add(this.rain, this.snow, this.dust)
    scene.add(this.group)
  }

  setBounds(center: THREE.Vector3, extent: number, groundY: number): void {
    const radius = Math.max(14, extent * 2.4)
    const height = Math.max(16, extent * 2.2)
    this.group.position.set(center.x, groundY, center.z)
    this.group.scale.set(radius, height, radius)
  }

  setEnvironment(state: Readonly<WorldEnvironmentState>, enabled: boolean): void {
    this.rainStrength = enabled ? state.rain : 0
    this.snowStrength = enabled ? state.snow : 0
    this.dustStrength = enabled ? state.dust : 0
    this.wind = enabled ? state.wind : 0
    const dustEnabled = getWorldEffectUniforms().dustParticles.value > 0.5
    this.rain.visible = this.rainStrength > 0.015
    this.snow.visible = this.snowStrength > 0.015
    this.dust.visible = this.dustStrength > 0.015 && dustEnabled
    this.rain.geometry.setDrawRange(0, Math.floor(260 * this.rainStrength) * 2)
    this.snow.geometry.setDrawRange(0, Math.floor(220 * this.snowStrength))
    this.dust.geometry.setDrawRange(0, Math.floor(520 * this.dustStrength))
    ;(this.rain.material as THREE.LineBasicMaterial).opacity = Math.min(0.68, 0.22 + this.rainStrength * 0.5)
    ;(this.snow.material as THREE.PointsMaterial).opacity = Math.min(0.92, 0.38 + this.snowStrength * 0.58)
    ;(this.dust.material as THREE.PointsMaterial).opacity = Math.min(0.6, 0.18 + this.dustStrength * 0.5)
  }

  tick(deltaSeconds: number): boolean {
    const delta = Math.min(0.05, Math.max(0, deltaSeconds))
    if (this.rain.visible) this.updateRain(delta)
    if (this.snow.visible) this.updateSnow(delta)
    if (this.dust.visible) this.updateDust(delta)
    return this.rain.visible || this.snow.visible || this.dust.visible
  }

  dispose(): void {
    this.group.removeFromParent()
    this.rain.geometry.dispose()
    ;(this.rain.material as THREE.Material).dispose()
    this.snow.geometry.dispose()
    ;(this.snow.material as THREE.Material).dispose()
    this.dust.geometry.dispose()
    ;(this.dust.material as THREE.Material).dispose()
  }

  private updateRain(delta: number): void {
    const positions = this.rain.geometry.getAttribute('position') as THREE.BufferAttribute
    const values = positions.array as Float32Array
    for (let index = 0; index < 260; index++) {
      const seedOffset = index * 3
      const vertexOffset = index * 6
      let y = this.rainSeeds[seedOffset + 1] - delta * (0.72 + this.rainStrength * 1.7)
      let x = this.rainSeeds[seedOffset] + delta * this.wind * 0.08
      if (y < 0) y += 1
      if (x > 0.5) x -= 1
      this.rainSeeds[seedOffset] = x
      this.rainSeeds[seedOffset + 1] = y
      values[vertexOffset] = x
      values[vertexOffset + 1] = y
      values[vertexOffset + 2] = this.rainSeeds[seedOffset + 2]
      values[vertexOffset + 3] = x - this.wind * 0.008
      values[vertexOffset + 4] = y - 0.018 - this.rainStrength * 0.025
      values[vertexOffset + 5] = this.rainSeeds[seedOffset + 2]
    }
    positions.needsUpdate = true
  }

  private updateSnow(delta: number): void {
    const positions = this.snow.geometry.getAttribute('position') as THREE.BufferAttribute
    const values = positions.array as Float32Array
    for (let index = 0; index < 220; index++) {
      const offset = index * 3
      let y = this.snowSeeds[offset + 1] - delta * (0.05 + this.snowStrength * 0.12)
      let x = this.snowSeeds[offset] + delta * this.wind * 0.025
      if (y < 0) y += 1
      if (x > 0.5) x -= 1
      this.snowSeeds[offset] = x
      this.snowSeeds[offset + 1] = y
      values[offset] = x
      values[offset + 1] = y
      values[offset + 2] = this.snowSeeds[offset + 2]
    }
    positions.needsUpdate = true
  }

  private updateDust(delta: number): void {
    const positions = this.dust.geometry.getAttribute('position') as THREE.BufferAttribute
    const values = positions.array as Float32Array
    for (let index = 0; index < 520; index++) {
      const offset = index * 3
      let x = this.dustSeeds[offset] + delta * this.wind * 0.05
      let y = this.dustSeeds[offset + 1] - delta * (0.008 + this.dustStrength * 0.02)
      if (x > 0.5) x -= 1
      if (x < -0.5) x += 1
      if (y < 0) y += 1
      this.dustSeeds[offset] = x
      this.dustSeeds[offset + 1] = y
      values[offset] = x
      values[offset + 1] = y
      values[offset + 2] = this.dustSeeds[offset + 2]
    }
    positions.needsUpdate = true
  }
}

function createSeeds(count: number, initialSeed: number): Float32Array {
  const values = new Float32Array(count * 3)
  let seed = initialSeed >>> 0
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
    return seed / 0xffffffff
  }
  for (let index = 0; index < count; index++) {
    const offset = index * 3
    values[offset] = random() - 0.5
    values[offset + 1] = random()
    values[offset + 2] = random() - 0.5
  }
  return values
}
