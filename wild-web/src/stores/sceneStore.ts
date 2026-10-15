/**
 * 场景状态管理 Store
 * 
 * 管理当前编辑的场景文档，包括：
 * - document: 场景文档（Blueprint + revision + dirty 状态）
 * - reconstructed: wild-core 重建后的几何数据
 * - validationIssues: Blueprint 校验问题列表
 * 
 * 核心方法：
 * - loadBlueprint(): 加载 Blueprint
 * - applyPatch(): 应用 ScenePatch（包含 revision 检查、校验、重建）
 * - reconstruct(): 调用 wild-core 重建场景
 * - validate(): 校验 Blueprint 合法性
 * - exportWild(): 导出 .wild 文件
 * 
 * 这是整个编辑器最核心的 Store，所有场景修改都通过这里。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SceneDocument, ReconstructedEntity } from '../types/scene'
import type { Blueprint } from '../types/blueprint'
import type { ScenePatch, ValidationIssue } from '../types/scenePatch'
import { applyPatchToBlueprint } from '../wild/scenePatch'
import { validateBlueprint } from '../wild/sceneValidator'
import { normalizeBlueprintInput } from 'wild-core/primitive'
import { deepClone } from '../utils/common'
import { useHistoryStore } from './historyStore'
import { reconstructScene } from '../renderer/reconstructionClient'
import { clearTextureLoadRecords } from '../renderer/textureLoadMonitor'

function compactSceneName(name: string): string {
  const firstClause = String(name).trim().replace(/\s+/g, ' ').split(/[：:，,；;。]/, 1)[0]?.trim() || '未命名建筑'
  return [...firstClause].slice(0, 24).join('')
}

export const useSceneStore = defineStore('scene', () => {
  // 当前编辑的场景文档
  const document = ref<SceneDocument | null>(null)
  const reconstructed = ref<ReconstructedEntity | null>(null)
  const validationIssues = ref<ValidationIssue[]>([])
  const isReconstructing = ref(false)
  let reconstructionRequest = 0

  // 创建一个新的空场景文档，用来初始化和新建
  function createEmptyDocument(): SceneDocument {
    return {
      id: `scene_${Date.now()}`,
      name: '未命名建筑',
      revision: 1,
      blueprint: {
        meta: {
          version: '1.0',
          type: 'building',
          name: '未命名建筑'
        },
        geometry: {
          elements: []
        },
        materials: {},
        behaviors: {}
      },
      dirty: false
    }
  }

  // 加载蓝图文件，导入文件
  // revision 参数可选：AI 生成/会话内刷新时传入当前 revision 以保持版本连续性，
  // 否则回退到蓝图 editor 元数据中的记录（无则从 1 开始），保证后续 patch base_revision 匹配。
  async function loadBlueprint(bp: Blueprint, name?: string, revision?: number): Promise<boolean> {
    const normalizedBlueprint = normalizeBlueprintInput(bp) as Blueprint
    const sceneName = compactSceneName(normalizedBlueprint.meta?.name || name || '未命名建筑')
    normalizedBlueprint.meta = { ...normalizedBlueprint.meta, name: sceneName }
    const editorRevision = typeof normalizedBlueprint.editor?.revision === 'number'
      ? normalizedBlueprint.editor.revision
      : undefined
    document.value = {
      id: `scene_${Date.now()}`,
      name: sceneName,
      revision: revision ?? editorRevision ?? 1,
      blueprint: normalizedBlueprint,
      dirty: false
    }
    validate(normalizedBlueprint)
    return await reconstruct()
  }

  async function applyPatch(patch: ScenePatch): Promise<boolean> {
    if (!document.value) {
      console.error('无场景文档，无法应用 patch')
      return false
    }

    // 检查 revision
    if (patch.base_revision !== document.value.revision) {
      console.error('Patch revision 不匹配', {
        expected: document.value.revision,
        received: patch.base_revision
      })
      return false
    }

    try {
      const before = deepClone(document.value.blueprint)
      // 应用到副本
      const newBlueprint = normalizeBlueprintInput(
        applyPatchToBlueprint(document.value.blueprint, patch)
      ) as Blueprint

      // 校验
      validate(newBlueprint)
      // 草稿已有错误也允许继续修改；重建问题保留在诊断中，不撤销用户编辑。
      document.value.blueprint = newBlueprint
      await reconstruct()
      document.value.revision++
      document.value.dirty = true

      useHistoryStore().push({
        label: patch.summary || '修改场景',
        before,
        after: deepClone(newBlueprint),
        patch,
        timestamp: Date.now(),
      })
      return true
    } catch (error) {
      console.error('应用 patch 失败', error)
      return false
    }
  }

  /** 恢复历史快照，不再次写入历史记录。 */
  async function restoreBlueprint(bp: Blueprint): Promise<boolean> {
    if (!document.value) return false
    const normalizedBlueprint = normalizeBlueprintInput(deepClone(bp)) as Blueprint
    validate(normalizedBlueprint)

    document.value.blueprint = normalizedBlueprint
    document.value.revision++
    document.value.dirty = true
    await reconstruct()
    return true
  }

  async function reconstruct(): Promise<boolean> {
    if (!document.value) return false

    const requestId = ++reconstructionRequest
    clearTextureLoadRecords()
    isReconstructing.value = true
    try {
      const entity = await reconstructScene(document.value.blueprint)
      if (requestId !== reconstructionRequest) return false
      reconstructed.value = entity
      return !entity.diagnostics.some(issue => issue.level === 'error')
    } catch (error) {
      console.error('重建失败', error)
      if (requestId === reconstructionRequest) {
        reconstructed.value = null
        validationIssues.value.push({ level: 'error', message: `场景重建失败：${String(error)}` })
      }
      return false
    } finally {
      if (requestId === reconstructionRequest) isReconstructing.value = false
    }
  }

  // 校验当前 Blueprint，返回 ValidationIssue 列表
  function validate(blueprint = document.value?.blueprint): ValidationIssue[] {
    if (!blueprint) return []
    try {
      validationIssues.value = validateBlueprint(blueprint)
    } catch (error) {
      validationIssues.value = [{ level: 'error', message: `蓝图校验执行失败：${String(error)}` }]
    }
    return validationIssues.value
  }

  function exportWild(): string {
    if (!document.value) return ''
    return JSON.stringify(document.value.blueprint, null, 2)
  }

  function markSaved() {
    if (document.value) {
      document.value.dirty = false
      document.value.savedAt = Date.now()
    }
  }

  return {
    document,
    reconstructed,
    validationIssues,
    isReconstructing,
    createEmptyDocument,
    loadBlueprint,
    applyPatch,
    restoreBlueprint,
    reconstruct,
    validate,
    exportWild,
    markSaved
  }
})
