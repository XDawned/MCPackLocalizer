/**
 * Vue Router 配置
 */
import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'home',
    redirect: '/work'
  },
  {
    path: '/work',
    name: 'work',
    component: () => import('@/components/work/WorkInterface.vue'),
    meta: {
      title: '工作台'
    }
  },
  {
    path: '/extract',
    name: 'extract',
    component: () => import('@/components/extract/ModpackExtractInterface.vue'),
    meta: {
      title: '整合包提取'
    }
  },
  {
    path: '/resourcepack',
    name: 'resourcepack',
    component: () => import('@/components/resourcepack/GenerateResourcepackInterface.vue'),
    meta: {
      title: '生成资源包'
    }
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/components/settings/SettingInterface.vue'),
    meta: {
      title: '设置'
    }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - 整合包本地化工具`
  }
  next()
})

export default router