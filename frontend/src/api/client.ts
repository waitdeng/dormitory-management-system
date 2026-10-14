import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiError } from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

const ACCESS_KEY = 'dms_access_token'
const REFRESH_KEY = 'dms_refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const requestId = crypto.randomUUID().replaceAll('-', '')
  config.headers['X-Request-Id'] = requestId
  return config
})

let isRefreshing = false
let pendingQueue: Array<(token: string | null) => void> = []

function flushPending(token: string | null): void {
  pendingQueue.forEach((cb) => cb(token))
  pendingQueue = []
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    const status = error.response?.status

    if (status === 401 && original && !original._retry) {
      original._retry = true
      const refresh = getRefreshToken()
      if (refresh && !isRefreshing) {
        isRefreshing = true
        try {
          const resp = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, { refresh_token: refresh })
          const data = resp.data
          setTokens(data.access_token, data.refresh_token)
          flushPending(data.access_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return http(original)
        } catch {
          clearTokens()
          flushPending(null)
          window.location.href = '/login'
          return Promise.reject(error)
        } finally {
          isRefreshing = false
        }
      } else if (isRefreshing && refresh) {
        return new Promise((resolve) => {
          pendingQueue.push((token) => {
            if (token && original) {
              original.headers.Authorization = `Bearer ${token}`
              resolve(http(original))
            } else {
              resolve(Promise.reject(error))
            }
          })
        })
      } else {
        clearTokens()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
      }
    }

    const apiError = error.response?.data
    const message = apiError?.message || error.message || '请求失败'
    if (status !== 401) {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  },
)

export function extractError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.message || error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}
