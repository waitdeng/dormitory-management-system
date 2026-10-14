import { http } from './client'
import type { PageEnvelope, PermissionOut, RoleOut, UserCreate, UserOut, UserUpdate } from '@/types'

export async function listUsers(params: {
  page?: number
  page_size?: number
  keyword?: string
  status?: string
}): Promise<PageEnvelope<UserOut>> {
  const { data } = await http.get<PageEnvelope<UserOut>>('/api/v1/users', { params })
  return data
}

export async function createUser(payload: UserCreate): Promise<UserOut> {
  const { data } = await http.post<UserOut>('/api/v1/users', payload)
  return data
}

export async function updateUser(id: number, payload: UserUpdate): Promise<UserOut> {
  const { data } = await http.patch<UserOut>(`/api/v1/users/${id}`, payload)
  return data
}

export async function setUserRoles(id: number, roleCodes: string[]): Promise<UserOut> {
  const { data } = await http.put<UserOut>(`/api/v1/users/${id}/roles`, { role_codes: roleCodes })
  return data
}

export async function listRoles(): Promise<RoleOut[]> {
  const { data } = await http.get<RoleOut[]>('/api/v1/roles')
  return data
}

export async function listPermissions(): Promise<PermissionOut[]> {
  const { data } = await http.get<PermissionOut[]>('/api/v1/permissions')
  return data
}
