import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import WorkbenchView from '../views/WorkbenchView.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'workbench', component: WorkbenchView, meta: { title: 'WildAgent · 建筑工作台' } },
    { path: '/admin/:section(overview|users|logs|blueprints|settings)?', name: 'admin', component: () => import('../views/AdminView.vue'), meta: { title: 'WildAgent · 管理后台', requiresAdmin: true } },
    { path: '/business-plan', name: 'business-plan', component: () => import('../views/BusinessPlanView.vue'), meta: { title: 'WILD · 旷野 | 商业计划书' } },
  ],
})

router.beforeEach(async to => {
  if (!to.meta.requiresAdmin) return true
  const auth = useAuthStore()
  if (!auth.initialized) await auth.restore()
  else await auth.refresh().catch(() => {})
  return auth.isAdmin ? true : { path: '/' }
})

router.afterEach(to => { document.title = String(to.meta.title || 'WildAgent') })
