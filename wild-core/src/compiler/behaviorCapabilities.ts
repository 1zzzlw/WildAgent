import type { InteractiveElementBehavior } from '../../types'
import { ComponentCompileError } from './types'

export interface ExtensionBehaviorCapability {
  name: string
  description: string
  validate: (config: Record<string, unknown>) => void
}

const capabilities = new Map<string, ExtensionBehaviorCapability>()
const legacyKinds = new Set(['opening', 'light', 'elevator', 'rotor'])

/** 能力定义由 Core 加载，主线程、Worker 与离线编译使用相同契约。 */
export function registerExtensionBehaviorCapability(capability: ExtensionBehaviorCapability): void {
  if (!capability.name.trim() || capabilities.has(capability.name)) {
    throw new Error(`行为能力名称为空或重复: ${capability.name}`)
  }
  capabilities.set(capability.name, capability)
}

export function getExtensionBehaviorCapabilities(): Array<{ name: string; description: string }> {
  return [...capabilities.values()].map(({ name, description }) => ({ name, description }))
}

export function validateElementBehavior(value: unknown): asserts value is InteractiveElementBehavior {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ComponentCompileError('配方行为必须是对象', 'behavior')
  }
  const behavior = value as Record<string, unknown>
  if (typeof behavior.kind === 'string' && legacyKinds.has(behavior.kind)) return
  if (behavior.kind !== 'extension' || typeof behavior.capability !== 'string') {
    throw new ComponentCompileError(`配方行为 kind 不受支持: ${String(behavior.kind)}`, 'behavior')
  }
  const capability = capabilities.get(behavior.capability)
  if (!capability) throw new ComponentCompileError(`未注册行为能力: ${behavior.capability}`, 'behavior.capability')
  if (!behavior.config || typeof behavior.config !== 'object' || Array.isArray(behavior.config)) {
    throw new ComponentCompileError('行为 config 必须是对象', 'behavior.config')
  }
  capability.validate(behavior.config as Record<string, unknown>)
}

registerExtensionBehaviorCapability({
  name: 'video',
  description: '将可访问的视频资源播放到指定表面，支持交互播放/暂停、循环与静音',
  validate(config) {
    if (typeof config.src !== 'string') {
      throw new ComponentCompileError('视频 src 必须是字符串', 'behavior.config.src')
    }
    const src = config.src.trim()
    if (src && (/^[a-z]:[\\/]|^\\\\/i.test(src)
      || !['http:', 'https:', 'blob:'].includes(new URL(src, 'https://wild.local/').protocol))) {
      throw new ComponentCompileError('视频 src 须为 HTTP(S)、blob URL 或相对资源路径；本地文件须先通过资源接口提供', 'behavior.config.src')
    }
    for (const field of ['loop', 'muted', 'autoplay']) {
      if (config[field] !== undefined && typeof config[field] !== 'boolean') {
        throw new ComponentCompileError(`视频 ${field} 必须是布尔值`, `behavior.config.${field}`)
      }
    }
  },
})
