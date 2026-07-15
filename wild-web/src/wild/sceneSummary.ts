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

import type { Blueprint } from '../types/blueprint'
import type { SceneSummary } from '../types/scene'

export function generateSceneSummary(blueprint: Blueprint): SceneSummary {
  const elements = blueprint.geometry.elements || []
  
  // 统计元素类型
  const typeSet = new Set<string>()
  elements.forEach(e => typeSet.add(e.type))

  // 计算边界盒
  let minX = Infinity, minY = Infinity, minZ = Infinity
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity

  elements.forEach(element => {
    // 简单的边界计算，实际应该更复杂
    if (element.type === 'column') {
      const base = (element as any).base
      if (Array.isArray(base) && base.length === 3) {
        minX = Math.min(minX, base[0])
        minY = Math.min(minY, base[1])
        minZ = Math.min(minZ, base[2])
        maxX = Math.max(maxX, base[0])
        maxY = Math.max(maxY, base[1] + ((element as any).height || 0))
        maxZ = Math.max(maxZ, base[2])
      }
    }
  })

  const bbox = (minX !== Infinity && maxX !== -Infinity) ? {
    min: [minX, minY, minZ] as [number, number, number],
    max: [maxX, maxY, maxZ] as [number, number, number]
  } : undefined

  return {
    elements_count: elements.length,
    types: Array.from(typeSet),
    bbox,
    materials: Object.keys(blueprint.materials || {})
  }
}
