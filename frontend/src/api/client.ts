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

export type RequestConfigExtras = {
  /** When true, the global interceptor will not toast — the caller owns messaging. */
  skipErrorToast?: boolean
  _retry?: boolean
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as (InternalAxiosRequestConfig & RequestConfigExtras) | undefined
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

    const message = await extractErrorAsync(error)
    const skipToast = original?.skipErrorToast === true
    if (status !== 401 && !skipToast) {
      ElMessage.error(message)
      markToasted(error)
    }
    return Promise.reject(error)
  },
)

type ToastedError = { __dmsToasted?: boolean }

function markToasted(error: unknown): void {
  if (typeof error === 'object' && error !== null) {
    ;(error as ToastedError).__dmsToasted = true
  }
}

export function wasToasted(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    (error as ToastedError).__dmsToasted === true
  )
}

/** Toast once per failure. If the global interceptor already notified, this is a no-op. */
export function notifyError(error: unknown, fallback?: string): void {
  if (wasToasted(error)) return
  ElMessage.error(fallback ?? extractError(error))
}

function isApiErrorBody(value: unknown): value is ApiError {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as ApiError).message === 'string'
  )
}

async function extractErrorAsync(error: unknown): Promise<string> {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    if (isApiErrorBody(data)) return data.message
    // Blob / ArrayBuffer error bodies (export downloads)
    if (data instanceof Blob) {
      try {
        const parsed = JSON.parse(await data.text())
        if (isApiErrorBody(parsed)) return parsed.message
      } catch {
        /* fall through */
      }
    }
    return error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}

export function extractError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    if (isApiErrorBody(data)) return data.message
    return error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}


declare module 'axios' {
  export interface AxiosRequestConfig {
    /** Skip the global error toast — caller owns messaging. */
    skipErrorToast?: boolean
  }
}
