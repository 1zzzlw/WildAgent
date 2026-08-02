import type {
  Blueprint,
  ComponentSpec,
  GeometryElement,
} from '../wild-core/types'

/** 单个组合构件编译时可读取的场景上下文。 */
export interface ComponentCompileContext {
  elements: readonly GeometryElement[]
}

/** 每种组合构件的纯函数编译接口。 */
export type ComponentCompiler<T extends ComponentSpec = ComponentSpec> = (
  component: T,
  context: ComponentCompileContext,
) => GeometryElement[]

/** 与 wild-core EngineDiagnostic 结构兼容，便于合并到渲染诊断。 */
export interface ComponentCompileDiagnostic {
  level: 'error'
  code: 'COMPONENT_COMPILE_FAILED'
  message: string
  elementId: string
  elementType: string
}

export interface ComponentCompilationResult {
  blueprint: Blueprint
  diagnostics: ComponentCompileDiagnostic[]
  mapping: ComponentCompilationMapping
}

/** 编译前后的双向 ID 映射，供视口拾取和组件级编辑使用。 */
export interface ComponentCompilationMapping {
  generatedElementIdsByComponentId: Record<string, string[]>
  componentIdByGeneratedElementId: Record<string, string>
}

/**
 * 构件编译的预期错误。field 用于把参数问题定位到具体字段，而不是让
 * renderer 最后只报告一个模糊的 ELEMENT_BUILD_FAILED。
 */
export class ComponentCompileError extends Error {
  readonly field?: string

  constructor(message: string, field?: string) {
    super(message)
    this.name = 'ComponentCompileError'
    this.field = field
  }
}
