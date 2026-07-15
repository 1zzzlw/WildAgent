/**
 * ScenePatch 协议定义
 * 
 * ScenePatch 是所有场景修改的统一格式，无论来自：
 * - 用户手动编辑（属性面板、拖拽）
 * - Agent AI 建议
 * - 系统自动操作
 * 
 * 核心操作类型：
 * - add_element / update_element / remove_element: 构件操作
 * - upsert_material: 材质操作
 * - add_template / add_instance / add_placement: 模板和批量操作
 * 
 * Patch 包含 revision 机制，类似 Git 的版本控制，防止冲突。
 */

import type { GeometryElement, MaterialDef, InstanceRef, Placement } from './blueprint'

export interface ScenePatch {
  type: 'scene_patch'
  patch_id: string
  base_revision: number
  source: 'user' | 'agent' | 'system'
  mode: 'apply' | 'proposal'
  requires_confirmation: boolean
  operations: SceneOperation[]
  summary?: string
}

export type SceneOperation =
  | AddElementOperation
  | UpdateElementOperation
  | RemoveElementOperation
  | UpsertMaterialOperation
  | AddTemplateOperation
  | UpdateTemplateOperation
  | RemoveTemplateOperation
  | AddInstanceOperation
  | AddPlacementOperation
  | SetBehaviorsOperation
  | SetEditorMetaOperation

export interface AddElementOperation {
  op: 'add_element'
  element: GeometryElement
}

export interface UpdateElementOperation {
  op: 'update_element'
  id: string
  changes: Record<string, unknown>
}

export interface RemoveElementOperation {
  op: 'remove_element'
  id: string
}

export interface UpsertMaterialOperation {
  op: 'upsert_material'
  name: string
  material: MaterialDef
}

export interface AddTemplateOperation {
  op: 'add_template'
  name: string
  template: GeometryElement
}

export interface UpdateTemplateOperation {
  op: 'update_template'
  name: string
  changes: Record<string, unknown>
}

export interface RemoveTemplateOperation {
  op: 'remove_template'
  name: string
}

export interface AddInstanceOperation {
  op: 'add_instance'
  instance: InstanceRef
}

export interface AddPlacementOperation {
  op: 'add_placement'
  placement: Placement
}

export interface SetBehaviorsOperation {
  op: 'set_behaviors'
  changes: Record<string, unknown>
}

export interface SetEditorMetaOperation {
  op: 'set_editor_meta'
  changes: Record<string, unknown>
}

export interface ValidationIssue {
  level: 'error' | 'warning'
  message: string
  path?: string
  elementId?: string
}
