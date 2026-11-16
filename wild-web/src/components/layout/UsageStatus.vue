<template>
  <div v-if="auth.canEdit" class="usage-status" aria-label="账号使用额度与蓝图状态">
    <div class="usage-counts" aria-live="polite" aria-atomic="true" :title="'操作按一次完成的编辑计数，拖动结束记一次；AI 修改和生成分别计数。'">
      <span v-if="auth.isAdmin" class="usage-admin">管理员 · 无限使用</span>
      <template v-else><span>剩余次数</span><span v-for="item in quotas" :key="item.kind" :class="{ exhausted: item.remaining === 0 }">{{ item.label }} <strong>{{ item.remaining ?? '—' }}</strong></span></template>
    </div>
    <span v-if="scene.isCommitting" class="usage-note" role="status">正在保存编辑…</span>
    <span v-if="!auth.isAdmin && !auth.hasQuota('operations')" class="lock-note">手工次数已用完，请联系管理员调整</span>
    <span v-if="scene.isLocked" class="lock-note">蓝图已锁定 · 所有账号只读</span>
    <button v-if="auth.isAdmin && current?.filename" type="button" class="lock-button" :disabled="locking || scene.isCommitting" @click="toggleLock">{{ locking ? '处理中…' : scene.isLocked ? '解锁蓝图' : '锁定蓝图' }}</button>
    <button type="button" class="lock-button" :disabled="refreshing" @click="refreshStatus">{{ refreshing ? '刷新中…' : '刷新额度' }}</button>
  </div>
</template>
<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore, type UsageKind } from '../../stores/authStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useAgentStore } from '../../stores/agentStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import { apiRequest } from '../../services/adminApi'
const auth = useAuthStore(), scene = useSceneStore(), agent = useAgentStore(), workspace = useWorkspaceStore()
const locking = ref(false), refreshing = ref(false)
const current = computed(() => agent.sessions.find(item => item.session_id === agent.currentSessionId))
const labels: Array<{ kind: UsageKind; label: string }> = [{ kind: 'operations', label: '手工操作' }, { kind: 'modifications', label: 'AI 修改' }, { kind: 'generations', label: '生成' }]
const quotas = computed(() => labels.map(item => ({ ...item, remaining: auth.user?.usage?.[item.kind].remaining })))
async function refreshStatus() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await auth.refresh()
    const target = current.value
    if (target?.filename) {
      const response = await fetch(`/api/sessions/${encodeURIComponent(target.session_id)}`, { cache: 'no-store' })
      if (response.ok) { const info = await response.json(); target.locked = Boolean(info.locked) }
      else if (response.status === 404) target.locked = true
    }
  } catch { /* 临时网络故障保留上一次状态；真正写入始终由服务器再次校验。 */ }
  finally { refreshing.value = false }
}
async function toggleLock() {
  const target = current.value
  if (!target?.filename || locking.value) return
  locking.value = true
  try {
    if (!scene.isLocked && scene.document?.dirty && !await workspace.saveScene()) return
    const result = await apiRequest<{ locked: boolean }>(`/api/admin/blueprints/${target.filename.split('/').map(encodeURIComponent).join('/')}`, 'PATCH', { locked: !scene.isLocked })
    target.locked = result.locked
    ElMessage.success(result.locked ? '蓝图已锁定' : '蓝图已解锁')
  } catch (cause) { ElMessage.error(cause instanceof Error ? cause.message : String(cause)) }
  finally { locking.value = false }
}
let timer: ReturnType<typeof setInterval> | undefined
function start() { if (!timer) timer = setInterval(() => { if (!document.hidden) void refreshStatus() }, 15000) }
function stop() { clearInterval(timer); timer = undefined }
onMounted(() => { start(); void refreshStatus() })
onActivated(() => { start(); void refreshStatus() })
onDeactivated(stop)
onBeforeUnmount(stop)
watch(() => agent.currentSessionId, () => { void refreshStatus() })
</script>
<style scoped>
.usage-status{display:flex;align-items:center;flex-wrap:wrap;gap:12px;min-height:34px;padding:5px 18px;background:var(--studio-input);border-bottom:1px solid var(--studio-border);color:var(--studio-muted);font-size:11px}.usage-counts{display:flex;align-items:center;flex-wrap:wrap;gap:16px;margin-right:auto}.usage-counts strong{color:var(--studio-text);margin-left:4px;font-variant-numeric:tabular-nums}.usage-counts .exhausted,.usage-counts .exhausted strong,.lock-note{color:var(--studio-danger)}.usage-admin{color:var(--studio-accent)}.lock-button{font:inherit;min-height:24px;background:transparent;border:0;color:var(--studio-accent);cursor:pointer;padding:2px 5px}.lock-button:hover{text-decoration:underline}.lock-button:disabled{opacity:.45;cursor:wait}.lock-button:focus-visible{outline:2px solid var(--studio-accent);outline-offset:2px}@media(max-width:700px){.usage-status{padding:5px 12px;gap:6px}.usage-counts{gap:10px}.usage-note{display:none}}
</style>
