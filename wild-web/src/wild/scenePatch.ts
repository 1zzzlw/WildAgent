/**
 * ScenePatch 应用逻辑
 * 
 * 实现 ScenePatch 到 Blueprint 的应用：
 * - applyPatchToBlueprint(): 将 patch 应用到 Blueprint 副本
 * - applyOperation(): 应用单个操作（内部函数）
 * - createPatch(): 创建 ScenePatch 对象的辅助函数
 * 
 * 支持的操作类型：
 * - add_element / update_element / remove_element
 * - upsert_material
 * - add_template / update_template / remove_template
 * - add_instance / add_placement
 * - set_behaviors / set_editor_meta
 * 
 * 这是 ScenePatch 协议的核心实现，确保所有修改都正确应用到 Blueprint。
 */

import type { Blueprint } from '../types/blueprint'
import type { ScenePatch, SceneOperation } from '../types/scenePatch'
import { deepClone } from '../utils/common'

export function applyPatchToBlueprint(blueprint: Blueprint, patch: ScenePatch): Blueprint {
  const newBlueprint = deepClone(blueprint)

  for (const op of patch.operations) {
    applyOperation(newBlueprint, op)
  }

  return newBlueprint
}

function applyOperation(blueprint: Blueprint, op: SceneOperation) {
  switch (op.op) {
    case 'add_element':
      blueprint.geometry.elements.push(op.element)
      break

    case 'update_element': {
      const element = blueprint.geometry.elements.find(e => e.id === op.id)
      if (element) {
        Object.assign(element, op.changes)
      }
      break
    }

    case 'remove_element': {
      // 级联删除：收集所有引用目标元素的子节点（opening.parentWall、组件 parentWall、
      // 全局物理约束 target），一并删除，避免悬空引用导致校验失败。
      const idsToRemove = new Set<string>([op.id])
      let foundNew = true
      while (foundNew) {
        foundNew = false
        for (const el of blueprint.geometry.elements) {
          if (idsToRemove.has(el.id)) continue
          const parentWall = (el as unknown as Record<string, unknown>).parentWall as string | undefined
          if (parentWall && idsToRemove.has(parentWall)) {
            idsToRemove.add(el.id)
            foundNew = true
          }
        }
        for (const comp of blueprint.geometry.components || []) {
          if (idsToRemove.has(comp.id)) continue
          const parentWall = (comp as unknown as Record<string, unknown>).parentWall as string | undefined
          if (parentWall && idsToRemove.has(parentWall)) {
            idsToRemove.add(comp.id)
            foundNew = true
          }
        }
      }
      blueprint.geometry.elements = blueprint.geometry.elements.filter(
        e => !idsToRemove.has(e.id)
      )
      if (blueprint.geometry.components) {
        blueprint.geometry.components = blueprint.geometry.components.filter(
          c => !idsToRemove.has(c.id)
        )
      }
      break
    }

    case 'add_component':
      if (!blueprint.geometry.components) {
        blueprint.geometry.components = []
      }
      blueprint.geometry.components.push(op.component)
      break

    case 'update_component': {
      const component = blueprint.geometry.components?.find(item => item.id === op.id)
      if (component) {
        for (const [key, value] of Object.entries(op.changes)) {
          if (value === undefined) {
            delete (component as unknown as Record<string, unknown>)[key]
          } else {
            (component as unknown as Record<string, unknown>)[key] = value
          }
        }
      }
      break
    }

    case 'remove_component':
      if (blueprint.geometry.components) {
        blueprint.geometry.components = blueprint.geometry.components.filter(
          component => component.id !== op.id
        )
      }
      break

    case 'upsert_material':
      if (!blueprint.materials) {
        blueprint.materials = {}
      }
      blueprint.materials[op.name] = op.material
      break

    case 'add_template':
      if (!blueprint.geometry.templates) {
        blueprint.geometry.templates = {}
      }
      blueprint.geometry.templates[op.name] = op.template
      break

    case 'update_template': {
      if (blueprint.geometry.templates && blueprint.geometry.templates[op.name]) {
        Object.assign(blueprint.geometry.templates[op.name], op.changes)
      }
      break
    }

    case 'remove_template':
      if (blueprint.geometry.templates) {
        delete blueprint.geometry.templates[op.name]
      }
      break

    case 'add_instance':
      if (!blueprint.geometry.instances) {
        blueprint.geometry.instances = []
      }
      blueprint.geometry.instances.push(op.instance)
      break

    case 'add_placement':
      if (!blueprint.geometry.placements) {
        blueprint.geometry.placements = []
      }
      blueprint.geometry.placements.push(op.placement)
      break

    case 'set_behaviors':
      if (!blueprint.behaviors) {
        blueprint.behaviors = {}
      }
      Object.assign(blueprint.behaviors, op.changes)
      break

    case 'set_editor_meta':
      if (!blueprint.editor) {
        blueprint.editor = {}
      }
      Object.assign(blueprint.editor, op.changes)
      break

    default:
      console.warn('未知操作类型', op)
  }
}

export function createPatch(
  baseRevision: number,
  operations: SceneOperation[],
  source: 'user' | 'agent' | 'system' = 'user',
  requiresConfirmation = false,
  summary?: string
): ScenePatch {
  return {
    type: 'scene_patch',
    patch_id: `patch_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    base_revision: baseRevision,
    source,
    mode: 'apply',
    requires_confirmation: requiresConfirmation,
    operations,
    summary
  }
}
