import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/Home.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/Login.vue'),
      meta: { public: true }
    },
    {
      path: '/setup',
      name: 'setup',
      component: () => import('@/views/Setup.vue'),
      meta: { public: true }
    },
    {
      path: '/wrong-questions',
      name: 'wrong-questions',
      component: () => import('@/views/WrongQuestions.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/plans',
      name: 'plans',
      component: () => import('@/views/Plans.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/todos',
      name: 'todos',
      component: () => import('@/views/Todos.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/study',
      name: 'study',
      component: () => import('@/views/Study.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/Settings.vue'),
      meta: { requiresAuth: true }
    }
  ]
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  // 已登录但还没拿到用户信息
  if (to.meta.requiresAuth && !auth.user) {
    const ok = await auth.fetchMe()
    if (!ok) return { name: 'login' }
  }
  // 公共页：检查初始化状态
  if (to.name === 'login') {
    const initialized = await auth.fetchSetupStatus()
    if (!initialized) return { name: 'setup' }
  }
})
