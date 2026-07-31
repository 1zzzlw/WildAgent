/**
 * 蓝图解析器
 * 
 * 将 JSON 字符串解析为 Blueprint AST。
 * 校验 meta.version 字段，确保蓝图使用引擎支持的语言版本。
 */

import type { Blueprint } from './types';
import { validateBlueprintSchema } from './schema-validator';

export function parseBlueprint(json: string): Blueprint {
  let obj: any;
  try {
    obj = JSON.parse(json);
  } catch (e) {
    throw new Error('Invalid blueprint: JSON parse error');
  }

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
