import type { GeometryElement } from '../../../types'
import { ComponentCompileError } from '../types'
import { evaluateExpression, type ExpressionScope } from './evaluator'
import type {
  ComponentRecipe,
  RecipeComponent,
  RecipeElementNode,
  RecipeRepeat,
  RecipeValue,
} from './types'

/** 模板里由解释器消费、不进入 element 的键。 */
const RESERVED_KEYS = new Set(['repeat', 'behavior'])
const ALLOWED_BEHAVIOR_KINDS = new Set(['opening', 'light', 'elevator', 'rotor'])

function isExpression(value: unknown): value is { $: string } {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const keys = Object.keys(value as Record<string, unknown>);
  return keys.length === 1 && keys[0] === '$' && typeof (value as { $: unknown }).$ === 'string';
}

/**
 * 把配方里的值还原成实际值。
 *
 * `undefined` 会一路透传并在装配阶段被**跳过**（不写进 element）——
 * 这是刻意的：`createBox` 在 `material` 为空时不写该键，配方必须能复现
 * 同样的键集合，否则黄金基线的逐字段比对会红。
 */
export function resolveValue(value: RecipeValue | undefined, scope: ExpressionScope): unknown {
  if (value === undefined) return undefined;
  if (isExpression(value)) return evaluateExpression(value.$, scope);
  if (Array.isArray(value)) {
    return value.map(item => resolveValue(item as RecipeValue, scope));
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, RecipeValue>)) {
      const resolved = resolveValue(item, scope);
      if (resolved !== undefined) out[key] = resolved;
    }
    return out;
  }
  return value;
}

/** id 模板：`{expr}` 段求值，其余原样保留。 */
function resolveIdTemplate(template: string, scope: ExpressionScope): string {
  return template.replace(/\{([^{}]+)\}/g, (_match, expression: string) => {
    const value = evaluateExpression(expression.trim(), scope);
    if (value === undefined || value === null) {
      throw new ComponentCompileError(`id 模板段 {${expression}} 求值为空`);
    }
    return String(value);
  });
}

interface RepeatContext {
  i: number;
  n: number;
  t: number;
  angle?: number;
  /** linear：累计位移。 */
  offset?: [number, number, number];
}

function expandRepeat(repeat: RecipeRepeat, scope: ExpressionScope): RepeatContext[] {
  const rawCount = evaluateExpression(repeat.count, scope);
  const count = Math.round(Number(rawCount));
  if (!Number.isFinite(count) || count <= 0) {
    throw new ComponentCompileError(`repeat.count 必须是正整数，得到 ${String(rawCount)}`);
  }
  if (count > 512) {
    throw new ComponentCompileError(`repeat.count 超过单构件副本上限 512（得到 ${count}）`);
  }
  const context: RepeatContext[] = [];
  for (let i = 0; i < count; i += 1) {
    const t = count === 1 ? 0 : i / (count - 1);
    if (repeat.kind === 'polar') {
      const startAngle = repeat.startAngle ? Number(evaluateExpression(repeat.startAngle, scope)) : 0;
      context.push({ i, n: count, t, angle: startAngle + (i * Math.PI * 2) / count });
      continue;
    }
    if (repeat.kind === 'stack') {
      const stepY = repeat.stepY ? Number(evaluateExpression(repeat.stepY, scope)) : 0;
      context.push({ i, n: count, t, offset: [0, i * stepY, 0] });
      continue;
    }
    const step = (repeat.step || ['0', '0', '0']).map(item => Number(evaluateExpression(item, scope)));
    context.push({ i, n: count, t, offset: [i * step[0], i * step[1], i * step[2]] });
  }
  return context;
}

