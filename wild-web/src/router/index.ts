import { createRouter, createWebHistory } from 'vue-router'
import WorkbenchView from '../views/WorkbenchView.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'workbench', component: WorkbenchView, meta: { title: 'WildAgent · 建筑工作台' } },
    { path: '/business-plan', name: 'business-plan', component: () => import('../views/BusinessPlanView.vue'), meta: { title: 'WILD · 旷野 | 商业计划书' } },
  ],
})

router.afterEach(to => { document.title = String(to.meta.title || 'WildAgent') })
