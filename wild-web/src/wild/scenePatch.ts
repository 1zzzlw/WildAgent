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
import type { ScenePatch, SceneOperation, RemoveElementOperation, RemoveComponentOperation } from '../types/scenePatch'
import type { PhysicsData } from 'wild-core/types'
import { deepClone } from '../utils/common'

export function createGeometryRemovalOperations(
  blueprint: Blueprint,
  selectedIds: readonly string[],
): Array<RemoveElementOperation | RemoveComponentOperation> {
  const elementIds = new Set(blueprint.geometry.elements.map(item => item.id))
  const componentIds = new Set(blueprint.geometry.components?.map(item => item.id))
  return [...new Set(selectedIds)].flatMap((id): Array<RemoveElementOperation | RemoveComponentOperation> => {
    if (elementIds.has(id)) return [{ op: 'remove_element', id }]
    if (componentIds.has(id)) return [{ op: 'remove_component', id }]
    return []
  })
}

/** 删除宿主及依附构件，并清理随之失效的排布、物理约束和编辑分组。 */
function removeGeometry(blueprint: Blueprint, id: string) {
  const idsToRemove = new Set([id])
  const items = [...blueprint.geometry.elements, ...(blueprint.geometry.components || [])]
  let foundNew = true
  while (foundNew) {
    foundNew = false
    for (const item of items) {
      if (idsToRemove.has(item.id)) continue
      const record = item as unknown as Record<string, unknown>
      const attachment = record.attachment as { parent?: string } | undefined
      const parents = [record.parentWall, record.parentFloor, record.parentRoof, attachment?.parent]
      if (parents.some(parent => typeof parent === 'string' && idsToRemove.has(parent))) {
        idsToRemove.add(item.id)
        foundNew = true
      }
    }
  }
  blueprint.geometry.elements = blueprint.geometry.elements.filter(item => !idsToRemove.has(item.id))
  if (blueprint.geometry.components) {
    blueprint.geometry.components = blueprint.geometry.components.filter(item => !idsToRemove.has(item.id))
  }
  if (blueprint.geometry.placements) {
    blueprint.geometry.placements = blueprint.geometry.placements.filter(placement => {
      const parent = (placement.onSurface as { parent?: string } | undefined)?.parent
      if (parent && idsToRemove.has(parent)) {
        idsToRemove.add(placement.id)
        return false
      }
      return true
    })
  }
  const physics = blueprint.behaviors?.physics as PhysicsData | undefined
  if (physics?.constraints) {
    physics.constraints = physics.constraints.filter(constraint => !idsToRemove.has(constraint.target))
  }
  for (const group of Object.values(blueprint.editor?.groups || {})) {
    group.elements = group.elements.filter(elementId => !idsToRemove.has(elementId))
  }
}

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

    case 'remove_element':
      removeGeometry(blueprint, op.id)
      break

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
      removeGeometry(blueprint, op.id)
      break

    case 'upsert_material':
      if (!blueprint.materials) {
        blueprint.materials = {}
      }
      blueprint.materials[op.name] = op.material
      break

    case 'tune_material': {
      const materialField = op.material_field || 'material'
      const element = blueprint.geometry.elements.find(item => item.id === op.id)
      const component = blueprint.geometry.components?.find(item => item.id === op.id)
      const target = (element || component) as unknown as Record<string, unknown> | undefined
      const sourceName = target?.[materialField]
      const source = typeof sourceName === 'string' ? blueprint.materials?.[sourceName] : undefined
      if (target && source && !blueprint.materials?.[op.new_name]) {
        if (!blueprint.materials) blueprint.materials = {}
        blueprint.materials[op.new_name] = { ...source, ...op.changes }
        target[materialField] = op.new_name
      }
      break
    }

    case 'upsert_asset':
      if (!blueprint.assets) {
        blueprint.assets = {}
      }
      blueprint.assets[op.asset_id] = op.asset
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
