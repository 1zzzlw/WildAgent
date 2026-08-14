import type { SurfaceQuality } from '../wild-core/src/materials'

/**
 * 视口级环境效果开关运行时。
 *
 * 与 ``worldEnvironmentRuntime``（持久化的世界环境状态）不同，这里保存的是
 * 设备/视口相关的性能敏感效果开关，**默认全部关闭**，低端设备不额外负担。
 * 开关通过共享 uniform 暴露给材质与云层 Shader，更新不触发重编译。
 */
export type WorldEffectId =
  | 'clouds'
  | 'puddles'
  | 'ripples'
  | 'dustParticles'
  | 'volumetricFog'
  | 'reflections'

export interface WorldEffectState {
  clouds: boolean
  puddles: boolean
  ripples: boolean
  dustParticles: boolean
  volumetricFog: boolean
  reflections: boolean
}

export const WORLD_EFFECT_ORDER: WorldEffectId[] = [
  'clouds',
  'puddles',
  'ripples',
  'dustParticles',
  'volumetricFog',
  'reflections',
]

export const WORLD_EFFECT_LABELS: Record<WorldEffectId, { label: string; icon: string }> = {
  clouds: { label: '云层', icon: '☁️' },
  puddles: { label: '积水', icon: '🫧' },
  ripples: { label: '波纹', icon: '〰️' },
  dustParticles: { label: '沙尘', icon: '🌫️' },
  volumetricFog: { label: '体积雾', icon: '🌁' },
  reflections: { label: '反射', icon: '✨' },
}

const DEFAULT_EFFECT_STATE: WorldEffectState = {
  clouds: false,
  puddles: false,
  ripples: false,
  dustParticles: false,
  volumetricFog: false,
  reflections: false,
}

type EffectListener = (state: Readonly<WorldEffectState>) => void

const state: WorldEffectState = { ...DEFAULT_EFFECT_STATE }
const listeners = new Set<EffectListener>()

const uniforms = {
  effectTime: { value: 0 },
  clouds: { value: 0 },
  puddles: { value: 0 },
  ripples: { value: 0 },
  dustParticles: { value: 0 },
  volumetricFog: { value: 0 },
  reflections: { value: 0 },
}

/** 共享 uniform 对象；更新 value 不触发材质重新编译。 */
export function getWorldEffectUniforms(): typeof uniforms {
  return uniforms
}

export function getWorldEffectState(): Readonly<WorldEffectState> {
  return state
}

export function updateWorldEffectState(patch: Partial<WorldEffectState>): Readonly<WorldEffectState> {
  let changed = false
  for (const key of WORLD_EFFECT_ORDER) {
    const next = patch[key]
    if (typeof next !== 'boolean' || state[key] === next) continue
    state[key] = next
    uniforms[key].value = next ? 1 : 0
    changed = true
  }
  if (changed) listeners.forEach(listener => listener(state))
  return state
}

export function subscribeWorldEffects(listener: EffectListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 每帧推进全局效果时钟；驱动波纹与云层漂移。 */
export function setWorldEffectTime(seconds: number): void {
  uniforms.effectTime.value = seconds
}

export { type SurfaceQuality }
