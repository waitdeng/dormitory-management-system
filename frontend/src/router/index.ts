import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/login/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/dashboard/DashboardView.vue'),
        meta: { title: '首页概览', permission: null },
      },
      {
        path: 'employees',
        name: 'employees',
        component: () => import('@/views/employees/EmployeesView.vue'),
        meta: { title: '员工管理', permission: 'employee:view' },
      },
      {
        path: 'dormitories',
        name: 'dormitories',
        component: () => import('@/views/dormitories/DormitoriesView.vue'),
        meta: { title: '宿舍资源', permission: 'dorm:view' },
      },
      {
        path: 'checkins',
        name: 'checkins',
        component: () => import('@/views/checkins/CheckinsView.vue'),
        meta: { title: '入住管理', permission: 'checkin:view' },
      },
      {
        path: 'transfers',
        name: 'transfers',
        component: () => import('@/views/transfers/TransfersView.vue'),
        meta: { title: '调宿管理', permission: 'transfer:view' },
      },
      {
        path: 'checkouts',
        name: 'checkouts',
        component: () => import('@/views/checkouts/CheckoutsView.vue'),
        meta: { title: '退宿管理', permission: 'checkout:view' },
      },
      {
        path: 'todos',
        name: 'todos',
        component: () => import('@/views/todos/TodosView.vue'),
        meta: { title: '待办中心', permission: null },
      },
      {
        path: 'bed-allocation',
        name: 'bed-allocation',
        component: () => import('@/views/allocation/BedAllocationView.vue'),
        meta: { title: '可视化分床', permission: 'dorm:view' },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/reports/ReportsView.vue'),
        meta: { title: '统计报表', permission: 'report:view' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/settings/UsersView.vue'),
        meta: { title: '系统设置', permission: 'user:manage' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (!auth.loaded) {
    try {
      await auth.loadProfile()
    } catch {
      await auth.logout()
      return { name: 'login' }
    }
  }

  const required = to.meta.permission as string | null | undefined
  if (required && !auth.hasPermission(required)) {
    return { name: 'dashboard' }
  }

  return true
})
