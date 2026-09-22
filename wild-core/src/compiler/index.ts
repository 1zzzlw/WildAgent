import type { Blueprint, ComponentSpec, GeometryElement } from '../wild-core/types'
import {
  getComponentCapabilities,
  getComponentCompiler,
  registerComponentCompiler,
} from './componentRegistry'
import type {
  ComponentCompilationResult,
  ComponentCompileDiagnostic,
} from './types'
import {
  clearComponentCompilationCache,
  compileComponentCached,
  getComponentCompilationCacheStats,
} from './componentCache'
import { applyComponentMaterialDefaults, COMPONENT_MATERIAL } from './componentMaterials'

/**
 * 将 geometry.components 展开为 wild-core 已支持的 geometry.elements。
 *
 * 源 Blueprint 不会被修改。某个组件失败时，其他组件与原生 elements 仍会
 * 被编译和渲染，失败信息通过结构化诊断返回。
 */
export function compileBlueprintComponents(
  source: Blueprint,
): ComponentCompilationResult {
  if ((source.geometry.components || []).length === 0) {
    return { blueprint: source, diagnostics: [], mapping: createEmptyMapping() }
  }

  const blueprint = cloneJson(source)
  const components = blueprint.geometry.components || []
  const materials = blueprint.materials || (blueprint.materials = {})
  applyComponentMaterialDefaults(components, materials)
  const elements = blueprint.geometry.elements || []
  const sourceElements = blueprint.geometry.elements || []
  const diagnostics: ComponentCompileDiagnostic[] = []
  const mapping = createEmptyMapping()
  const usedIds = new Set(elements.map(element => element.id))
  const componentIds = new Set<string>()

  for (const component of components) {
    const componentType = String((component as { type?: unknown }).type || 'unknown')
    const componentId = String((component as { id?: unknown }).id || '')

    if (!componentId) {
      diagnostics.push(createDiagnostic(component, '组合构件缺少非空 id'))
      continue
    }
    if (componentIds.has(componentId)) {
      diagnostics.push(createDiagnostic(component, `组合构件 id 重复: ${componentId}`))
      continue
    }
    componentIds.add(componentId)
    if (usedIds.has(componentId)) {
      diagnostics.push(createDiagnostic(
        component,
        `组合构件 id 与原生元素 id 冲突: ${componentId}`,
      ))
      continue
    }

    const registration = getComponentCompiler(componentType)
    if (!registration) {
      diagnostics.push(createDiagnostic(
        component,
        `没有注册组合构件类型 "${componentType}" 的编译器`,
      ))
      continue
    }

    try {
      const generated = compileComponentCached(
        component,
        { elements: sourceElements, components },
        registration.compile,
      )
      if (component.draggable) {
        for (const element of generated) {
          (element as GeometryElement & { _draggable?: boolean })._draggable = true
        }
      }
      const generatedIds = new Set<string>()
      for (const element of generated) {
        if (!element.id) throw new Error('编译结果包含空 element.id')
        if (generatedIds.has(element.id) || usedIds.has(element.id)) {
          throw new Error(`编译结果 element.id 冲突: ${element.id}`)
        }
        generatedIds.add(element.id)
      }
      elements.push(...generated)
      for (const id of generatedIds) usedIds.add(id)
      mapping.generatedElementIdsByComponentId[componentId] = [...generatedIds]
      for (const id of generatedIds) {
        mapping.componentIdByGeneratedElementId[id] = componentId
      }
    } catch (error) {
      diagnostics.push(createDiagnostic(
        component,
        error instanceof Error ? error.message : String(error),
      ))
    }
  }

  blueprint.geometry.elements = elements
  delete blueprint.geometry.components
  return { blueprint, diagnostics, mapping }
}

export {
  getComponentCapabilities,
  getComponentCompiler,
  registerComponentCompiler,
  clearComponentCompilationCache,
  getComponentCompilationCacheStats,
  COMPONENT_MATERIAL,
}
export type {
  ComponentCompilationResult,
  ComponentCompileContext,
  ComponentCompileDiagnostic,
  ComponentCompilationMapping,
  ComponentCompiler,
} from './types'

function createEmptyMapping(): import('./types').ComponentCompilationMapping {
  return {
    generatedElementIdsByComponentId: {},
    componentIdByGeneratedElementId: {},
  }
}

function createDiagnostic(
  component: Partial<ComponentSpec> | Record<string, unknown>,
  message: string,
): ComponentCompileDiagnostic {
  return {
    level: 'error',
    code: 'COMPONENT_COMPILE_FAILED',
    message,
    elementId: String(component.id || '?'),
    elementType: String(component.type || 'unknown'),
  }
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
