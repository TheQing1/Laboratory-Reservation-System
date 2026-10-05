import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from '@/api/request'
import { useUserStore } from '@/store/user'

const MainLayout = () => import('@/layout/MainLayout.vue')

export const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { title: '注册', public: true },
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '首页概览', icon: 'HomeFilled' },
      },
      {
        path: 'labs',
        name: 'LabList',
        component: () => import('@/views/lab/LabList.vue'),
        meta: { title: '实验室', icon: 'OfficeBuilding' },
      },
      {
        path: 'labs/:id',
        name: 'LabDetail',
        component: () => import('@/views/lab/LabDetail.vue'),
        meta: { title: '实验室详情', hidden: true, activeMenu: '/labs' },
      },
      {
        path: 'labs/manage',
        name: 'LabManage',
        component: () => import('@/views/lab/LabManage.vue'),
        meta: { title: '实验室管理', icon: 'Management', roles: ['admin'] },
      },
      {
        path: 'equipments',
        name: 'EquipmentManage',
        component: () => import('@/views/equipment/EquipmentManage.vue'),
        meta: { title: '设备管理', icon: 'Cpu', roles: ['admin'] },
      },
      {
        path: 'booking',
        name: 'Booking',
        component: () => import('@/views/reservation/Booking.vue'),
        meta: { title: '我要预约', icon: 'Calendar', roles: ['student'] },
      },
      {
        path: 'my-reservations',
        name: 'MyReservations',
        component: () => import('@/views/reservation/MyReservations.vue'),
        meta: { title: '我的预约', icon: 'Tickets', roles: ['student'] },
      },
      {
        path: 'review',
        name: 'Review',
        component: () => import('@/views/reservation/ReviewList.vue'),
        meta: { title: '预约审核', icon: 'Checked', roles: ['admin'] },
      },
      {
        path: 'ai-assistant',
        name: 'AiAssistant',
        component: () => import('@/views/ai/AiAssistant.vue'),
        meta: { title: 'AI 智能助手', icon: 'MagicStick' },
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/knowledge/KnowledgeManage.vue'),
        meta: { title: '知识库管理', icon: 'Notebook', roles: ['admin'] },
      },
      {
        path: 'users',
        name: 'UserManage',
        component: () => import('@/views/user/UserManage.vue'),
        meta: { title: '用户管理', icon: 'UserFilled', roles: ['admin'] },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: '个人中心', icon: 'User', hidden: true },
      },
    ],
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/error/403.vue'),
    meta: { title: '无权访问', public: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在', public: true },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智能实验室预约系统` : '智能实验室预约系统'

  const hasToken = !!getToken()
  if (to.meta.public) {
    // 已登录用户访问登录页直接回首页
    if (hasToken && (to.name === 'Login' || to.name === 'Register')) {
      return { path: '/dashboard' }
    }
    return true
  }

  if (!hasToken) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  const userStore = useUserStore()
  if (!userStore.user) {
    try {
      await userStore.fetchProfile()
    } catch {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  // 角色校验
  const roles = to.meta.roles
  if (roles && roles.length && !roles.includes(userStore.role)) {
    return { path: '/403' }
  }
  return true
})

export default router
