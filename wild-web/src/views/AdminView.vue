<template>
  <div class="admin-layout">
    <aside class="admin-sidebar">
      <RouterLink class="admin-brand" to="/">W<span>WildAgent<small>管理后台</small></span></RouterLink>
      <nav aria-label="后台管理导航"><RouterLink v-for="item in navigation" :key="item.id" :to="'/admin/' + item.id" :class="{ current: section === item.id }"><el-icon><component :is="item.icon" /></el-icon>{{ item.label }}</RouterLink></nav>
      <div class="admin-sidebar-footer"><span>{{ auth.user?.username }} · 管理员</span><RouterLink to="/">← 返回建筑工作台</RouterLink></div>
    </aside>
    <main class="admin-main">
      <header class="admin-page-heading"><div><p class="admin-eyebrow">WILDAGENT ADMINISTRATION</p><h1>{{ currentTitle }}</h1><p>用户、使用额度与蓝图资料的统一管理。</p></div><button class="admin-button" @click="theme.toggle()"><el-icon><Sunny v-if="theme.isDark" /><Moon v-else /></el-icon>{{ theme.isDark ? '亮色主题' : '暗色主题' }}</button></header>
      <section v-if="section === 'overview'" aria-labelledby="overview-heading">
        <div class="admin-section-heading"><h2 id="overview-heading">运行概览</h2><button class="admin-button" :disabled="loading" @click="loadStats">{{ loading ? '刷新中…' : '刷新数据' }}</button></div>
        <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
        <div class="admin-metrics" :aria-busy="loading"><article v-for="metric in metrics" :key="metric.label" class="admin-card"><span>{{ metric.label }}</span><strong>{{ metric.value ?? '—' }}</strong><small>{{ metric.hint }}</small></article></div>
        <section class="admin-card admin-overview-note"><h2>权限与使用规则</h2><dl><dt>普通用户</dt><dd>每天手工操作 20 次，AI 对话、修改和生成共用 200 次，每次扣 1 次。北京时间每日 00:00 自动恢复，不累计。可在用户管理中调整每日上限和当日剩余。</dd><dt>管理员</dt><dd>不受次数限制，可管理账号、删除蓝图、锁定与解锁蓝图，以及设置全站 AI API。</dd><dt>锁定蓝图</dt><dd>对所有账号只读，包括管理员。需要修改时先解锁。</dd><dt>操作记录</dt><dd>编辑记录保留对象、变更字段和前后值；AI 对话保留请求、回复和执行结果。页面数据更新于 {{ updatedAt || '—' }}。</dd></dl></section>
      </section>
      <AdminUsers v-else-if="section === 'users'" />
      <AdminLogs v-else-if="section === 'logs'" />
      <AdminBlueprints v-else-if="section === 'blueprints'" />
      <section v-else class="admin-card admin-settings"><el-icon><Cpu /></el-icon><div><h2>AI API 设置</h2><p>管理全站模型供应商、模型名称、接口地址、API Key 与思考预算。设置会影响所有用户的新请求。</p><button class="admin-button primary" @click="modelVisible = true">打开 API 设置</button></div><LLMConfigDialog :visible="modelVisible" @update:visible="modelVisible = $event" /></section>
    </main>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { DataAnalysis, User, Document, Clock, Cpu, Sunny, Moon } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/authStore'
import { useThemeStore } from '../stores/themeStore'
import { apiRequest, type AdminStats } from '../services/adminApi'
import AdminUsers from '../components/admin/AdminUsers.vue'
import AdminLogs from '../components/admin/AdminLogs.vue'
import AdminBlueprints from '../components/admin/AdminBlueprints.vue'
import LLMConfigDialog from '../components/layout/LLMConfigDialog.vue'
import '../components/admin/admin.css'

const auth = useAuthStore(), theme = useThemeStore(), route = useRoute(), router = useRouter()
const navigation = [{ id: 'overview', label: '运行概览', icon: DataAnalysis }, { id: 'users', label: '用户管理', icon: User },
  { id: 'logs', label: '操作记录', icon: Clock }, { id: 'blueprints', label: '蓝图管理', icon: Document }, { id: 'settings', label: 'AI API 设置', icon: Cpu }]
const section = computed(() => String(route.params.section || 'overview'))
const currentTitle = computed(() => navigation.find(item => item.id === section.value)?.label || '运行概览')
const stats = ref<AdminStats>(), error = ref(''), loading = ref(false), updatedAt = ref(''), modelVisible = ref(false)
const metrics = computed(() => [
  { label: '用户总数', value: stats.value?.users, hint: `正常 ${stats.value?.active_users ?? '—'} · 封禁 ${stats.value?.blocked_users ?? '—'}` },
  { label: '最近 7 天注册', value: stats.value?.new_users_7d, hint: '不含已删除账号' },
  { label: '24 小时活跃用户', value: stats.value?.active_users_24h, hint: '根据已记录的操作去重' },
  { label: '有效管理员', value: stats.value?.administrators, hint: '拥有后台管理权限' },
  { label: '蓝图总数', value: stats.value?.blueprints, hint: `已锁定 ${stats.value?.locked_blueprints ?? '—'} 份` },
  { label: '操作记录', value: stats.value?.operations, hint: '已持久化的审计记录' },
])
async function loadStats() {
  loading.value = true; error.value = ''
  try { stats.value = await apiRequest<AdminStats>('/api/admin/stats'); updatedAt.value = new Date().toLocaleTimeString('zh-CN') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { loading.value = false }
}
watch(section, value => { if (value === 'overview') void loadStats(); if (value === 'settings') modelVisible.value = true }, { immediate: true })
watch(() => auth.isAdmin, allowed => { if (!allowed) void router.replace('/') })
let refreshTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => { refreshTimer = setInterval(() => { if (!document.hidden) void auth.refresh().catch(() => {}) }, 15000) })
onBeforeUnmount(() => clearInterval(refreshTimer))
</script>
