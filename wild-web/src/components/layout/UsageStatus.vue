<template>
  <ElPopover v-if="auth.canEdit" trigger="click" placement="bottom-end" :width="300">
    <template #reference>
      <button type="button" class="usage-status" :class="{ 'has-exhausted-quota': hasExhaustedQuota }" :aria-label="usageDescription + '，查看额度与蓝图状态'" :title="usageDescription">
        <ElIcon aria-hidden="true"><Wallet /></ElIcon>
        <span class="usage-counts" aria-live="polite" aria-atomic="true">
          <span v-if="auth.isAdmin" class="usage-admin">管理员 · 无限使用</span>
          <template v-else><span v-for="item in quotas" :key="item.kind" :class="{ exhausted: item.remaining === 0 }">{{ item.shortLabel }} <strong>{{ item.remaining ?? '—' }}</strong></span></template>
        </span>
        <ElIcon v-if="scene.isLocked" class="lock-note" aria-label="蓝图已锁定"><Lock /></ElIcon>
        <ElIcon class="usage-arrow" aria-hidden="true"><ArrowDown /></ElIcon>
      </button>
    </template>
    <div class="usage-panel">
      <strong class="usage-heading">今日使用额度</strong>
      <p v-if="auth.isAdmin" class="usage-admin">管理员 · 无限使用</p>
      <dl v-else class="quota-details"><div v-for="item in quotas" :key="item.kind" :class="{ exhausted: item.remaining === 0 }"><dt>{{ item.label }}</dt><dd>剩余 <strong>{{ item.remaining ?? '—' }}</strong> / {{ item.limit ?? '—' }} 次</dd></div></dl>
      <p class="usage-help">AI 对话、修改和生成共用每日额度，每次请求扣 1 次。手工编辑按完成一次操作计数，拖动结束记一次。</p>
      <p class="usage-help">每天北京时间 00:00 自动恢复，不累计至次日。</p>
      <p v-if="scene.isCommitting" class="usage-note" role="status">正在保存编辑…</p>
      <p v-if="!auth.isAdmin && !auth.hasQuota('operations')" class="lock-note">今日手工操作次数已用完，明日零点恢复</p>
      <p v-if="!auth.isAdmin && !auth.hasQuota('ai')" class="lock-note">今日 AI 次数已用完，明日零点恢复</p>
      <p v-if="scene.isLocked" class="lock-note">蓝图已锁定 · 所有账号只读</p>
      <div class="usage-actions">
        <button v-if="auth.isAdmin && current?.filename" type="button" class="lock-button" :disabled="locking || scene.isCommitting" @click="toggleLock">{{ locking ? '处理中…' : scene.isLocked ? '解锁蓝图' : '锁定蓝图' }}</button>
        <button type="button" class="lock-button" :disabled="refreshing" @click="refreshStatus">{{ refreshing ? '刷新中…' : '刷新额度' }}</button>
      </div>
    </div>
  </ElPopover>
</template>
<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { ElIcon, ElMessage, ElPopover } from 'element-plus'
import { ArrowDown, Lock, Wallet } from '@element-plus/icons-vue'
import 'element-plus/es/components/popover/style/css'
import { useAuthStore, type UsageKind } from '../../stores/authStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useAgentStore } from '../../stores/agentStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import { apiRequest } from '../../services/adminApi'
const auth = useAuthStore(), scene = useSceneStore(), agent = useAgentStore(), workspace = useWorkspaceStore()
const locking = ref(false), refreshing = ref(false)
const current = computed(() => agent.sessions.find(item => item.session_id === agent.currentSessionId))
const labels: Array<{ kind: UsageKind; label: string; shortLabel: string }> = [
  { kind: 'operations', label: '手工操作', shortLabel: '手工' },
  { kind: 'ai', label: 'AI 使用', shortLabel: 'AI' },
]
const quotas = computed(() => labels.map(item => ({ ...item, remaining: auth.user?.usage?.[item.kind]?.remaining, limit: auth.user?.usage?.[item.kind]?.daily_limit })))
const hasExhaustedQuota = computed(() => !auth.isAdmin && quotas.value.some(item => item.remaining === 0))
const usageDescription = computed(() => auth.isAdmin ? '管理员 · 无限使用' : '今日剩余：' + quotas.value.map(item => `${item.label} ${item.remaining ?? '—'}`).join('，'))
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
let resetTimer: ReturnType<typeof setTimeout> | undefined
let active = false
function scheduleReset() {
  clearTimeout(resetTimer)
  resetTimer = undefined
  if (!active) return
  const resetsAt = auth.user?.usage?.operations.resets_at
  if (resetsAt && resetsAt > Date.now()) resetTimer = setTimeout(() => { void refreshStatus() }, resetsAt - Date.now() + 100)
}
function start() { active = true; if (!timer) timer = setInterval(() => { if (!document.hidden) void refreshStatus() }, 15000); scheduleReset() }
function stop() { active = false; clearInterval(timer); timer = undefined; clearTimeout(resetTimer); resetTimer = undefined }
function restoreVisibleStatus() { if (active && !document.hidden) void refreshStatus() }
onMounted(() => { document.addEventListener('visibilitychange', restoreVisibleStatus); start(); void refreshStatus() })
onActivated(() => { start(); void refreshStatus() })
onDeactivated(stop)
onBeforeUnmount(() => { document.removeEventListener('visibilitychange', restoreVisibleStatus); stop() })
watch(() => agent.currentSessionId, () => { void refreshStatus() })
watch(() => auth.user?.usage?.operations.resets_at, scheduleReset)
</script>
<style scoped>
.usage-status{display:inline-flex;flex-shrink:0;align-items:center;justify-content:center;gap:6px;min-width:32px;min-height:32px;padding:0 8px;border:1px solid var(--studio-border);border-radius:6px;background:transparent;color:var(--studio-muted);font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.usage-status:hover{background:var(--studio-hover);color:var(--studio-text)}
.usage-counts{display:inline-flex;align-items:center;gap:8px}
.usage-counts strong{color:var(--studio-text);margin-left:1px;font-variant-numeric:tabular-nums}
.exhausted,.usage-counts .exhausted strong,.lock-note{color:var(--studio-danger)}
.usage-status.has-exhausted-quota{color:var(--studio-danger)}
.usage-admin{color:var(--studio-accent)}
.usage-arrow{font-size:10px}
.usage-panel{display:grid;gap:12px;color:var(--studio-text);font-size:12px}
.usage-panel p,.quota-details,.quota-details dd{margin:0}
.usage-heading{font-size:13px;font-weight:600}
.quota-details{display:grid;gap:10px}.quota-details>div{display:flex;justify-content:space-between;gap:16px}.quota-details dd strong{font-variant-numeric:tabular-nums}
.usage-help,.usage-note{color:var(--studio-muted);line-height:1.7}
.usage-actions{display:flex;justify-content:flex-end;gap:8px;border-top:1px solid var(--studio-border);padding-top:10px}
.lock-button{font:inherit;min-height:32px;background:transparent;border:1px solid var(--studio-border);border-radius:4px;color:var(--studio-accent);cursor:pointer;padding:5px 10px}
.lock-button:hover{background:var(--studio-hover)}.lock-button:disabled{opacity:.45;cursor:wait}
.usage-status:focus-visible,.lock-button:focus-visible{outline:2px solid var(--studio-accent);outline-offset:2px}
@media(max-width:760px){.usage-status{padding:0 6px;gap:4px}.usage-counts,.usage-arrow{display:none}.lock-button{min-height:44px}}
</style>
