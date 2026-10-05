import { defineStore } from 'pinia'
import { authApi } from '@/api'
import { clearToken, setToken } from '@/api/request'

export const useUserStore = defineStore('user', {
  state: () => ({
    user: null,
    loading: false,
  }),
  getters: {
    isLogin: (state) => !!state.user,
    role: (state) => state.user?.role || '',
    isAdmin: (state) => state.user?.role === 'admin',
    isStudent: (state) => state.user?.role === 'student',
    displayName: (state) => state.user?.name || state.user?.username || '',
  },
  actions: {
    async login(payload) {
      const { data } = await authApi.login(payload)
      setToken(data.token)
      this.user = data.user
      return data.user
    },
    async register(payload) {
      const { data } = await authApi.register(payload)
      setToken(data.token)
      this.user = data.user
      return data.user
    },
    async fetchProfile() {
      this.loading = true
      try {
        const { data } = await authApi.me()
        this.user = data
        return data
      } finally {
        this.loading = false
      }
    },
    setUser(user) {
      this.user = { ...(this.user || {}), ...user }
    },
    async logout() {
      try {
        await authApi.logout()
      } catch {
        // 忽略退出接口异常
      }
      clearToken()
      this.user = null
    },
  },
})
