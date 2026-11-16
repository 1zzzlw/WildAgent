<template>
  <section class="admin-card" aria-labelledby="logs-heading">
    <header class="admin-card-heading"><div><h2 id="logs-heading">{{ username ? username + '的操作记录' : '操作记录' }}</h2><p>记录服务端收到的编辑、AI 对话、资料操作与管理变更。</p></div><RouterLink v-if="userId" class="admin-link" to="/admin/logs">查看全部用户</RouterLink></header>
    <form class="admin-filters" @submit.prevent="load(1)">
      <label>搜索记录<input v-model.trim="query" type="search" placeholder="用户、动作或蓝图名称" maxlength="128" /></label>
      <label>操作类型<select v-model="action"><option value="">全部操作</option><option v-for="(label, key) in actionLabels" :key="key" :value="key">{{ label }}</option></select></label>
      <label>开始日期<input v-model="startDate" type="date" /></label><label>结束日期<input v-model="endDate" type="date" /></label>
      <button class="admin-button primary" :disabled="loading">{{ loading ? '查询中…' : '查询' }}</button>
    </form>
    <p v-if="error" class="admin-error" role="alert">{{ error }} <button class="admin-link" @click="load(page)">重试</button></p>
    <div class="admin-table-scroll" :aria-busy="loading"><table class="admin-table"><thead><tr><th scope="col">时间</th><th scope="col">用户</th><th scope="col">操作</th><th scope="col">内容 / 对象</th><th scope="col">详情</th></tr></thead>
      <tbody><tr v-for="log in rows" :key="log.id"><td>{{ displayTime(log.created_at) }}</td><td><strong>{{ log.actor_name }}</strong><small class="admin-code">{{ log.actor_id }}</small></td><td><span class="admin-badge">{{ actionLabels[log.action] || log.action }}</span></td><td class="admin-log-summary"><span>{{ summary(log) }}</span><small v-if="log.resource">{{ log.resource }}</small></td><td><button class="admin-link" @click="selected = log">查看详情</button></td></tr><tr v-if="!rows.length && !loading"><td colspan="5" class="admin-empty">暂无符合条件的记录</td></tr></tbody>
    </table></div>
    <AdminPagination :page="page" :total="total" :busy="loading" @change="load" />
    <ElDialog :model-value="Boolean(selected)" title="操作详情" width="min(800px, calc(100vw - 32px))" @update:model-value="selected = undefined">
      <template v-if="selected"><dl class="admin-details"><dt>用户</dt><dd>{{ selected.actor_name }}</dd><dt>时间</dt><dd>{{ displayTime(selected.created_at) }}</dd><dt>操作</dt><dd>{{ actionLabels[selected.action] || selected.action }}</dd><dt>对象</dt><dd>{{ selected.resource || '—' }}</dd><dt>会话</dt><dd>{{ selected.session_id || '—' }}</dd><dt>AI 请求</dt><dd>{{ selected.request_id || '—' }}</dd></dl><pre class="admin-json" tabindex="0" aria-label="操作数据详情">{{ JSON.stringify(selected.details, null, 2) }}</pre></template>
    </ElDialog>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ElDialog } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { actionLabels, adminQuery, apiRequest, displayTime, type AuditLog, type Page } from '../../services/adminApi'
import AdminPagination from './AdminPagination.vue'
const route = useRoute()
const userId = computed(() => typeof route.query.user_id === 'string' ? route.query.user_id : undefined)
const username = computed(() => typeof route.query.username === 'string' ? route.query.username : '')
const query = ref(''), action = ref(''), startDate = ref(''), endDate = ref(''), error = ref('')
const rows = ref<AuditLog[]>([]), selected = ref<AuditLog>(), page = ref(1), total = ref(0), loading = ref(false)
let request = 0
function summary(log: AuditLog) { return String(log.details.label || log.details.message || log.details.content || log.details.summary || '查看详情') }
async function load(next = 1) {
  if (startDate.value && endDate.value && startDate.value > endDate.value) { error.value = '开始日期不能晚于结束日期'; return }
  const sequence = ++request
  loading.value = true; error.value = ''
  try {
    const result = await apiRequest<Page<AuditLog>>(adminQuery('logs', { user_id: userId.value, action: action.value, query: query.value, page: next,
      since: startDate.value ? new Date(startDate.value + 'T00:00:00').getTime() : undefined,
      until: endDate.value ? new Date(endDate.value + 'T23:59:59.999').getTime() : undefined }))
    if (sequence !== request) return
    rows.value = result.items; total.value = result.total; page.value = result.page
  } catch (cause) { if (sequence === request) error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { if (sequence === request) loading.value = false }
}
watch(userId, () => load(1), { immediate: true })
</script>
