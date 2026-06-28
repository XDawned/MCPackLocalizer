import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import { resolveWorkflowStepByPath, useWorkflowStore } from '@/stores/workflow'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { title: '首页' }
    },
    {
      path: '/search',
      name: 'search',
      component: () => import('../views/SearchView.vue'),
      meta: { title: '检索整合包', workflowStep: 1 }
    },
    {
      path: '/modpack/:platform/:id',
      name: 'modpackDetail',
      component: () => import('../views/ModpackDetailView.vue'),
      meta: { title: '整合包详情' }
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('../views/HistoryView.vue'),
      meta: { title: '处理历史' }
    },
    {
      path: '/l10n-config',
      name: 'l10nConfig',
      component: () => import('../views/TranslateConfigView.vue'),
      meta: { title: '翻译配置', workflowStep: 2 }
    },
    {
      path: '/translating',
      name: 'translating',
      component: () => import('../views/TranslateProgressView.vue'),
      meta: { title: '翻译进度', workflowStep: 3 }
    },
    {
      path: '/apply',
      name: 'apply',
      component: () => import('../views/ApplyView.vue'),
      meta: { title: '汉化应用', workflowStep: 4 }
    },
    {
      path: '/translation-review',
      name: 'translationReview',
      component: () => import('../views/FeedbackView.vue'),
      meta: { title: '翻译效果确认', workflowStep: 5 }
    },
    {
      path: '/workflow',
      name: 'workflow',
      component: () => import('../views/WorkflowView.vue'),
      meta: { title: '本地化工作流' }
    },
    {
      path: '/glossary',
      name: 'glossary',
      component: () => import('../views/GlossaryView.vue'),
      meta: { title: '术语库管理' }
    },
    {
      path: '/settings',
      name: 'settings',
      redirect: '/settings/general',
      meta: { title: '系统设置' }
    },
    {
      path: '/settings/general',
      name: 'settingsGeneral',
      component: () => import('../views/SettingsView.vue'),
      meta: { title: '通用设置' }
    },
    {
      path: '/settings/cache',
      name: 'settingsCache',
      component: () => import('../views/SettingsView.vue'),
      meta: { title: '缓存设置' }
    },
    {
      path: '/cache-config',
      redirect: '/settings/cache'
    },
    {
      path: '/local-import',
      name: 'localImport',
      component: () => import('../views/LocalImportView.vue'),
      meta: { title: '本地整合包导入', workflowStep: 1 }
    }
  ]
})

router.beforeEach((to, from, next) => {
  const workflowStore = useWorkflowStore()
  workflowStore.syncRouteContext(to)

  const workflowStep = resolveWorkflowStepByPath(to.path)
  if (!workflowStep) {
    next()
    return
  }

  const validation = workflowStore.validateStepAccess(workflowStep, to.query)
  if (!validation.allowed) {
    next(validation.redirect)
    return
  }

  next()
})

export default router
