import type { ComponentSpec, GeometryElement } from '../wild-core/types'
import type { ComponentCompileContext, ComponentCompiler } from './types'

const MAX_CACHE_ENTRIES = 256
const cache = new Map<string, GeometryElement[]>()
let hits = 0
let misses = 0

/**
 * 仅把组件本身和它显式引用的依附目标纳入缓存键。屋顶没有显式 position
 * 时，其自动原点依赖结构墙，因此屋顶依附组件还需要把墙体纳入缓存键。
 */
export function compileComponentCached(
  component: ComponentSpec,
  context: ComponentCompileContext,
  compile: ComponentCompiler,
): GeometryElement[] {
  const key = createCacheKey(component, context)
  const cached = cache.get(key)
  if (cached) {
    hits++
    cache.delete(key)
    cache.set(key, cached)
    return cloneJson(cached)
  }

  misses++
  const generated = compile(component, context)
  cache.set(key, cloneJson(generated))
  while (cache.size > MAX_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value
    if (oldest === undefined) break
    cache.delete(oldest)
  }
  return generated
}

export function clearComponentCompilationCache(): void {
  cache.clear()
  hits = 0
  misses = 0
}

export function getComponentCompilationCacheStats(): {
  size: number
  hits: number
  misses: number
} {
  return { size: cache.size, hits, misses }
}

function createCacheKey(
  component: ComponentSpec,
  context: ComponentCompileContext,
): string {
  const record = component as unknown as Record<string, unknown>
  const dependencyIds = [record.parentWall, record.parentFloor, record.parentRoof]
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
  const dependencies = context.elements.filter(element => dependencyIds.includes(element.id))
  const parentRoof = typeof record.parentRoof === 'string'
    ? context.elements.find(element => element.id === record.parentRoof && element.type === 'roof')
    : undefined
  if (parentRoof && !('position' in parentRoof) && context.elements.some(element => element.type === 'wall')) {
    dependencies.push(...context.elements.filter(element => element.type === 'wall'))
  }
  return stableSerialize({ component, dependencies })
}

function stableSerialize(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableSerialize).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>)
      .filter(([, child]) => child !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, child]) => `${JSON.stringify(key)}:${stableSerialize(child)}`)
      .join(',')}}`
  }
  return JSON.stringify(value) ?? 'null'
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
