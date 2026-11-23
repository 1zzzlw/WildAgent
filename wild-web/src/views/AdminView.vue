<template>
  <div class="admin-layout">
    <aside class="admin-sidebar">
      <RouterLink class="admin-brand" to="/admin">
        <span class="admin-brand-mark" aria-hidden="true">W</span><span>WildAgent<small>管理后台</small></span>
      </RouterLink>
      <nav aria-label="后台管理导航">
        <RouterLink v-for="item in navigation" :key="item.id" :to="'/admin/' + item.id"
          :class="{ current: section === item.id }" :aria-current="section === item.id ? 'page' : undefined">
          <el-icon aria-hidden="true"><component :is="item.icon" /></el-icon>{{ item.label }}
        </RouterLink>
      </nav>
      <div class="admin-sidebar-footer">
        <span :title="auth.user?.username">{{ auth.user?.username }} · 管理员</span>
        <RouterLink to="/"><el-icon aria-hidden="true"><Back /></el-icon>工作台</RouterLink>
      </div>
    </aside>
    <main class="admin-main">
      <header class="admin-page-heading">
        <div><h1 id="admin-page-title">{{ currentTitle }}</h1><p v-if="section === 'overview' && updatedAt">更新于 {{ updatedAt }}</p></div>
        <div class="admin-heading-actions">
          <button v-if="section === 'overview'" class="admin-button" :disabled="loading" @click="loadStats">
            <el-icon aria-hidden="true"><Refresh /></el-icon>{{ loading ? '刷新中…' : '刷新' }}
          </button>
          <button class="admin-button admin-theme" type="button" :aria-label="theme.isDark ? '切换为亮色主题' : '切换为暗色主题'"
            :title="theme.isDark ? '切换为亮色主题' : '切换为暗色主题'" @click="theme.toggle()">
            <el-icon aria-hidden="true"><Sunny v-if="theme.isDark" /><Moon v-else /></el-icon>
          </button>
        </div>
      </header>
      <section v-if="section === 'overview'" aria-labelledby="admin-page-title">
        <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
        <div class="admin-metrics" :aria-busy="loading">
          <article v-for="metric in metrics" :key="metric.label" class="admin-card">
            <div class="admin-metric-label"><el-icon aria-hidden="true"><component :is="metric.icon" /></el-icon>{{ metric.label }}</div>
            <strong>{{ metric.value?.toLocaleString('zh-CN') ?? '—' }}</strong>
            <small v-if="metric.hint">{{ metric.hint }}</small>
          </article>
        </div>
        <section class="admin-card admin-overview-note">
          <h2>权限与使用规则</h2>
          <dl>
            <dt>普通用户</dt><dd>默认每天手工操作 20 次，AI 对话、修改和生成共用 5 次，每次扣 1 次。额度每天北京时间 00:00 恢复，可在用户管理中调整。</dd>
            <dt>管理员</dt><dd>不限次，可管理账号、蓝图和全站 AI API。</dd>
            <dt>锁定蓝图</dt><dd>对所有账号只读，需要修改时先解锁。</dd>
          </dl>
        </section>
      </section>
      <AdminUsers v-else-if="section === 'users'" />
      <AdminLogs v-else-if="section === 'logs'" />
      <AdminBlueprints v-else-if="section === 'blueprints'" />
      <section v-else class="admin-card admin-settings">
        <span class="admin-settings-icon"><el-icon aria-hidden="true"><Cpu /></el-icon></span>
        <div>
          <h2>全站模型配置</h2>
          <p>管理模型供应商、接口地址、API Key 与思考预算。设置会应用到所有用户的新请求。</p>
          <button ref="modelButton" class="admin-button primary" @click="modelVisible = true">打开 API 设置</button>
        </div>
        <LLMConfigDialog v-if="modelVisible" :visible="modelVisible" @update:visible="updateModelVisibility" />
      </section>
    </main>
  </div>
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Back, DataAnalysis, User, Document, Clock, Cpu, Sunny, Moon, Refresh, UserFilled, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/authStore'
import { useThemeStore } from '../stores/themeStore'
import { apiRequest, type AdminStats } from '../services/adminApi'
import '../components/admin/admin.css'

const AdminUsers = defineAsyncComponent(() => import('../components/admin/AdminUsers.vue'))
const AdminLogs = defineAsyncComponent(() => import('../components/admin/AdminLogs.vue'))
const AdminBlueprints = defineAsyncComponent(() => import('../components/admin/AdminBlueprints.vue'))
const LLMConfigDialog = defineAsyncComponent(() => import('../components/layout/LLMConfigDialog.vue'))
const auth = useAuthStore(), theme = useThemeStore(), route = useRoute(), router = useRouter()
const navigation = [{ id: 'overview', label: '运行概览', icon: DataAnalysis }, { id: 'users', label: '用户管理', icon: User },
  { id: 'logs', label: '操作记录', icon: Clock }, { id: 'blueprints', label: '蓝图管理', icon: Document }, { id: 'settings', label: 'AI API 设置', icon: Cpu }]
const section = computed(() => String(route.params.section || 'overview'))
const currentTitle = computed(() => navigation.find(item => item.id === section.value)?.label || '运行概览')
const stats = ref<AdminStats>(), error = ref(''), loading = ref(false), updatedAt = ref(''), modelVisible = ref(false)
const modelButton = ref<HTMLButtonElement>()
const metrics = computed(() => [
  { label: '用户总数', icon: User, value: stats.value?.users, hint: `正常 ${stats.value?.active_users ?? '—'} · 封禁 ${stats.value?.blocked_users ?? '—'}` },
  { label: '最近 7 天注册', icon: UserFilled, value: stats.value?.new_users_7d },
  { label: '24 小时活跃用户', icon: DataAnalysis, value: stats.value?.active_users_24h, hint: '按操作记录去重' },
  { label: '有效管理员', icon: Lock, value: stats.value?.administrators },
  { label: '蓝图总数', icon: Document, value: stats.value?.blueprints, hint: `已锁定 ${stats.value?.locked_blueprints ?? '—'} 份` },
  { label: '操作记录', icon: Clock, value: stats.value?.operations },
])
async function loadStats() {
  loading.value = true; error.value = ''
  try { stats.value = await apiRequest<AdminStats>('/api/admin/stats'); updatedAt.value = new Date().toLocaleTimeString('zh-CN') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { loading.value = false }
}
function updateModelVisibility(visible: boolean) {
  modelVisible.value = visible
  if (!visible) modelButton.value?.focus()
}
watch(section, value => {
  modelVisible.value = false
  if (value === 'overview' && !loading.value) void loadStats()
}, { immediate: true })
watch(() => auth.isAdmin, allowed => { if (!allowed) void router.replace('/') })
let refreshTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => { refreshTimer = setInterval(() => { if (!document.hidden) void auth.refresh().catch(() => {}) }, 15000) })
onBeforeUnmount(() => clearInterval(refreshTimer))
</script>
