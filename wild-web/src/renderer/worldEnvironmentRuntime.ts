import type { SurfaceQuality, WorldEnvironmentState } from '../wild-core/src/materials'
import { DEFAULT_WORLD_ENVIRONMENT } from '../wild-core/src/materials'

type EnvironmentListener = (state: Readonly<WorldEnvironmentState>) => void
type RenderingListener = (state: Readonly<WorldRenderingState>) => void

export interface WorldRenderingState {
  surfaceEnabled: boolean
  surfaceQuality: SurfaceQuality
  weatherEnabled: boolean
  weatherQuality: SurfaceQuality
}

const state: WorldEnvironmentState = { ...DEFAULT_WORLD_ENVIRONMENT }
const listeners = new Set<EnvironmentListener>()
const renderingState: WorldRenderingState = {
  surfaceEnabled: true,
  surfaceQuality: 'medium',
  weatherEnabled: true,
  weatherQuality: 'medium',
}
const renderingListeners = new Set<RenderingListener>()

const QUALITY_FACTOR: Record<SurfaceQuality, number> = {
  fallback: 0,
  low: 0.48,
  medium: 0.78,
  high: 1,
}

/** 共享 uniform 对象；更新 value 不会触发材质重新编译。 */
const uniforms = {
  timeOfDay: { value: state.timeOfDay },
  rain: { value: state.rain },
  wetness: { value: state.wetness },
  snow: { value: state.snow },
  dust: { value: state.dust },
  wind: { value: state.wind },
  cloudCoverage: { value: state.cloudCoverage },
  fog: { value: state.fog },
}

/** 所有材质共享这些 uniform；切换画质或关闭功能不触发 Shader 重编译。 */
const renderingUniforms = {
  surfaceEnabled: { value: 1 },
  surfaceQuality: { value: QUALITY_FACTOR.medium },
  weatherEnabled: { value: 1 },
  weatherQuality: { value: QUALITY_FACTOR.medium },
}

export function getWorldEnvironmentState(): Readonly<WorldEnvironmentState> {
  return state
}

export function getWorldEnvironmentUniforms(): typeof uniforms {
  return uniforms
}

export function getWorldRenderingState(): Readonly<WorldRenderingState> {
  return renderingState
}

export function getWorldRenderingUniforms(): typeof renderingUniforms {
  return renderingUniforms
}

export function updateWorldEnvironmentState(
  patch: Partial<WorldEnvironmentState>,
): Readonly<WorldEnvironmentState> {
  let changed = false
  for (const key of Object.keys(state) as Array<keyof WorldEnvironmentState>) {
    const next = patch[key]
    if (typeof next !== 'number' || !Number.isFinite(next)) continue
    const normalized = key === 'timeOfDay'
      ? Math.min(24, Math.max(0, next))
      : Math.min(1, Math.max(0, next))
    if (state[key] === normalized) continue
    state[key] = normalized
    uniforms[key].value = normalized
    changed = true
  }
  if (changed) listeners.forEach(listener => listener(state))
  return state
}

export function subscribeWorldEnvironment(listener: EnvironmentListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function updateWorldRenderingState(
  patch: Partial<WorldRenderingState>,
): Readonly<WorldRenderingState> {
  let changed = false
  if (typeof patch.surfaceEnabled === 'boolean' && patch.surfaceEnabled !== renderingState.surfaceEnabled) {
    renderingState.surfaceEnabled = patch.surfaceEnabled
    renderingUniforms.surfaceEnabled.value = patch.surfaceEnabled ? 1 : 0
    changed = true
  }
  if (typeof patch.weatherEnabled === 'boolean' && patch.weatherEnabled !== renderingState.weatherEnabled) {
    renderingState.weatherEnabled = patch.weatherEnabled
    renderingUniforms.weatherEnabled.value = patch.weatherEnabled ? 1 : 0
    changed = true
  }
  if (patch.surfaceQuality && patch.surfaceQuality !== renderingState.surfaceQuality) {
    renderingState.surfaceQuality = patch.surfaceQuality
    renderingUniforms.surfaceQuality.value = QUALITY_FACTOR[patch.surfaceQuality]
    changed = true
  }
  if (patch.weatherQuality && patch.weatherQuality !== renderingState.weatherQuality) {
    renderingState.weatherQuality = patch.weatherQuality
    renderingUniforms.weatherQuality.value = QUALITY_FACTOR[patch.weatherQuality]
    changed = true
  }
  if (changed) renderingListeners.forEach(listener => listener(renderingState))
  return renderingState
}

export function subscribeWorldRendering(listener: RenderingListener): () => void {
  renderingListeners.add(listener)
  return () => renderingListeners.delete(listener)
}
