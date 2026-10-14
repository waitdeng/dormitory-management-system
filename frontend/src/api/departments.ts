import { http } from './client'
import type {
  DepartmentCreate,
  DepartmentOut,
  DepartmentTreeNode,
  DepartmentUpdate,
  PageEnvelope,
} from '@/types'

export async function listDepartments(params: {
  page?: number
  page_size?: number
  keyword?: string
  status?: string
  parent_id?: number
}): Promise<PageEnvelope<DepartmentOut>> {
  const { data } = await http.get<PageEnvelope<DepartmentOut>>('/api/v1/departments', { params })
  return data
}

export async function fetchDepartmentTree(includeDisabled = false): Promise<DepartmentTreeNode[]> {
  const { data } = await http.get<DepartmentTreeNode[]>('/api/v1/departments/tree', {
    params: { include_disabled: includeDisabled },
  })
  return data
}

export async function createDepartment(payload: DepartmentCreate): Promise<DepartmentOut> {
  const { data } = await http.post<DepartmentOut>('/api/v1/departments', payload)
  return data
}

export async function updateDepartment(
  id: number,
  payload: DepartmentUpdate
): Promise<DepartmentOut> {
  const { data } = await http.patch<DepartmentOut>(`/api/v1/departments/${id}`, payload)
  return data
}
