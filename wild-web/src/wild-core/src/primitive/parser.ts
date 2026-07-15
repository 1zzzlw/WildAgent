/**
 * 蓝图解析器
 * 
 * 将 JSON 字符串解析为 Blueprint AST。
 * 校验 meta.version 字段，确保蓝图使用引擎支持的语言版本。
 */

import type { Blueprint } from './types';

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

  const [major, minor] = version.split('.').map(Number);
  if (major > 1 || (major === 1 && minor > 0)) {
    throw new Error(`Unsupported blueprint version: ${version}. Engine supports up to 1.0`);
  }

  return obj as Blueprint;
}