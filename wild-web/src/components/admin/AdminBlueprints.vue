<template>
  <section class="admin-card" aria-labelledby="blueprints-heading">
    <header class="admin-card-heading"><div><h2 id="blueprints-heading">蓝图管理</h2><p>锁定后，所有账号都不能编辑、覆盖或删除。管理员也需要先解锁。</p></div></header>
    <form class="admin-filters" @submit.prevent="load(1)">
      <label>搜索蓝图<input v-model.trim="query" type="search" placeholder="蓝图名称、文件名或所属用户" maxlength="128" /></label>
      <label>锁定状态<select v-model="lockFilter"><option value="">全部状态</option><option value="true">已锁定</option><option value="false">未锁定</option></select></label>
      <button class="admin-button primary" :disabled="loading">{{ loading ? '查询中…' : '查询' }}</button>
    </form>
    <p v-if="error" class="admin-error" role="alert">{{ error }} <button class="admin-link" @click="load(page)">重试</button></p>
    <div class="admin-table-scroll" :aria-busy="loading"><table class="admin-table"><thead><tr><th scope="col">蓝图 / 所属用户</th><th scope="col">内容</th><th scope="col">状态</th><th scope="col">更新时间</th><th scope="col">操作</th></tr></thead>
      <tbody><tr v-for="blueprint in rows" :key="blueprint.filename">
        <td><strong>{{ blueprint.name }}</strong><small>{{ blueprint.owner_name || '共享资料' }}</small><small class="admin-code">{{ blueprint.filename }}</small></td>
        <td>{{ blueprint.elements_count }} 元素 · {{ blueprint.components_count }} 构件</td>
        <td><span :class="['admin-badge', { warning: blueprint.locked }]">{{ blueprint.locked ? '已锁定 · 只读' : '可编辑' }}</span></td>
        <td>{{ displayTime(blueprint.updated_at) }}</td>
        <td><div class="admin-actions"><button class="admin-link" @click="viewDetails(blueprint)">查看详情</button><a class="admin-link" :href="sceneUrl(blueprint.filename)" :download="blueprint.filename.split('/').pop()">导出 WILD</a><button class="admin-link" :disabled="busy" @click="toggleLock(blueprint)">{{ blueprint.locked ? '解锁' : '锁定' }}</button><button class="admin-link danger" :disabled="busy || blueprint.locked" :title="blueprint.locked ? '请先解锁蓝图' : '删除蓝图'" @click="remove(blueprint)">删除</button></div></td>
      </tr><tr v-if="!rows.length && !loading"><td colspan="5" class="admin-empty">没有符合条件的蓝图</td></tr></tbody>
    </table></div>
    <AdminPagination :page="page" :total="total" :busy="loading" @change="load" />
    <ElDialog :model-value="Boolean(selected)" title="蓝图详情" width="min(620px, calc(100vw - 32px))" @update:model-value="selected = undefined">
      <template v-if="selected">
        <dl class="admin-details"><dt>蓝图</dt><dd>{{ selected.name }}</dd><dt>文件名</dt><dd>{{ selected.filename }}</dd><dt>所属用户</dt><dd>{{ selected.owner_name || '共享资料' }}</dd><dt>内容</dt><dd>{{ selected.elements_count }} 元素 · {{ selected.components_count }} 构件</dd><dt>状态</dt><dd>{{ selected.locked ? '已锁定 · 只读' : '可编辑' }}</dd><dt>更新时间</dt><dd>{{ displayTime(selected.updated_at) }}</dd>
          <template v-if="metrics"><dt>占地</dt><dd>{{ metrics.footprint_area === null ? '暂不可测量' : metrics.footprint_area.toFixed(2) + ' ㎡' }}</dd><template v-if="metrics.footprint_width !== null"><dt>宽 × 深</dt><dd>{{ metrics.footprint_width.toFixed(2) }} × {{ metrics.footprint_depth?.toFixed(2) }} m</dd></template><dt>计算依据</dt><dd>{{ metrics.footprint_kind === 'floor_union' ? '最低层矩形楼板并集' : metrics.footprint_kind === 'bounds' ? '包络估算' : '没有可测量楼板或墙体' }}</dd></template>
        </dl>
        <p v-if="detailsLoading" role="status">正在读取占地信息…</p>
        <p v-if="detailsError" class="admin-danger" role="alert">{{ detailsError }} <button class="admin-link" @click="viewDetails(selected)">重试</button></p>
      </template>
    </ElDialog>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElDialog, ElMessage, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { adminQuery, apiRequest, displayTime, sceneUrl, type AdminBlueprint, type BlueprintMetrics, type Page } from '../../services/adminApi'
import AdminPagination from './AdminPagination.vue'
const query = ref(''), lockFilter = ref(''), error = ref(''), loading = ref(false), busy = ref(false)
const rows = ref<AdminBlueprint[]>([]), page = ref(1), total = ref(0)
const selected = ref<AdminBlueprint>(), metrics = ref<BlueprintMetrics>(), detailsLoading = ref(false), detailsError = ref('')
let request = 0
let detailsRequest = 0
async function load(next = 1) {
  const sequence = ++request
  loading.value = true; error.value = ''
  try {
    const result = await apiRequest<Page<AdminBlueprint>>(adminQuery('blueprints', { query: query.value, locked: lockFilter.value, page: next }))
    if (sequence !== request) return
    rows.value = result.items; total.value = result.total; page.value = result.page
  } catch (cause) { if (sequence === request) error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { if (sequence === request) loading.value = false }
}
async function viewDetails(blueprint: AdminBlueprint) {
  const sequence = ++detailsRequest
  selected.value = blueprint; metrics.value = undefined; detailsError.value = ''; detailsLoading.value = true
  const filename = blueprint.filename.split('/').map(encodeURIComponent).join('/')
  try {
    const result = await apiRequest<BlueprintMetrics>(`/api/admin/blueprints/${filename}/metrics`)
    if (sequence === detailsRequest) metrics.value = result
  } catch (cause) {
    if (sequence === detailsRequest) detailsError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (sequence === detailsRequest) detailsLoading.value = false
  }
}
async function toggleLock(blueprint: AdminBlueprint) {
  busy.value = true
  try {
    await apiRequest(`/api/admin/blueprints/${blueprint.filename.split('/').map(encodeURIComponent).join('/')}`, 'PATCH', { locked: !blueprint.locked })
    ElMessage.success(blueprint.locked ? '蓝图已解锁' : '蓝图已锁定'); await load(page.value)
  } catch (cause) { ElMessage.error(cause instanceof Error ? cause.message : String(cause)) }
  finally { busy.value = false }
}
async function remove(blueprint: AdminBlueprint) {
  try { await ElMessageBox.confirm(`确定删除蓝图“${blueprint.name}”？此操作无法撤销。`, '删除蓝图', { confirmButtonText: '删除蓝图', cancelButtonText: '取消', type: 'warning' }) }
  catch { return }
  busy.value = true
  try { await apiRequest(sceneUrl(blueprint.filename), 'DELETE'); ElMessage.success('蓝图已删除'); await load(rows.value.length === 1 ? Math.max(1, page.value - 1) : page.value) }
  catch (cause) { ElMessage.error(cause instanceof Error ? cause.message : String(cause)) }
  finally { busy.value = false }
}
onMounted(() => load())
</script>
