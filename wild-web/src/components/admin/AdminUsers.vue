<template>
  <section class="admin-card" aria-labelledby="users-heading">
    <header class="admin-card-heading"><div><h2 id="users-heading">用户管理</h2><p>查询账号、管理身份与状态，调整三类剩余次数。</p></div></header>
    <form class="admin-filters" @submit.prevent="load(1)">
      <label>账号查询<input v-model.trim="query" type="search" placeholder="用户名或邮箱" maxlength="128" /></label>
      <label>账号状态<select v-model="status"><option value="">全部状态</option><option value="active">正常</option><option value="blocked">已封禁</option></select></label>
      <button class="admin-button primary" :disabled="loading">{{ loading ? '查询中…' : '查询' }}</button>
    </form>
    <p v-if="error" class="admin-error" role="alert">{{ error }} <button class="admin-link" @click="load(page)">重试</button></p>
    <div class="admin-table-scroll" :aria-busy="loading">
      <table class="admin-table">
        <thead><tr><th scope="col">账号</th><th scope="col">身份 / 状态</th><th scope="col">剩余次数</th><th scope="col">累计使用</th><th scope="col">注册时间</th><th scope="col">操作</th></tr></thead>
        <tbody>
          <tr v-for="user in rows" :key="user.id">
            <td><strong>{{ user.username }}</strong><small>{{ user.email }}</small></td>
            <td><span class="admin-badge">{{ user.identity === 2 ? '管理员' : '普通用户' }}</span><small :class="{ 'admin-danger': user.status === 'blocked' }">{{ user.status === 'active' ? '正常' : '已封禁' }}</small></td>
            <td><span v-if="user.identity === 2">无限使用</span><template v-else><small>操作 {{ user.operations_remaining }}</small><small>AI 修改 {{ user.modifications_remaining }} · 生成 {{ user.generations_remaining }}</small></template></td>
            <td><small>操作 {{ user.usage.operations.used }}</small><small>AI 修改 {{ user.usage.modifications.used }} · 生成 {{ user.usage.generations.used }}</small></td>
            <td>{{ displayTime(user.created_at) }}</td>
            <td><div class="admin-actions"><button class="admin-link" @click="edit(user)">身份与额度</button><RouterLink class="admin-link" :to="{ path: '/admin/logs', query: { user_id: user.id, username: user.username } }">操作记录</RouterLink><button class="admin-link danger" :disabled="user.id === auth.user?.id || saving" @click="remove(user)">删除</button></div></td>
          </tr>
          <tr v-if="!rows.length && !loading"><td colspan="6" class="admin-empty">{{ error ? '加载失败，请重试' : '没有符合条件的用户' }}</td></tr>
        </tbody>
      </table>
    </div>
    <AdminPagination :page="page" :total="total" :busy="loading" @change="load" />
    <ElDialog v-model="dialog" title="身份与使用额度" width="min(540px, calc(100vw - 32px))" :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving">
      <form v-if="selected" class="admin-form" @submit.prevent="save">
        <p><strong>{{ selected.username }}</strong> · {{ selected.email }}</p>
        <label>账号身份<select v-model.number="form.identity" :disabled="selected.id === auth.user?.id"><option :value="1">普通用户</option><option :value="2">管理员</option></select></label>
        <label>账号状态<select v-model="form.status" :disabled="selected.id === auth.user?.id"><option value="active">正常</option><option value="blocked">封禁</option></select></label>
        <p class="admin-hint">管理员不受次数限制。以下数值是普通用户的剩余次数，不会清空累计使用记录。</p>
        <div class="admin-quota-inputs">
          <label>手工操作<input v-model.number="form.operations_remaining" type="number" min="0" max="1000000000" step="1" required :disabled="form.identity === 2" /></label>
          <label>AI 修改<input v-model.number="form.modifications_remaining" type="number" min="0" max="1000000000" step="1" required :disabled="form.identity === 2" /></label>
          <label>AI 生成<input v-model.number="form.generations_remaining" type="number" min="0" max="1000000000" step="1" required :disabled="form.identity === 2" /></label>
        </div>
        <p v-if="formError" class="admin-error" role="alert">{{ formError }}</p>
        <footer class="admin-dialog-actions"><button class="admin-button" type="button" :disabled="saving" @click="dialog = false">取消</button><button class="admin-button primary" :disabled="saving">{{ saving ? '保存中…' : '保存设置' }}</button></footer>
      </form>
    </ElDialog>
  </section>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ElDialog, ElMessage, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { useAuthStore } from '../../stores/authStore'
import { adminQuery, apiRequest, displayTime, type AdminUser, type Page } from '../../services/adminApi'
import AdminPagination from './AdminPagination.vue'

const auth = useAuthStore()
const rows = ref<AdminUser[]>([])
const page = ref(1), total = ref(0), query = ref(''), status = ref(''), error = ref('')
const loading = ref(false), saving = ref(false), dialog = ref(false), formError = ref('')
const selected = ref<AdminUser>()
const form = reactive({ identity: 1 as 1 | 2, status: 'active', operations_remaining: 0, modifications_remaining: 0, generations_remaining: 0 })
let request = 0
async function load(next = 1) {
  const sequence = ++request
  loading.value = true
  error.value = ''
  try {
    const result = await apiRequest<Page<AdminUser>>(adminQuery('users', { query: query.value, status: status.value, page: next }))
    if (sequence !== request) return
    rows.value = result.items; total.value = result.total; page.value = result.page
  } catch (cause) { if (sequence === request) error.value = String(cause instanceof Error ? cause.message : cause) }
  finally { if (sequence === request) loading.value = false }
}
function edit(user: AdminUser) {
  selected.value = user
  Object.assign(form, { identity: user.identity, status: user.status, operations_remaining: user.operations_remaining,
    modifications_remaining: user.modifications_remaining, generations_remaining: user.generations_remaining })
  formError.value = ''; dialog.value = true
}
async function save() {
  if (!selected.value || saving.value) return
  saving.value = true; formError.value = ''
  try {
    await apiRequest(`/api/admin/users/${selected.value.id}`, 'PATCH', form)
    dialog.value = false; ElMessage.success('账号设置已更新'); await load(page.value); await auth.refresh()
  } catch (cause) { formError.value = cause instanceof Error ? cause.message : String(cause) }
  finally { saving.value = false }
}
async function remove(user: AdminUser) {
  try { await ElMessageBox.confirm(`删除“${user.username}”后，该账号将永久停用。蓝图归属与审计记录会保留。`, '删除账号', { confirmButtonText: '删除账号', cancelButtonText: '取消', type: 'warning' }) }
  catch { return }
  saving.value = true
  try { await apiRequest(`/api/admin/users/${user.id}`, 'DELETE'); ElMessage.success('账号已删除'); await load(rows.value.length === 1 ? Math.max(1, page.value - 1) : page.value) }
  catch (cause) { ElMessage.error(cause instanceof Error ? cause.message : String(cause)) }
  finally { saving.value = false }
}
onMounted(() => load())
</script>
