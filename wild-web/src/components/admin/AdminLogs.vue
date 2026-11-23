<template>
  <section class="admin-card" aria-label="操作记录列表">
    <header v-if="userId" class="admin-card-heading">
      <h2>{{ username ? username + '的操作记录' : '指定用户的操作记录' }}</h2>
      <RouterLink class="admin-link" to="/admin/logs">查看全部用户</RouterLink>
    </header>
    <form class="admin-filters" @submit.prevent="load(1)">
      <label>搜索记录<input v-model.trim="query" type="search" placeholder="用户、动作或蓝图名称" maxlength="128" /></label>
      <label>操作类型<select v-model="action"><option value="">全部操作</option><option v-for="(label, key) in actionLabels" :key="key" :value="key">{{ label }}</option></select></label>
      <label>开始日期<input v-model="startDate" type="date" /></label><label>结束日期<input v-model="endDate" type="date" /></label>
      <button class="admin-button primary" :disabled="loading">{{ loading ? '查询中…' : '查询' }}</button>
    </form>
    <p v-if="error" class="admin-error" role="alert">{{ error }} <button class="admin-link" @click="load(page)">重试</button></p>
    <div class="admin-table-scroll" :aria-busy="loading">
      <table class="admin-table" role="table">
        <thead><tr><th scope="col">时间</th><th scope="col">用户</th><th scope="col">操作</th><th scope="col">内容 / 对象</th><th scope="col">详情</th></tr></thead>
        <tbody>
          <tr v-for="log in rows" :key="log.id">
            <td data-label="时间">{{ displayTime(log.created_at) }}</td>
            <td data-label="用户"><strong>{{ log.actor_name }}</strong><small class="admin-code">{{ log.actor_id }}</small></td>
            <td data-label="操作"><span class="admin-badge">{{ actionLabels[log.action] || log.action }}</span></td>
            <td data-label="内容 / 对象" class="admin-log-summary"><span>{{ log.preview || '—' }}</span><small v-if="log.resource">{{ log.resource }}</small></td>
            <td class="admin-row-actions"><button class="admin-link" @click="openDetails(log)">查看详情</button></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="5" class="admin-empty">{{ loading ? '正在加载记录…' : error ? '加载失败，请重试' : '暂无符合条件的记录' }}</td></tr>
        </tbody>
      </table>
    </div>
    <AdminPagination :page="page" :total="total" :busy="loading" @change="load" />
    <ElDialog :model-value="Boolean(selected)" title="操作详情" width="min(800px, calc(100vw - 32px))" @update:model-value="closeDetails">
      <template v-if="selected">
        <dl class="admin-details"><dt>用户</dt><dd>{{ selected.actor_name }}</dd><dt>时间</dt><dd>{{ displayTime(selected.created_at) }}</dd><dt>操作</dt><dd>{{ actionLabels[selected.action] || selected.action }}</dd><dt>对象</dt><dd>{{ selected.resource || '—' }}</dd><dt>会话</dt><dd>{{ selected.session_id || '—' }}</dd><dt>AI 请求</dt><dd>{{ selected.request_id || '—' }}</dd></dl>
        <p v-if="detailsLoading" role="status">正在加载完整记录…</p>
        <p v-else-if="detailsError" class="admin-danger" role="alert">{{ detailsError }} <button class="admin-link" @click="openDetails(selected)">重试</button></p>
        <pre v-else-if="details" class="admin-json" tabindex="0" aria-label="操作数据详情">{{ details }}</pre>
      </template>
    </ElDialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ElDialog } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { actionLabels, adminQuery, apiRequest, displayTime, type AuditLog, type AuditLogSummary, type Page } from '../../services/adminApi'
import AdminPagination from './AdminPagination.vue'
const route = useRoute()
const userId = computed(() => typeof route.query.user_id === 'string' ? route.query.user_id : undefined)
const username = computed(() => typeof route.query.username === 'string' ? route.query.username : '')
const query = ref(''), action = ref(''), startDate = ref(''), endDate = ref(''), error = ref('')
const rows = ref<AuditLogSummary[]>([]), page = ref(1), total = ref(0), loading = ref(false)
const selected = ref<AuditLogSummary>(), details = ref(''), detailsError = ref(''), detailsLoading = ref(false)
let request = 0
let detailRequest: AbortController | undefined

function closeDetails() {
  detailRequest?.abort()
  detailRequest = undefined
  selected.value = undefined
  details.value = ''
  detailsError.value = ''
  detailsLoading.value = false
}
async function openDetails(log: AuditLogSummary) {
  closeDetails()
  selected.value = log
  detailsLoading.value = true
  const controller = new AbortController()
  detailRequest = controller
  try {
    const record = await apiRequest<AuditLog>(`/api/admin/logs/${encodeURIComponent(log.id)}`, 'GET', undefined, controller.signal)
    if (!controller.signal.aborted) details.value = JSON.stringify(record.details, null, 2)
  } catch (cause) {
    if (!controller.signal.aborted) detailsError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (!controller.signal.aborted) detailsLoading.value = false
  }
}
async function load(next = 1) {
  if (startDate.value && endDate.value && startDate.value > endDate.value) { error.value = '开始日期不能晚于结束日期'; return }
  const sequence = ++request
  loading.value = true; error.value = ''
  try {
    const result = await apiRequest<Page<AuditLogSummary>>(adminQuery('logs', { user_id: userId.value, action: action.value, query: query.value, page: next, include_details: false,
      since: startDate.value ? new Date(startDate.value + 'T00:00:00').getTime() : undefined,
      until: endDate.value ? new Date(endDate.value + 'T23:59:59.999').getTime() : undefined }))
    if (sequence !== request) return
    rows.value = result.items; total.value = result.total; page.value = result.page
  } catch (cause) { if (sequence === request) error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { if (sequence === request) loading.value = false }
}
watch(userId, () => { closeDetails(); void load(1) }, { immediate: true })
onBeforeUnmount(closeDetails)
</script>
