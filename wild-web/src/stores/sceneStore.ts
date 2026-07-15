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

export const useSceneStore = defineStore('scene', () => {
  // 当前编辑的场景文档
  const document = ref<SceneDocument | null>(null)
  const reconstructed = ref<ReconstructedEntity | null>(null)
  const validationIssues = ref<ValidationIssue[]>([])
  const isReconstructing = ref(false)

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
  function loadBlueprint(bp: Blueprint, name?: string) {
    document.value = {
      id: `scene_${Date.now()}`,
      name: name || bp.meta.name || '未命名建筑',
      revision: 1,
      blueprint: bp,
      dirty: false
    }
    reconstruct()
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
      // 应用到副本
      const newBlueprint = applyPatchToBlueprint(document.value.blueprint, patch)

      // 校验
      const issues = validateBlueprint(newBlueprint)
      validationIssues.value = issues

      const hasErrors = issues.some(i => i.level === 'error')
      if (hasErrors) {
        console.error('Blueprint 校验失败', issues)
        return false
      }

      // 应用成功
      document.value.blueprint = newBlueprint
      document.value.revision++
      document.value.dirty = true

      await reconstruct()
      return true
    } catch (error) {
      console.error('应用 patch 失败', error)
      return false
    }
  }

  async function reconstruct() {
    if (!document.value) return

    isReconstructing.value = true
    try {
      // 调用 wild-core 重建场景
      console.log('开始重建场景...', document.value.blueprint)
      const { reconstructWildEntity } = await import('../renderer/wildCoreAdapter')
      const entity = await reconstructWildEntity(document.value.blueprint)
      console.log('场景重建成功', {
        meshCount: entity.meshes.length,
        materialCount: entity.materialParams?.length || 0,
        boundingBox: entity.boundingBox
      })
      reconstructed.value = entity
    } catch (error) {
      console.error('重建失败', error)
      reconstructed.value = null
    } finally {
      isReconstructing.value = false
    }
  }

  // 校验当前 Blueprint，返回 ValidationIssue 列表
  function validate(): ValidationIssue[] {
    if (!document.value) return []
    const issues = validateBlueprint(document.value.blueprint)
    validationIssues.value = issues
    return issues
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
    reconstruct,
    validate,
    exportWild,
    markSaved
  }
})
