/**
 * Blueprint 校验器
 * 
 * 校验 Blueprint 的合法性，包括：
 * - meta 字段完整性（version, type）
 * - 构件 id 唯一性
 * - 构件 type 存在性
 * - 材质引用有效性（构件引用的材质必须存在）
 * - 父元素存在性（opening.parentWall 必须存在）
 * 
 * 返回 ValidationIssue 列表：
 * - level: 'error' | 'warning'
 * - message: 问题描述
 * - elementId / path: 问题位置
 * 
 * 校验时机：
 * - applyPatch 之前
 * - 用户手动触发校验
 * - Agent 生成 Patch 之前
 */

import type { Blueprint } from '../types/blueprint'
import type { ValidationIssue } from '../types/scenePatch'

export function validateBlueprint(blueprint: Blueprint): ValidationIssue[] {
  const issues: ValidationIssue[] = []

  // 校验 meta
  if (!blueprint.meta?.version) {
    issues.push({ level: 'error', message: 'Blueprint 缺少 meta.version', path: 'meta.version' })
  }
  if (!blueprint.meta?.type) {
    issues.push({ level: 'error', message: 'Blueprint 缺少 meta.type', path: 'meta.type' })
  }

  // 校验 geometry
  if (!blueprint.geometry) {
    issues.push({ level: 'error', message: 'Blueprint 缺少 geometry', path: 'geometry' })
    return issues
  }

  // 检查元素 id 唯一性
  const elementIds = new Set<string>()
  for (const element of blueprint.geometry.elements || []) {
    if (!element.id) {
      issues.push({ level: 'error', message: '构件缺少 id', path: `geometry.elements` })
      continue
    }

    if (elementIds.has(element.id)) {
      issues.push({
        level: 'error',
        message: `构件 id 重复: ${element.id}`,
        elementId: element.id
      })
    }
    elementIds.add(element.id)

    // 校验构件类型
    if (!element.type) {
      issues.push({
        level: 'error',
        message: `构件 ${element.id} 缺少 type`,
        elementId: element.id
      })
    }
  }

  // 校验材质引用
  const materialNames = new Set(Object.keys(blueprint.materials || {}))
  for (const element of blueprint.geometry.elements || []) {
    const mat = (element as any).material
    if (mat && typeof mat === 'string' && !materialNames.has(mat)) {
      issues.push({
        level: 'warning',
        message: `构件 ${element.id} 引用了不存在的材质: ${mat}`,
        elementId: element.id
      })
    }
  }

  // 校验 opening.parentWall
  for (const element of blueprint.geometry.elements || []) {
    if (element.type === 'opening') {
      const parentWall = (element as any).parentWall
      if (parentWall && !elementIds.has(parentWall)) {
        issues.push({
          level: 'error',
          message: `opening ${element.id} 的 parentWall 不存在: ${parentWall}`,
          elementId: element.id
        })
      }
    }
  }

  return issues
}
