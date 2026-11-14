import type { GeometryElement } from '../../../types'

/**
 * 构件配方：一份**数据**描述一个构件怎么从零件拼出来。
 *
 * 设计边界（与 `primitive/registry.ts` 的「蓝图不能携带 JS」一致）：
 * 配方只解释白名单表达式，不能调用任意代码。宿主求解由 Core 维护；
 * 已有 rotor / elevator / light / opening 行为继续兼容，新能力通过
 * extension + 已注册能力名接入，并由统一运行时管理。
 *
 * 新组件优先组合已有能力；只有新增能力本身才需要增加求解器或行为处理器，
 * 不按组件名称增加渲染分支。
 */

/** 表达式叶子：`{ $: 'width / 2' }`。任何不是这种形状的值都按字面量处理。 */
export interface RecipeExpression {
  $: string
}

/** 元素字段值：字面量 / 表达式叶子 / 由二者组成的数组与对象。 */
export type RecipeValue =
  | string
  | number
  | boolean
  | null
  | RecipeExpression
  | RecipeValue[]
  | { [key: string]: RecipeValue }

export type RecipeHostKind =
  /** `component.position` 已是世界坐标；不做任何宿主求解。 */
  | 'position'
  /** 无宿主：所有坐标都是绝对世界坐标（路径类构件）。 */
  | 'none'
  /** 挂墙：`from` 是 [沿墙距离, 底标高, 法向偏移]，需要解析父墙帧。 */
  | 'wall'
  /** 屋面：`position` 相对屋面求解；没给 `parentRoof` 时按绝对坐标。 */
  | 'roof'

export interface RecipeParam {
  type: 'number' | 'integer' | 'vec3' | 'string'
  default?: number | string | boolean | number[]
  min?: number
  max?: number
  step?: number
  label?: string
}

export interface RecipeGuard {
  /** 为假则拒绝编译；实际值是表达式求值结果。 */
  expr: string
  message: string
  field?: string
}

export type RecipeRepeatKind =
  /** 沿固定步长线性复制；提供 i / n / t。 */
  | 'linear'
  /** 沿 Y 逐层复制；提供 i / n / t。 */
  | 'stack'
  /** 绕 Y 轴极坐标复制；提供 i / n / t / angle（弧度）。 */
  | 'polar'

export interface RecipeRepeat {
  kind: RecipeRepeatKind
  /** 副本数，表达式求值后取整。 */
  count: string
  /** linear：每次的位移向量。 */
  step?: [string, string, string]
  /** stack：每次的 Y 位移。 */
  stepY?: string
  /** polar：复制半径。 */
  radius?: string
  /** polar：起始角（弧度），默认 0。 */
  startAngle?: string
}

/**
 * 一条元素模板。**除保留键外，其余键原样进入生成的 element** ——
 * 所以 `shape` / `dimensions` / `radius` / `material` / `label` 这些字段名
 * 必须与引擎 schema 一致，不要在配方里发明新拼写。
 */
export interface RecipeElementNode {
  /** 保留键：元素 id 模板，`{i}` 这类花括号段按表达式求值。 */
  id: string
  /** 保留键：元素类型。 */
  type: 'primitive' | 'solid' | 'opening'
  /** 保留键：复制规则。 */
  repeat?: RecipeRepeat
  /** 保留键：写入 `_interaction`；extension 能力必须先在 Core 注册。 */
  behavior?: RecipeValue
  [field: string]: RecipeValue | RecipeRepeat | undefined
}

export interface ComponentRecipe {
  /** 与 `component.type` 对应；同一 type 只能有一份配方。 */
  type: string
  description: string
  host: RecipeHostKind
  /**
   * 构件面板上的显示名与图标。**显示名只在这里声明一次** —— 面板不再维护
   * 「type → 中文名」的对照表，否则加一个构件又要在两个地方登记。
   */
  label?: string
  icon?: string
  /** 属性面板要暴露的材质字段名，例如 `["material", "frameMaterial"]`。 */
  materialFields?: string[]
  /**
   * 后端规划用的点名关键词（「用户提到百叶就要配额」）。
   * 引擎不读它，但它是同一份数据的一部分 —— 放在别处就又成第二份声明。
   */
  keywords?: string[]
  /**
   * 知识库分片名。KB 里若有该类型的专属分片（如 `chimney`）必须点它，
   * 否则检索落不到那一篇、静默退回代码兜底规则。省略时用通用 `component` 分片。
   */
  entityType?: string
  /** 位置/运行语义的自然语言说明，进后端提示词；引擎不读。 */
  notes?: string
  /**
   * 从构件面板拖进场景时的初始字段值。
   * 没在这里写、但 `params` 里带 `default` 的字段会自动补齐 ——
   * 所以「新构件放下来」这件事不需要再改前端那份 `createDefaultComponent` 大 switch。
   */
  defaults?: Record<string, RecipeValue>
  /**
   * 拖拽与属性面板的元数据。省略时由 `host` 推导：
   * `wall` → `wallFrom` + `parentWall`（必填）；`roof` → `position` + `parentRoof`；
   * 其余 → `position` 无宿主。路径类构件（栏杆、坡道）必须显式写 `path` / `fromTo`。
   */
  editing?: {
    translation: 'wallFrom' | 'fromTo' | 'path' | 'position' | 'lightBody'
    host?: 'parentWall' | 'parentFloor' | 'parentRoof'
    hostRequired?: boolean
  }
  /** 参数表：属性面板与校验共用，不要在别处再抄一份。 */
  params?: Record<string, RecipeParam>
  /**
   * 除了 `type` / `id` / `position` 之外**必须**给出的字段。
   * 后端据此生成必填字段清单；不写就会退化成"可选"，模型可以合法地漏掉它。
   */
  required?: string[]
  guards?: RecipeGuard[]
  elements: RecipeElementNode[]
}

/** 解释器的输入：组件原始对象（字段即作用域变量）。 */
export type RecipeComponent = Record<string, unknown> & {
  type: string
  id: string
  position?: number[]
}

/** 解释器产物。 */
export interface RecipeCompileResult {
  elements: GeometryElement[]
}
