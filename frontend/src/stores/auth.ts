import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchMe, login as apiLogin, logout as apiLogout } from '@/api/auth'
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from '@/api/client'
import type { LoginRequest } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(getAccessToken())
  const refreshToken = ref<string | null>(getRefreshToken())
  const userId = ref<number | null>(null)
  const username = ref('')
  const displayName = ref('')
  const roles = ref<string[]>([])
  const permissions = ref<string[]>([])
  const loaded = ref(false)

  const isAuthenticated = computed(() => Boolean(accessToken.value))

  function hasPermission(code: string): boolean {
    return permissions.value.includes(code)
  }

  function hasAnyPermission(...codes: string[]): boolean {
    return codes.some((c) => permissions.value.includes(c))
  }

  async function login(payload: LoginRequest): Promise<void> {
    const data = await apiLogin(payload)
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    userId.value = data.user_id
    username.value = data.username
    displayName.value = data.display_name
    roles.value = data.roles
    permissions.value = data.permissions
    loaded.value = true
    setTokens(data.access_token, data.refresh_token)
  }

  async function loadProfile(): Promise<void> {
    if (!accessToken.value) return
    const me = await fetchMe()
    userId.value = me.id
    username.value = me.username
    displayName.value = me.display_name
    roles.value = me.roles
    permissions.value = me.permissions
    loaded.value = true
  }

  async function logout(): Promise<void> {
    try {
      await apiLogout(refreshToken.value)
    } catch {
      // ignore network errors on logout
    } finally {
      accessToken.value = null
      refreshToken.value = null
      userId.value = null
      username.value = ''
      displayName.value = ''
      roles.value = []
      permissions.value = []
      loaded.value = false
      clearTokens()
    }
  }

  return {
    accessToken,
    refreshToken,
    userId,
    username,
    displayName,
    roles,
    permissions,
    loaded,
    isAuthenticated,
    hasPermission,
    hasAnyPermission,
    login,
    loadProfile,
    logout,
  }
})
