/**
 * 蓝图解析器
 * 
 * 将 JSON 字符串解析为 Blueprint AST。
 * 校验 meta.version 字段，确保蓝图使用引擎支持的语言版本。
 */

import type { Blueprint } from './types';
import { validateBlueprintSchema } from './schema-validator';
import { migrateBlueprintToLatest } from './migrations';
export { migrateBlueprintToLatest } from './migrations';

export function parseBlueprint(json: string): Blueprint {
  let obj: any;
  try {
    obj = JSON.parse(json);
  } catch (e) {
    throw new Error('Invalid blueprint: JSON parse error');
  }

  obj = normalizeBlueprintInput(obj);

  if (!obj.meta) throw new Error('Invalid blueprint: missing meta');
  if (!obj.geometry) throw new Error('Invalid blueprint: missing geometry');

  const version = obj.meta.version;
  if (!version) throw new Error('Invalid blueprint: missing meta.version');

  const versionParts = String(version).split('.');
  const major = Number(versionParts[0]);
  const minor = Number(versionParts[1]);
  if (!Number.isInteger(major) || !Number.isInteger(minor)) {
    throw new Error(`Invalid blueprint version: ${version}`);
  }
  if (major > 1 || (major === 1 && minor > 1)) {
    throw new Error(`Unsupported blueprint version: ${version}. Engine supports up to 1.1`);
  }

  if (obj.geometry.elements !== undefined && !Array.isArray(obj.geometry.elements)) {
    throw new Error('Invalid blueprint: geometry.elements must be an array');
  }

  const schemaErrors = validateBlueprintSchema(obj);
  if (schemaErrors.length > 0) {
    const summary = schemaErrors.slice(0, 5).join('; ');
    const remaining = schemaErrors.length > 5 ? `; 另有 ${schemaErrors.length - 5} 个错误` : '';
    throw new Error(`Invalid blueprint: schema validation failed: ${summary}${remaining}`);
  }

  return obj as Blueprint;
}

/** 将模型常见简写转换为标准 WILD 1.1 字段，不修改输入对象。 */
export function normalizeBlueprintInput(value: any): any {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;

  const elements = Array.isArray(value.geometry?.elements)
    ? value.geometry.elements.map(normalizeElement)
    : value.geometry?.elements;
  const components = Array.isArray(value.geometry?.components)
    ? value.geometry.components.map(normalizeComponent)
    : value.geometry?.components;
  const materials = value.materials && typeof value.materials === 'object'
    ? Object.fromEntries(
        Object.entries(value.materials).map(([name, material]) => [
          name,
          normalizeMaterial(material),
        ]),
      )
    : value.materials;

  // 修正 wall-attached 构件的 from[1]：
  // 模型有时误把 from[1] 写成相对父墙底部的局部偏移，而系统约定是世界坐标。
  // 当 from[1] < 父墙底部 Y 时，推断为局部坐标并自动加上 wallBottom。
  const normalizedComponents = Array.isArray(components)
    ? fixComponentFromY(components, Array.isArray(elements) ? elements : [])
    : components;

  const normalized = {
    ...value,
    geometry: value.geometry && typeof value.geometry === 'object'
      ? { ...value.geometry, elements, components: normalizedComponents }
      : value.geometry,
    materials,
  };
  return migrateBlueprintToLatest(normalized).blueprint;
}

/** 规范化 geometry.components 中的单个构件（如 light 的颜色格式）。 */
function normalizeComponent(component: any): any {
  if (!component || typeof component !== 'object' || Array.isArray(component)) {
    return component;
  }

  // 将 light 的 color 字段从 hex 字符串统一转换为 [R, G, B] 数组
  if (component.type === 'light' && typeof component.color === 'string') {
    const parsed = parseHexColor(component.color);
    if (parsed) {
      return { ...component, color: parsed };
    }
  }

  return { ...component };
}

/**
 * 修正 wall-attached 构件的 from[1] 坐标。
 *
 * 系统约定 from[1] 是世界坐标 Y，但模型常误用相对父墙底部的局部偏移。
 * 当 from[1] 明显小于父墙底部 Y（超过 0.5m）时，推断为局部坐标并加上 wallBottom。
 */
function fixComponentFromY(components: any[], elements: any[]): any[] {
  // 建立 wallId -> wallBottom 映射
  const wallBottomMap = new Map<string, number>();
  for (const el of elements) {
    if (el?.type === 'wall' && el.id && Array.isArray(el.from) && Array.isArray(el.to)) {
      const bottom = Math.min(el.from[1], el.to[1]);
      if (Number.isFinite(bottom)) wallBottomMap.set(el.id, bottom);
    }
  }

  return components.map((component: any) => {
    if (
      !component
      || typeof component !== 'object'
      || !['door', 'window', 'canopy', 'balcony', 'bay_window'].includes(component.type)
      || typeof component.parentWall !== 'string'
      || !Array.isArray(component.from)
      || component.from.length !== 3
    ) {
      return component;
    }
    const wallBottom = wallBottomMap.get(component.parentWall);
    if (wallBottom === undefined || wallBottom < 1e-6) return component; // 一楼墙无需修正

    const fromY = component.from[1];
    // from[1] 明显小于 wallBottom，判定为局部偏移，补正为世界坐标
    if (Number.isFinite(fromY) && fromY < wallBottom - 0.5) {
      const corrected = [...component.from];
      corrected[1] = wallBottom + fromY;
      return { ...component, from: corrected };
    }
    return component;
  });
}

