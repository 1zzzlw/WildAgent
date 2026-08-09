/**
 * 场景摘要生成
 * 
 * 生成场景的简要描述，用于：
 * - 发送给 Agent，帮助快速了解当前场景状态
 * - 避免发送完整 Blueprint（减少数据传输）
 * - 显示场景统计信息
 * 
 * SceneSummary 包含：
 * - elements_count: 构件总数
 * - types: 构件类型列表（['wall', 'column', ...]）
 * - bbox: 场景边界盒（min/max 坐标）
 * - materials: 材质列表
 * 
 * Agent 可以根据摘要判断：
 * - 场景是否为空
 * - 有哪些类型的构件
 * - 场景的大致范围
 * - 是否需要进一步查询详细信息
 */

import type { Blueprint, GeometryElement } from '../types/blueprint'
import type { SceneSummary } from '../types/scene'

function isVec3(v: unknown): v is number[] {
  return Array.isArray(v)
    && v.length >= 3
    && typeof v[0] === 'number'
    && typeof v[1] === 'number'
    && typeof v[2] === 'number'
    && Number.isFinite(v[0])
    && Number.isFinite(v[1])
    && Number.isFinite(v[2])
}

/** 向边界盒加入一个三维点（忽略非法值）。 */
function addPoint(
  point: number[],
  min: number[],
  max: number[],
) {
  if (!isVec3(point)) return
  for (let i = 0; i < 3; i++) {
    if (point[i] < min[i]) min[i] = point[i]
    if (point[i] > max[i]) max[i] = point[i]
  }
}

/**
 * 提取构件的锚点坐标（from/to/base/position/origin/center），
 * 并尽量把尺寸/高度信息展开成包围盒范围，而不是只统计柱。
 */
function elementBBox(element: GeometryElement, min: number[], max: number[]) {
  const e = element as Record<string, unknown>
  const anyAnchorKeys = ['from', 'to', 'base', 'position', 'origin', 'center'] as const
  for (const key of anyAnchorKeys) {
    const v = e[key]
    if (isVec3(v)) {
      addPoint(v, min, max)
    }
    // 曲线片段也提供端点信息（如墙体的 arc/ellipse 路径）
    if (key === 'from' && e.curve) {
      const curve = e.curve as { center?: number[] } | Array<{ center?: number[] }>
      const list = Array.isArray(curve) ? curve : [curve]
      for (const seg of list) {
        if (seg && isVec3(seg.center)) addPoint(seg.center, min, max)
      }
    }
  }

  // 底部 Y + 高度 → 顶面 Y
  const height = e.height
  if (typeof height === 'number' && Number.isFinite(height) && height > 0) {
    const baseY = (isVec3(e.base) && e.base[1]) || (isVec3(e.from) && e.from[1])
    if (typeof baseY === 'number' && Number.isFinite(baseY)) {
      addPoint([max[0], baseY + height, max[2]], min, max)
    }
  }

  // roof：position/span/depth/height 展开
  if (e.type === 'roof') {
    const pos = isVec3(e.position) ? e.position : [0, 0, 0]
    const span = typeof e.span === 'number' ? e.span : 0
    const depth = typeof e.depth === 'number' ? e.depth : 0
    const roofH = typeof e.height === 'number' ? e.height : 0
    if (span > 0 || depth > 0 || roofH > 0) {
      addPoint([pos[0] - span / 2, pos[1], pos[2] - depth / 2], min, max)
      addPoint([pos[0] + span / 2, pos[1] + roofH, pos[2] + depth / 2], min, max)
    }
  }

  // furniture / primitive.box：position + dimensions 展开
  const dimensions = e.dimensions
  if (dimensions && typeof dimensions === 'object') {
    const pos = isVec3(e.position) ? e.position : [0, 0, 0]
    const dims = Array.isArray(dimensions)
      ? dimensions
      : [
          (dimensions as Record<string, unknown>).width,
          (dimensions as Record<string, unknown>).height,
          (dimensions as Record<string, unknown>).depth,
        ]
    if (isVec3(dims)) {
      addPoint([pos[0], pos[1], pos[2]], min, max)
      addPoint([pos[0] + (dims[0] || 0), pos[1] + (dims[1] || 0), pos[2] + (dims[2] || 0)], min, max)
    }
  }
}

/** 组合构件的包围盒（from/to/position + 尺寸，path 逐点）。 */
function componentBBox(component: Record<string, unknown>, min: number[], max: number[]) {
  const anyAnchorKeys = ['from', 'to', 'position'] as const
  for (const key of anyAnchorKeys) {
    if (isVec3(component[key])) addPoint(component[key], min, max)
  }
  const path = component.path
  if (Array.isArray(path)) {
    for (const p of path) addPoint(p, min, max)
  }
  const width = component.width
  const height = component.height
  if (typeof width === 'number' || typeof height === 'number') {
    const anchor = isVec3(component.from) ? component.from : [0, 0, 0]
    addPoint([anchor[0] + (typeof width === 'number' ? width : 0), anchor[1] + (typeof height === 'number' ? height : 0), anchor[2]], min, max)
  }
  const depth = component.depth
  if (typeof depth === 'number' && isVec3(component.from)) {
    addPoint([component.from[0], component.from[1], component.from[2] + depth], min, max)
  }
}

export function generateSceneSummary(blueprint: Blueprint): SceneSummary {
  const elements = blueprint.geometry.elements || []
  const components = blueprint.geometry.components || []
  
  // 统计元素类型
  const typeSet = new Set<string>()
  elements.forEach(e => typeSet.add(e.type))
  components.forEach(component => typeSet.add(`component:${component.type}`))

  // 计算边界盒（遍历全部基础构件 + 组合构件）
  const min = [Infinity, Infinity, Infinity]
  const max = [-Infinity, -Infinity, -Infinity]

  elements.forEach(element => elementBBox(element, min, max))
  components.forEach(component => componentBBox(component as unknown as Record<string, unknown>, min, max))

  const bbox = (min[0] !== Infinity && max[0] !== -Infinity) ? {
    min: min as [number, number, number],
    max: max as [number, number, number]
  } : undefined

  return {
    elements_count: elements.length + components.length,
    types: Array.from(typeSet),
    bbox,
    materials: Object.keys(blueprint.materials || {})
  }
}
