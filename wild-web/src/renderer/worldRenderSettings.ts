import * as THREE from 'three'
import { ENVIRONMENT_PRESETS, QUALITY_PRESETS, TIME_PRESETS } from './defaultWorldLook'
import type { EnvironmentPresetId, QualityLevel, TimeOfDay } from './defaultWorldLook'
import { getWorldEnvironmentState, getWorldRenderingState } from './worldEnvironmentRuntime'
import { deriveWorldAtmosphere } from './worldWeatherRuntime'
import { worldLookRuntime } from './worldLookRuntime'
import type { WorldLightingRig } from './lightingRuntime'
import type { WorldPostProcessingRuntime } from './postProcessingRuntime'

/** 视口和离线展示出图使用同一组色彩、阴影与画质约定。 */
export function configureWorldRenderer(renderer: THREE.WebGLRenderer): void {
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.shadowMap.autoUpdate = false
  renderer.info.autoReset = false
}

export function applyWorldRenderQuality(renderer: THREE.WebGLRenderer, post: WorldPostProcessingRuntime,
  lighting: WorldLightingRig | null, quality: QualityLevel, time: TimeOfDay, devicePixelRatio = 1): void {
  const preset = QUALITY_PRESETS[quality]
  const ratio = Math.min(devicePixelRatio, preset.pixelRatio)
  renderer.setPixelRatio(ratio)
  post.setPixelRatio(ratio)
  post.setMsaaSamples(4)
  post.setAmbientOcclusion(quality === 'high' ? 'gtao' : preset.ssao ? 'ssao' : 'off')
  post.setBloomEnabled(preset.bloom && time === 'night')
  lighting?.setShadowMapSize(preset.shadowMapSize, renderer.capabilities.maxTextureSize)
  renderer.shadowMap.needsUpdate = true
}

export function resolveWorldIllumination(time: TimeOfDay, environment: EnvironmentPresetId) {
  const preset = TIME_PRESETS[time], setting = ENVIRONMENT_PRESETS[environment]
  const appearance = worldLookRuntime.getActiveProfile().appearance
  const atmosphere = deriveWorldAtmosphere(getWorldEnvironmentState(), getWorldRenderingState().weatherEnabled)
  const sunDirection = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(preset.sunPhi),
    THREE.MathUtils.degToRad(preset.sunTheta + setting.sunAzimuthOffset))
  return {
    preset, atmosphere, sunDirection,
    keyDirection: time === 'night' ? sunDirection.clone().negate() : sunDirection.clone(),
    background: new THREE.Color(preset.background).lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength),
    exposure: preset.exposure * setting.exposureScale * (appearance?.exposureScale ?? 1) * atmosphere.exposureScale,
    groundColor: resolveWorldEnvironmentColor('groundColor', time, environment),
    lighting: {
      hemisphereSkyColor: new THREE.Color(preset.hemisphereSkyColor).lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength * 0.38).getHex(),
      hemisphereGroundColor: new THREE.Color(preset.hemisphereGroundColor).lerp(new THREE.Color(atmosphere.groundTint), atmosphere.tintStrength * 0.38).getHex(),
      hemisphereIntensity: preset.hemisphereIntensity * setting.ambientLightScale * (appearance?.ambientLightScale ?? 1) * atmosphere.ambientLightScale,
      keyColor: new THREE.Color(preset.directionalColor).lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength * 0.22).getHex(),
      keyIntensity: preset.directionalIntensity * setting.directLightScale * (appearance?.directLightScale ?? 1) * atmosphere.directLightScale,
    },
  }
}

export function resolveWorldEnvironmentColor(kind: 'groundColor' | 'fogColor', time: TimeOfDay, environment: EnvironmentPresetId): THREE.Color {
  const atmosphere = deriveWorldAtmosphere(getWorldEnvironmentState(), getWorldRenderingState().weatherEnabled)
  const timeBlend = time === 'night' ? 0.76 : time === 'sunset' ? 0.42 : 0.08
  return new THREE.Color(ENVIRONMENT_PRESETS[environment][kind])
    .lerp(new THREE.Color(TIME_PRESETS[time][kind]), timeBlend)
    .lerp(new THREE.Color(kind === 'groundColor' ? atmosphere.groundTint : atmosphere.fogColor), atmosphere.tintStrength)
}
