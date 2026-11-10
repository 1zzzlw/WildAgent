import type { ComponentSpec, GeometryElement } from '../../../types'
import type { ComponentCompileContext } from '../types'
import { registerComponentCompiler } from '../componentRegistry'
import { attachPointsToRoof } from '../components/attachedToSurface'
import { createWallCoordinateFrame } from '../components/attachedToWall'
import { ComponentCompileError } from '../types'
import { compileRecipe } from './interpreter'
import type { ComponentRecipe, RecipeComponent } from './types'

/**
 * 配方注册表。
 *
 * 这里只做三件事：存配方、把配方接到 `componentRegistry` 的同一个 Map 上、
 * 提供**宿主求解**闭集。解释逻辑全在 `interpreter.ts`，两者不混。
 *
 * 加一个构件 = 放一份 JSON 进 `recipes/` + 在 `recipes/index.ts` 的 import 列表
 * 加一行。**不需要改 `componentRegistry`、`types.ts`、schema、属性面板、
 * 构件面板** —— 这正是这套东西存在的理由。
 */

/** 宿主求解：把「父引用 + 局部坐标」换成世界坐标。闭集，不开放扩展。 */
type RecipeHostResolver = (
  component: RecipeComponent,
  context: ComponentCompileContext,
) => RecipeComponent

const HOST_RESOLVERS: Record<string, RecipeHostResolver> = {
  /** 坐标已是世界坐标。 */
  position: component => component,
  /** 无宿主，所有坐标都是绝对世界坐标。 */
  none: component => component,
  /** `position` 相对屋面：给了 `parentRoof` 才求解，否则按绝对坐标。 */
  roof: (component, context) => {
    const parentRoof = component.parentRoof;
    if (typeof parentRoof !== 'string' || !Array.isArray(component.position)) return component;
    const resolved = attachPointsToRoof(
      parentRoof,
      [component.position as [number, number, number]],
      context,
    )[0];
    return { ...component, position: resolved };
  },
  /**
   * 挂墙配方以 `from=[沿墙距离, 世界标高, 法向偏移]` 存储。
   * 除世界锚点外同时暴露墙帧，配方可用 `hostRotationY / hostDirection /
   * hostNormal` 让自身细节跟随任意朝向的直墙或曲墙切线。
   */
  wall: (component, context) => {
    const parentWall = component.parentWall
    const from = component.from
    if (typeof parentWall !== 'string' || !parentWall) {
      throw new ComponentCompileError('挂墙配方缺少 parentWall', 'parentWall')
    }
    if (!Array.isArray(from) || from.length !== 3 || !from.every(Number.isFinite)) {
      throw new ComponentCompileError('挂墙配方的 from 必须是 [沿墙距离, 世界标高, 法向偏移]', 'from')
    }
    const local = from as [number, number, number]
    const wall = context.elements.find(element => element.id === parentWall)
    if (!wall) throw new ComponentCompileError(`parentWall "${parentWall}" 不存在`, 'parentWall')
    if (wall.type !== 'wall') throw new ComponentCompileError(`parentWall "${parentWall}" 不是 wall`, 'parentWall')
    const frame = createWallCoordinateFrame(wall, local[0])
    if (local[0] < 0 || local[0] > frame.length + 1e-6) {
      throw new ComponentCompileError(`from[0] 超出父墙长度 ${frame.length}`, 'from')
    }
    return {
      ...component,
      position: frame.pointAt(local[0], local[1], local[2]),
      hostRotationY: frame.rotationAt(local[0]),
      hostDirection: frame.directionAt(local[0]),
      hostNormal: frame.normalAt(local[0]),
    }
  },
}

const recipes = new Map<string, ComponentRecipe>()

export function getRecipe(type: string): ComponentRecipe | undefined {
  return recipes.get(type)
}

export function getRecipeTypes(): string[] {
  return [...recipes.keys()].sort();
}

/**
 * 拖入场景时的初始字段：`params` 的 `default` 打底，`recipe.defaults` 覆盖。
 *
 * 合并逻辑放在引擎侧而不是前端，是为了让「新构件放下来」也变成纯数据 ——
 * 否则前端那份 `createDefaultComponent` 大 switch 又会长出一条分支。
 */
export function getRecipeDefaults(type: string): Record<string, unknown> | undefined {
  const recipe = recipes.get(type);
  if (!recipe) return undefined;
  const defaults: Record<string, unknown> = {};
  for (const [key, param] of Object.entries(recipe.params || {})) {
    if (param.default !== undefined) defaults[key] = param.default;
  }
  Object.assign(defaults, recipe.defaults || {});
  return JSON.parse(JSON.stringify(defaults)) as Record<string, unknown>;
}

/** 只读快照，供前端构件面板列出可用的数据化构件。 */
export function getRecipeCapabilities(): Array<{
  type: string
  label: string
  icon: string
  description: string
  host: string
  materialFields: string[]
  params: ComponentRecipe['params']
}> {
  return [...recipes.values()]
    .map(recipe => ({
      type: recipe.type,
      label: recipe.label || recipe.type,
      icon: recipe.icon || '◇',
      description: recipe.description,
      host: recipe.host,
      materialFields: [...(recipe.materialFields || [])],
      params: recipe.params,
    }))
    .sort((left, right) => left.label.localeCompare(right.label))
}

function compileWithRecipe(
  recipe: ComponentRecipe,
  component: ComponentSpec,
  context: ComponentCompileContext,
): GeometryElement[] {
  const resolver = HOST_RESOLVERS[recipe.host]
  if (!resolver) {
    throw new Error(`配方 ${recipe.type} 声明了未知宿主种类 ${recipe.host}`);
  }
  const prepared = resolver({
    ...getRecipeDefaults(recipe.type),
    ...(component as unknown as RecipeComponent),
  } as RecipeComponent, context)
  return compileRecipe(recipe, prepared)
}

/**
 * 把一批配方接到构件注册表上。
 *
 * 必须在 `componentRegistry` 的 `compilers` Map 初始化之后调用（由
 * `registerBuiltins()` 末尾触发）——模块顶层自动注册会踩到 `const` 的 TDZ。
 */
/** 由 `host` 推导拖拽元数据；配方可用 `editing` 显式覆盖。 */
function deriveEditing(recipe: ComponentRecipe): NonNullable<ComponentRecipe['editing']> {
  if (recipe.editing) return recipe.editing
  if (recipe.host === 'wall') {
    return { translation: 'wallFrom', host: 'parentWall', hostRequired: true }
  }
  if (recipe.host === 'roof') return { translation: 'position', host: 'parentRoof' }
  return { translation: 'position' }
}

export function registerRecipeCompilers(list: readonly ComponentRecipe[]): void {
  for (const recipe of list) {
    if (recipes.has(recipe.type)) {
      throw new Error(`构件配方重复: ${recipe.type}`)
    }
    recipes.set(recipe.type, recipe)
    const editing = deriveEditing(recipe)
    registerComponentCompiler({
      type: recipe.type as ComponentSpec['type'],
      description: recipe.description,
      editing: {
        ...editing,
        // 参数表就是属性面板的字段清单，不另立一份。
        parameters: Object.keys(recipe.params || {}),
      },
      compile: (component, context) => compileWithRecipe(recipe, component, context),
    })
  }
}
