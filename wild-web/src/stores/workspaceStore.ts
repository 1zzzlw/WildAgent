import { defineStore } from 'pinia'
import { h, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, ElOption, ElSelect } from 'element-plus'
import { agentBridge } from '../agent/agentBridge'
import { useAgentStore } from './agentStore'
import { useSceneStore } from './sceneStore'
import { useHistoryStore } from './historyStore'
import { useSelectionStore } from './selectionStore'
import { deepClone } from '../utils/common'
import type { Blueprint } from '../types/blueprint'
import { playUISound } from '../utils/uiSound'
import { useAuthStore } from './authStore'

export const useWorkspaceStore = defineStore('workspace', () => {
  const isSaving = ref(false)
  const isImporting = ref(false)
  let sessionLoad: AbortController | null = null
  watch(() => useAuthStore().user?.id, cancelSessionLoad)

  function cancelSessionLoad() {
    sessionLoad?.abort()
    sessionLoad = null
    const scene = useSceneStore()
    scene.cancelReconstruction()
    scene.isLoading = false
  }

  /** 蓝图优先显示，聊天记录独立恢复；离开会话后取消未完成的加载。 */
  async function openSession(sessionId: string): Promise<boolean> {
    const scene = useSceneStore()
    if (isImporting.value || isSaving.value || scene.isCommitting) return false
    if (scene.document?.dirty && !await saveScene()) return false
    cancelSessionLoad()
    const controller = new AbortController()
    sessionLoad = controller
    scene.isLoading = true
    const agent = useAgentStore()
    const accountId = useAuthStore().user?.id
    const current = () => sessionLoad === controller && !controller.signal.aborted
      && useAuthStore().user?.id === accountId

    void agentBridge.fetchSessionMessages(sessionId, controller.signal).then(messages => {
      if (messages && current()) agent.mergeMessagesForSession(sessionId, messages)
    })
    void agentBridge.fetchSessionTurns(sessionId, controller.signal).then(turns => {
      if (turns && current()) agent.mergeTurnsForSession(sessionId, turns)
    })
    try {
      const blueprint = await agentBridge.loadSessionBlueprint(sessionId, controller.signal)
      if (!current()) return false
      const info = agent.sessions.find(item => item.session_id === sessionId)
      if (!blueprint && info?.status !== 'draft') {
        ElMessage.error('无法读取会话蓝图，请稍后重试')
        return false
      }
      // 蓝图成功读取后才切换，读取失败时继续保留原会话和画布。
      agent.switchToSession(sessionId)
      useHistoryStore().clear()
      useSelectionStore().clearSelection()
      const source = blueprint as unknown as Blueprint | null
      const empty = source ? undefined : scene.createEmptyDocument()
      await scene.loadBlueprint(source || empty!.blueprint, info?.name || empty?.name)
      if (!current()) return false
      scene.markSaved()
      if (source) {
        agent.updateSessionInfo(sessionId, info?.name || source.meta.name,
          source.geometry.elements?.length || 0, source.geometry.components?.length || 0)
      }
      return true
    } finally {
      if (current()) scene.isLoading = false
    }
  }

  async function saveScene(): Promise<boolean> {
    if (!useAuthStore().canEdit) return false
    const scene = useSceneStore()
    if (scene.isLocked) { ElMessage.warning('蓝图已锁定，请先由管理员解锁'); return false }
    const agent = useAgentStore()
    const doc = scene.document
    if (!doc || isSaving.value || scene.isCommitting) return false
    if (!agent.currentSessionId) agent.switchToSession(agent.createSession(doc.name))
    const sessionId = agent.currentSessionId
    const revision = doc.revision
    const blueprint = deepClone(doc.blueprint)
    const issues = scene.validate(blueprint)
    isSaving.value = true
    try {
      const saved = await agentBridge.syncBlueprintToBackend(
        blueprint as unknown as Record<string, unknown>, { sessionId, revision, baseRevision: revision, operationId: crypto.randomUUID(), label: '保存蓝图' },
      )
      if (!saved) {
        if (scene.document === doc) doc.dirty = true
        ElMessage.error('保存失败，当前草稿已保留，请检查连接后重试')
        playUISound('error')
        return false
      }
      const elements = blueprint.geometry.elements?.length || 0
      const components = blueprint.geometry.components?.length || 0
      agent.updateSessionInfo(sessionId, blueprint.meta.name || doc.name, elements + components, components)
      agent.setSessionSaved(sessionId)
      // 保存期间可能继续编辑或切换文档，只清除与本次快照一致的未保存状态。
      if (scene.document === doc && doc.revision === revision && agent.currentSessionId === sessionId) scene.markSaved()
      const errors = issues.filter(issue => issue.level === 'error').length
      ElMessage.success(errors ? `草稿已保存到服务器，仍有 ${errors} 项校验问题` : '已保存到服务器')
      playUISound('save')
      return true
    } finally {
      isSaving.value = false
    }
  }

  async function newScene(): Promise<boolean> {
    if (!useAuthStore().canEdit) return false
    cancelSessionLoad()
    const scene = useSceneStore()
    if (scene.document?.dirty && !await saveScene()) return false
    const agent = useAgentStore()
    agent.switchToSession(agent.createSession())
    useHistoryStore().clear()
    useSelectionStore().clearSelection()
    const empty = scene.createEmptyDocument()
    await scene.loadBlueprint(empty.blueprint, empty.name)
    return true
  }

  async function importFile(file: File): Promise<boolean> {
    if (!useAuthStore().canEdit) return false
    if (isImporting.value || isSaving.value) return false
    cancelSessionLoad()
    isImporting.value = true
    try {
      const blueprint = JSON.parse(await file.text()) as Blueprint
      // 检查文件结构，确保包含 meta 和 geometry
      if (!blueprint || !blueprint.meta || typeof blueprint.meta !== 'object' || Array.isArray(blueprint.meta)
        || !blueprint.geometry || typeof blueprint.geometry !== 'object' || Array.isArray(blueprint.geometry)) {
        throw new Error('文件缺少 meta 或 geometry 对象')
      }
      const scene = useSceneStore()
      if (scene.document?.dirty && !await saveScene()) return false
      const candidates = await agentBridge.findBlueprintImportCandidates(file.name, blueprint)
      let target: typeof candidates[number] | undefined = candidates[0]
      if (candidates.length > 1) {
        const selected = ref(target!.filename || '')
        try {
          await ElMessageBox({
            title: '存在多份匹配蓝图，请选择要替换的记录',
            message: () => h(ElSelect, {
              modelValue: selected.value,
              'onUpdate:modelValue': (value: unknown) => { selected.value = String(value) },
              style: { width: '100%' },
            }, () => candidates.map(item => h(ElOption, { key: item.filename, label: item.filename, value: item.filename }))),
            showCancelButton: true,
            confirmButtonText: '替换所选蓝图',
            cancelButtonText: '取消导入',
          })
        } catch { return false }
        target = candidates.find(item => item.filename === selected.value)
        if (!target) return false
      }
      const agent = useAgentStore()
      const sessionId = target?.session_id || agent.createSession(blueprint.meta.name)
      if (target?.locked) throw new Error('蓝图已锁定，请先由管理员解锁再导入替换')
      // 先绑定原会话和文件路径，保存及后续编辑都覆盖同一条数据库记录。
      agent.switchToSession(sessionId)
      if (target) {
        const session = agent.sessions.find(item => item.session_id === sessionId)!
        Object.assign(session, target)
      }
      useHistoryStore().clear()
      useSelectionStore().clearSelection()
      // 渲染蓝图文件
      const loading = scene.loadBlueprint(blueprint, file.name)
      const imported = scene.document
      if (imported) imported.dirty = true
      await loading
      if (scene.document !== imported || agent.currentSessionId !== sessionId) return false
      const saved = await saveScene()
      if (target) {
        const [messages, turns] = await Promise.all([
          agentBridge.fetchSessionMessages(sessionId), agentBridge.fetchSessionTurns(sessionId),
        ])
        if (messages) agent.mergeMessagesForSession(sessionId, messages)
        if (turns) agent.mergeTurnsForSession(sessionId, turns)
      }
      return saved
    } catch (error) {
      ElMessage.error(`导入失败：${error instanceof Error ? error.message : String(error)}`)
      return false
    } finally {
      isImporting.value = false
    }
  }

  return { isSaving, isImporting, saveScene, newScene, importFile, openSession }
})
