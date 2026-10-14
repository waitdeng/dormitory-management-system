import { http } from './client'
import type { LoginRequest, MeResponse, TokenResponse } from '@/types'

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>('/api/v1/auth/login', payload)
  return data
}

export async function logout(refreshToken?: string | null): Promise<void> {
  await http.post('/api/v1/auth/logout', { refresh_token: refreshToken ?? null })
}

export async function fetchMe(): Promise<MeResponse> {
  const { data } = await http.get<MeResponse>('/api/v1/auth/me')
  return data
}

export async function fetchMyPermissions(): Promise<{ roles: string[]; permissions: string[] }> {
  const { data } = await http.get<{ roles: string[]; permissions: string[] }>(
    '/api/v1/auth/permissions',
  )
  return data
}
