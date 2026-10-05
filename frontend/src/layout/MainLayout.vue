<template>
  <el-container class="layout">
    <!-- 侧边栏 -->
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo" @click="router.push('/dashboard')">
        <span class="logo-icon">🔬</span>
        <span v-show="!collapsed" class="logo-text">智能实验室预约</span>
      </div>
      <el-scrollbar>
        <el-menu
          :default-active="activeMenu"
          :collapse="collapsed"
          :collapse-transition="false"
          background-color="#1f2d3d"
          text-color="#bfcbd9"
          active-text-color="#ffffff"
          router
        >
          <template v-for="item in menuItems" :key="item.path">
            <el-menu-item :index="item.path">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title>{{ item.title }}</template>
            </el-menu-item>
          </template>
          <el-sub-menu v-if="adminItems.length" index="admin-group">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item v-for="item in adminItems" :key="item.path" :index="item.path">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title>{{ item.title }}</template>
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-scrollbar>
      <div v-show="!collapsed" class="sidebar-footer">
        <div class="mode-tag" :class="aiMode === 'llm' ? 'is-llm' : 'is-local'">
          <el-icon><component :is="aiMode === 'llm' ? 'Cpu' : 'Monitor'" /></el-icon>
          <span>{{ aiModeText }}</span>
        </div>
      </div>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="collapsed = !collapsed">
            <component :is="collapsed ? 'Expand' : 'Fold'" />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentTitle">{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tooltip content="AI 智能助手" placement="bottom">
            <el-button circle :icon="MagicStick" @click="router.push('/ai-assistant')" />
          </el-tooltip>
          <el-badge :value="pendingCount" :hidden="!pendingCount" class="badge">
            <el-tooltip :content="isAdmin ? '待审核预约' : '待处理预约'" placement="bottom">
              <el-button
                circle
                :icon="Bell"
                @click="router.push(isAdmin ? '/review' : '/my-reservations')"
              />
            </el-tooltip>
          </el-badge>
          <el-dropdown @command="onCommand">
            <div class="user-info">
              <el-avatar :size="30" :src="userStore.user?.avatar || ''">
                {{ userStore.displayName.charAt(0) }}
              </el-avatar>
              <span class="username">{{ userStore.displayName }}</span>
              <el-tag size="small" :type="userStore.isAdmin ? 'danger' : 'success'" effect="plain">
                {{ userStore.user?.role_text }}
              </el-tag>
              <el-icon><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile" :icon="User">个人中心</el-dropdown-item>
                <el-dropdown-item command="ai" :icon="MagicStick">AI 助手</el-dropdown-item>
                <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Bell, MagicStick, SwitchButton, User } from '@element-plus/icons-vue'
import { routes } from '@/router'
import { useUserStore } from '@/store/user'
import { dashboardApi, reservationApi } from '@/api'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const collapsed = ref(false)
const pendingCount = ref(0)
const aiMode = ref('local')
const aiModeText = ref('本地助手模式')

const isAdmin = computed(() => userStore.isAdmin)

// 顶部/管理菜单分组
const allChildren = computed(() => {
  const layout = routes.find((r) => r.path === '/')
  return (layout?.children || []).filter((c) => !c.meta?.hidden)
})

const visibleItems = computed(() =>
  allChildren.value.filter((item) => {
    const roles = item.meta?.roles
    if (!roles || !roles.length) return true
    return roles.includes(userStore.role)
  })
)

const ADMIN_PATHS = ['labs/manage', 'equipments', 'review', 'knowledge', 'users']

const menuItems = computed(() =>
  visibleItems.value
    .filter((i) => !ADMIN_PATHS.includes(i.path))
    .map((i) => ({ path: `/${i.path}`, title: i.meta.title, icon: i.meta.icon }))
)

const adminItems = computed(() =>
  visibleItems.value
    .filter((i) => ADMIN_PATHS.includes(i.path))
    .map((i) => ({ path: `/${i.path}`, title: i.meta.title, icon: i.meta.icon }))
)

const activeMenu = computed(() => route.meta?.activeMenu || route.path)
const currentTitle = computed(() => route.meta?.title)

async function loadBadge() {
  try {
    const { data } = await reservationApi.stats()
    pendingCount.value = isAdmin.value ? data.pending : data.pending
  } catch {
    pendingCount.value = 0
  }
}

async function loadAiMode() {
  try {
    const { data } = await dashboardApi.aiStatus()
    aiMode.value = data.mode
    aiModeText.value = data.mode_text
  } catch {
    aiMode.value = 'local'
    aiModeText.value = '本地助手模式'
  }
}

async function onCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'ai') {
    router.push('/ai-assistant')
  } else if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
        type: 'warning',
        confirmButtonText: '退出',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
    await userStore.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  }
}

onMounted(() => {
  loadBadge()
  loadAiMode()
})
</script>

<style scoped>
.layout {
  height: 100vh;
}

.sidebar {
  background: #1f2d3d;
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease;
  overflow: hidden;
}

.logo {
  height: 58px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logo-icon {
  font-size: 20px;
}

.sidebar :deep(.el-menu) {
  border-right: none;
}

.sidebar :deep(.el-menu-item.is-active) {
  background: #409eff !important;
}

.sidebar-footer {
  margin-top: auto;
  padding: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.mode-tag {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  padding: 6px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

.mode-tag.is-llm {
  color: #67c23a;
  background: rgba(103, 194, 58, 0.12);
}

.mode-tag.is-local {
  color: #e6a23c;
  background: rgba(230, 162, 60, 0.12);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e8eaec;
  height: 58px;
  padding: 0 18px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.collapse-btn {
  font-size: 19px;
  cursor: pointer;
  color: #5a5e66;
}

.collapse-btn:hover {
  color: #409eff;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.badge :deep(.el-badge__content) {
  border: none;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  outline: none;
}

.user-info:hover {
  background: #f5f7fa;
}

.username {
  font-size: 14px;
  color: #303133;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.main {
  background: #f0f2f5;
  padding: 0;
  overflow-y: auto;
}
</style>