function buildElement(
  node: RecipeElementNode,
  scope: ExpressionScope,
  repeatContext?: RepeatContext,
): GeometryElement {
  const id = resolveIdTemplate(node.id, scope);
  const element: Record<string, unknown> = { id };
  for (const [key, value] of Object.entries(node)) {
    if (key === 'id' || key === 'type' || RESERVED_KEYS.has(key)) continue;
    const resolved = resolveValue(value as RecipeValue, scope);
    if (resolved === undefined) continue;
    if (repeatContext?.offset && (key === 'position') && Array.isArray(resolved)) {
      element[key] = [
        (resolved[0] as number) + repeatContext.offset[0],
        (resolved[1] as number) + repeatContext.offset[1],
        (resolved[2] as number) + repeatContext.offset[2],
      ];
      continue;
    }
    element[key] = resolved;
  }
  element.type = node.type;
  if (node.behavior) {
    const behavior = resolveValue(node.behavior, scope);
    if (behavior !== undefined) {
      const kind = behavior && typeof behavior === 'object'
        ? (behavior as { kind?: unknown }).kind
        : undefined
      if (typeof kind !== 'string' || !ALLOWED_BEHAVIOR_KINDS.has(kind)) {
        throw new ComponentCompileError(`配方行为 kind 不受支持: ${String(kind)}`)
      }
      element._interaction = behavior;
    }
  }
  return element as unknown as GeometryElement;
}

/**
 * 按配方把组件展开为元素。
 *
 * 纯函数：不读全局状态、不改 `component`、不依赖编译顺序。
 */
export function compileRecipe(
  recipe: ComponentRecipe,
  component: RecipeComponent,
): GeometryElement[] {
  if (!component.id || typeof component.id !== 'string') {
    throw new ComponentCompileError('组件缺少非空 id', 'id');
  }

  validateRecipeComponent(recipe, component)

  const scope: ExpressionScope = {
    ...component,
    id: component.id,
    // `pos` 是位置的分量视图：数组没有 `.x`，配方里大量使用 `pos.x / pos.y / pos.z`。
    // 数组形态仍可通过 `position` 拿到。
    pos: Array.isArray(component.position)
      ? { x: component.position[0], y: component.position[1], z: component.position[2] }
      : undefined,
  };

  for (const guard of recipe.guards || []) {
    if (!evaluateExpression(guard.expr, scope)) {
      throw new ComponentCompileError(guard.message, guard.field);
    }
  }

  const elements: GeometryElement[] = [];
  for (const node of recipe.elements) {
    if (!node.repeat) {
      elements.push(buildElement(node, scope));
      continue;
    }
    const contexts = expandRepeat(node.repeat, scope);
    for (const repeatContext of contexts) {
      const localScope: ExpressionScope = { ...scope, ...repeatContext };
      elements.push(buildElement(node, localScope, repeatContext));
    }
  }

  const seen = new Set<string>();
  for (const element of elements) {
    if (seen.has(element.id)) {
      throw new ComponentCompileError(`配方生成了重复的元素 id: ${element.id}`);
    }
    seen.add(element.id);
  }
  return elements;
}

function validateRecipeComponent(recipe: ComponentRecipe, component: RecipeComponent): void {
  for (const field of recipe.required || []) {
    if (component[field] === undefined || component[field] === null) {
      throw new ComponentCompileError(`组件缺少必填字段 ${field}`, field)
    }
  }
  for (const [field, spec] of Object.entries(recipe.params || {})) {
    const value = component[field]
    if (value === undefined || value === null) continue
    if (spec.type === 'vec3') {
      if (!Array.isArray(value) || value.length !== 3 || !value.every(Number.isFinite)) {
        throw new ComponentCompileError(`${field} 必须是三个有限数字`, field)
      }
      continue
    }
    if (spec.type === 'string') {
      if (typeof value !== 'string') throw new ComponentCompileError(`${field} 必须是字符串`, field)
      continue
    }
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new ComponentCompileError(`${field} 必须是有限数字`, field)
    }
    if (spec.type === 'integer' && !Number.isInteger(value)) {
      throw new ComponentCompileError(`${field} 必须是整数`, field)
    }
    if (spec.min !== undefined && value < spec.min) {
      throw new ComponentCompileError(`${field} 不能小于 ${spec.min}`, field)
    }
    if (spec.max !== undefined && value > spec.max) {
      throw new ComponentCompileError(`${field} 不能大于 ${spec.max}`, field)
    }
  }
}
