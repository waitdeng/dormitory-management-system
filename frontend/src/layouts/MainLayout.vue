<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const menuItems = computed(() => {
  const items: Array<{ path: string; title: string; icon: string; show: boolean }> = [
    { path: '/dashboard', title: '首页概览', icon: 'Odometer', show: true },
    { path: '/employees', title: '员工管理', icon: 'User', show: auth.hasPermission('employee:view') },
    { path: '/dormitories', title: '宿舍资源', icon: 'OfficeBuilding', show: auth.hasPermission('dorm:view') },
    { path: '/bed-allocation', title: '可视化分床', icon: 'Grid', show: auth.hasPermission('dorm:view') },
    { path: '/checkins', title: '入住管理', icon: 'Key', show: auth.hasPermission('checkin:view') },
    { path: '/transfers', title: '调宿管理', icon: 'Switch', show: auth.hasPermission('transfer:view') },
    { path: '/checkouts', title: '退宿管理', icon: 'Finished', show: auth.hasPermission('checkout:view') },
    { path: '/todos', title: '待办中心', icon: 'Bell', show: true },
    { path: '/reports', title: '统计报表', icon: 'DataAnalysis', show: auth.hasPermission('report:view') },
    { path: '/settings', title: '系统设置', icon: 'Setting', show: auth.hasPermission('user:manage') },
  ]
  return items.filter((i) => i.show)
})

async function handleLogout(): Promise<void> {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    type: 'warning',
    confirmButtonText: '退出',
    cancelButtonText: '取消',
  })
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="sidebar">
      <div class="brand">
        <el-icon :size="22"><OfficeBuilding /></el-icon>
        <span class="brand-title">宿舍入住管理</span>
      </div>
      <el-menu
        :default-active="route.path"
        class="sidebar-menu"
        background-color="#1f2d3d"
        text-color="#bfcbd9"
        active-text-color="#ffffff"
        router
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">{{ (route.meta.title as string) || '首页' }}</div>
        <div class="header-user">
          <el-dropdown @command="(cmd: string) => (cmd === 'logout' ? handleLogout() : undefined)">
            <span class="user-chip">
              <el-icon><UserFilled /></el-icon>
              {{ auth.displayName || auth.username }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  角色：{{ auth.roles.join('、') || '—' }}
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100vh;
}

.sidebar {
  background: #1f2d3d;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  height: 56px;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #606266;
  outline: none;
}

.main {
  padding: 20px;
  overflow: auto;
}
</style>