function normalizeElement(element: any): any {
  if (!element || typeof element !== 'object' || Array.isArray(element)) {
    return element;
  }

  if (element.type === 'wall' && Number.isFinite(element.height) && element.height > 0) {
    const from = Array.isArray(element.from) ? [...element.from] : element.from;
    const to = Array.isArray(element.to) ? [...element.to] : element.to;
    if (
      Array.isArray(from)
      && Array.isArray(to)
      && from.length === 3
      && to.length === 3
      && Math.abs(to[1] - from[1]) < 1e-6
    ) {
      to[1] = from[1] + element.height;
    }
    const normalized = { ...element, from, to };
    delete normalized.height;
    return normalized;
  }

  if (element.type === 'opening' && (element.style === 'door' || element.style === 'window')) {
    const role = element.style;
    const from = Array.isArray(element.from) ? [...element.from] : element.from;
    if (role === 'window' && Array.isArray(from) && from[1] <= 0.1) from[1] = 0.9;
    return {
      ...element,
      from,
      style: 'rectangular',
      height: element.height <= 0.1 ? (role === 'door' ? 2.1 : 1.2) : element.height,
    };
  }

  if (element.type === 'opening' && (element.style === 'double' || element.style === 'lattice')) {
    // 旧样例曾把门扇/窗格外观写入 opening.style；几何轮廓都可无歧义地
    // 收敛为矩形，具体门窗细节现在由 geometry.components 表达。
    return { ...element, style: 'rectangular' };
  }

  if (element.type === 'column' && element.style === 'round') {
    return { ...element, style: 'modern' };
  }

  if (element.type === 'roof') {
    // 兼容模型常用的建筑术语，统一转换为 WILD 1.1 标准枚举值
    const roofType = element.roofType;
    if (roofType === 'pitched' || roofType === 'sloped' || roofType === 'gabled') {
      // pitched/sloped 是通用坡屋顶术语，默认映射为双坡（gable）
      return { ...element, roofType: 'gable' };
    }
    if (roofType === 'hipped') {
      return { ...element, roofType: 'hip' };
    }
    if (roofType === 'shed' || roofType === 'mono-pitch') {
      // 单坡屋顶在当前引擎中用 gable + 适当参数模拟
      return { ...element, roofType: 'gable' };
    }
  }

  if (element.type === 'primitive' && element.shape === 'box') {
    const dimensions = element.dimensions;
    if (dimensions && typeof dimensions === 'object' && !Array.isArray(dimensions)) {
      const orderedDimensions = [
        dimensions.width,
        dimensions.height,
        dimensions.depth,
      ];
      // furniture 的 dimensions 是对象，primitive.box 则要求三元素数组。
      // 只兼容能够无歧义转换的对象；不完整对象仍由 Schema/构建器明确报错。
      if (orderedDimensions.every(isPositiveFiniteNumber)) {
        return { ...element, dimensions: orderedDimensions };
      }
    }
  }

  return { ...element };
}

function normalizeMaterial(value: any): any {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  const baseColor = isColor(value.baseColor)
    ? [...value.baseColor]
    : parseHexColor(value.color);
  if (!baseColor) return { ...value };

  const normalized = {
    ...value,
    baseColor,
    roughness: validUnit(value.roughness) ? value.roughness : 0.8,
    metallic: validUnit(value.metallic) ? value.metallic : 0,
    albedo: validUnit(value.albedo) ? value.albedo : 1,
    lightingCondition: 'D65_noon',
  };
  delete normalized.color;
  return normalized;
}

function parseHexColor(value: unknown): [number, number, number] | undefined {
  if (typeof value !== 'string' || !/^#[0-9a-f]{6}$/i.test(value)) return undefined;
  return [
    Number.parseInt(value.slice(1, 3), 16) / 255,
    Number.parseInt(value.slice(3, 5), 16) / 255,
    Number.parseInt(value.slice(5, 7), 16) / 255,
  ];
}

function isColor(value: unknown): value is [number, number, number] {
  return Array.isArray(value) && value.length === 3 && value.every(validUnit);
}

function validUnit(value: unknown): value is number {
  return typeof value === 'number'
    && Number.isFinite(value)
    && value >= 0
    && value <= 1;
}

function isPositiveFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}
