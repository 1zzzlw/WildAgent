/**
 * Blueprint 默认值定义
 * 
 * 提供 Blueprint 和各类构件的默认参数：
 * 
 * - createEmptyBlueprint(): 创建空白 Blueprint
 *   - 包含最小必需字段（meta, geometry, materials）
 *   - 用于"新建"功能
 * 
 * - getElementDefaults(): 获取构件类型的默认参数
 *   - wall: from, to, height, thickness
 *   - column: base, height, bottomRadius, topRadius
 *   - floor: region, thickness
 *   - beam: from, to, width, height
 *   - roof: roofType, span, depth, height
 *   - opening: parentWall, from, width, height
 *   - furniture: subtype, position, dimensions
 * 
 * 用于：
 * - 构件库添加构件时提供默认值
 * - Agent 生成构件时作为参考
 * - 确保新构件包含必需参数
 */

import type { Blueprint } from '../types/blueprint'

export function createEmptyBlueprint(name: string = '未命名建筑'): Blueprint {
  return {
    meta: {
      version: '1.0',
      type: 'building',
      name
    },
    geometry: {
      elements: []
    },
    materials: {},
    behaviors: {}
  }
}

export function getElementDefaults(type: string): Record<string, unknown> {
  const defaults: Record<string, Record<string, unknown>> = {
    wall: {
      from: [0, 0, 0],
      to: [4, 0, 0],
      height: 3,
      thickness: 0.24
    },
    column: {
      base: [0, 0, 0],
      height: 3,
      bottomRadius: 0.2,
      topRadius: 0.2,
      style: 'plain'
    },
    floor: {
      region: [[0, 0, 0], [4, 0, 0], [4, 0, 4], [0, 0, 4]],
      thickness: 0.2
    },
    beam: {
      from: [0, 3, 0],
      to: [4, 3, 0],
      width: 0.2,
      height: 0.3
    },
    roof: {
      roofType: 'gable',
      span: 8,
      depth: 6,
      height: 3,
      thickness: 0.1
    },
    opening: {
      parentWall: '',
      from: 0,
      width: 1.2,
      height: 2.4,
      style: 'door'
    },
    furniture: {
      subtype: 'table',
      position: [0, 0, 0],
      dimensions: [1, 0.8, 1]
    }
  }

  return defaults[type] || {}
}
