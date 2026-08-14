export type TimeOfDay = 'day' | 'sunset' | 'night'
export type ViewMode = 'editor' | 'presentation'
export type QualityLevel = 'low' | 'medium' | 'high'
export type CameraPresetId = 'corner' | 'human' | 'bird' | 'front'
export type EnvironmentPresetId = 'minimal' | 'meadow' | 'alpine' | 'desert' | 'autumn'

export interface TimePreset {
  label: string
  icon: string
  background: number
  exposure: number
  skyVisible: boolean
  turbidity: number
  rayleigh: number
  mieCoefficient: number
  mieDirectionalG: number
  sunPhi: number
  sunTheta: number
  directionalColor: number
  directionalIntensity: number
  hemisphereSkyColor: number
  hemisphereGroundColor: number
  hemisphereIntensity: number
  groundColor: number
  fogColor: number
}

export interface QualityPreset {
  label: string
  pixelRatio: number
  shadowMapSize: number
  ssao: boolean
  bloom: boolean
}

export interface CameraPreset {
  label: string
  direction: [number, number, number]
}

export interface EnvironmentPreset {
  label: string
  icon: string
  groundColor: number
  fogColor: number
  sunAzimuthOffset: number
  directLightScale: number
  ambientLightScale: number
  exposureScale: number
  shadowOpacity: number
}

export const TIME_ORDER: TimeOfDay[] = ['day', 'sunset', 'night']
export const TIME_PRESETS: Record<TimeOfDay, TimePreset> = {
  day: {
    label: '白天', icon: '☀️', background: 0xb9c9d8, exposure: 1.08, skyVisible: true,
    turbidity: 3.2, rayleigh: 1.72, mieCoefficient: 0.005, mieDirectionalG: 0.81,
    sunPhi: 48, sunTheta: 135, directionalColor: 0xfff1d6, directionalIntensity: 2.68,
    hemisphereSkyColor: 0xddeeff, hemisphereGroundColor: 0x665544,
    hemisphereIntensity: 0.62, groundColor: 0x7c8378, fogColor: 0xb9c9d8,
  },
  sunset: {
    label: '黄昏', icon: '🌇', background: 0x6f4054, exposure: 0.9, skyVisible: true,
    turbidity: 10, rayleigh: 2.8, mieCoefficient: 0.02, mieDirectionalG: 0.9,
    sunPhi: 84, sunTheta: 245, directionalColor: 0xff8a4c, directionalIntensity: 1.82,
    hemisphereSkyColor: 0xffa27d, hemisphereGroundColor: 0x34283f,
    hemisphereIntensity: 0.38, groundColor: 0x5b4b48, fogColor: 0x6f4054,
  },
  night: {
    label: '夜晚', icon: '🌙', background: 0x050914, exposure: 0.68, skyVisible: false,
    turbidity: 2, rayleigh: 0.2, mieCoefficient: 0.001, mieDirectionalG: 0.7,
    sunPhi: 108, sunTheta: 220, directionalColor: 0x9dbbff, directionalIntensity: 0.32,
    hemisphereSkyColor: 0x182442, hemisphereGroundColor: 0x08070d,
    hemisphereIntensity: 0.2, groundColor: 0x111722, fogColor: 0x050914,
  },
}

export const QUALITY_ORDER: QualityLevel[] = ['low', 'medium', 'high']
export const QUALITY_PRESETS: Record<QualityLevel, QualityPreset> = {
  low: { label: '流畅', pixelRatio: 1, shadowMapSize: 1024, ssao: false, bloom: false },
  medium: { label: '均衡', pixelRatio: 1.5, shadowMapSize: 2048, ssao: true, bloom: false },
  high: { label: '精细', pixelRatio: 2, shadowMapSize: 4096, ssao: true, bloom: true },
}

export const CAMERA_ORDER: CameraPresetId[] = ['corner', 'human', 'bird', 'front']
export const CAMERA_PRESETS: Record<CameraPresetId, CameraPreset> = {
  corner: { label: '街角', direction: [1, 0.62, 1] },
  human: { label: '人视', direction: [1, 0.18, 1] },
  bird: { label: '鸟瞰', direction: [0.8, 1.25, 0.8] },
  front: { label: '正立面', direction: [0, 0.12, 1] },
}

export const ENVIRONMENT_ORDER: EnvironmentPresetId[] = [
  'minimal', 'meadow', 'alpine', 'desert', 'autumn',
]
export const ENVIRONMENT_PRESETS: Record<EnvironmentPresetId, EnvironmentPreset> = {
  minimal: {
    label: '极简', icon: '◻️', groundColor: 0x747b73, fogColor: 0xb9c9d8,
    sunAzimuthOffset: 0, directLightScale: 1, ambientLightScale: 0.9, exposureScale: 1,
    shadowOpacity: 0.22,
  },
  meadow: {
    label: '草地', icon: '🌿', groundColor: 0x526d42, fogColor: 0xadc2ae,
    sunAzimuthOffset: -18, directLightScale: 1.16, ambientLightScale: 0.72, exposureScale: 0.96,
    shadowOpacity: 0.28,
  },
  alpine: {
    label: '雪山', icon: '🏔️', groundColor: 0xc9d1d5, fogColor: 0xc6d2da,
    sunAzimuthOffset: 16, directLightScale: 1.22, ambientLightScale: 0.82, exposureScale: 0.92,
    shadowOpacity: 0.3,
  },
  desert: {
    label: '沙漠', icon: '🏜️', groundColor: 0xb9844f, fogColor: 0xd2ad7f,
    sunAzimuthOffset: 30, directLightScale: 1.3, ambientLightScale: 0.66, exposureScale: 0.92,
    shadowOpacity: 0.34,
  },
  autumn: {
    label: '秋林', icon: '🍂', groundColor: 0x665c3d, fogColor: 0xb39a78,
    sunAzimuthOffset: -32, directLightScale: 1.18, ambientLightScale: 0.68, exposureScale: 0.92,
    shadowOpacity: 0.32,
  },
}
