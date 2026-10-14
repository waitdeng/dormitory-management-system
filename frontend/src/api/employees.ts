import { http } from './client'
import type {
  EmployeeCreate,
  EmployeeImportCommitOut,
  EmployeeImportPreviewOut,
  EmployeeOut,
  EmployeeUpdate,
  ImportJobOut,
  PageEnvelope,
} from '@/types'

export async function listEmployees(params: {
  page?: number
  page_size?: number
  keyword?: string
  department_id?: number
  employment_status?: string
  accommodation_status?: string
}): Promise<PageEnvelope<EmployeeOut>> {
  const { data } = await http.get<PageEnvelope<EmployeeOut>>('/api/v1/employees', { params })
  return data
}

export async function createEmployee(payload: EmployeeCreate): Promise<EmployeeOut> {
  const { data } = await http.post<EmployeeOut>('/api/v1/employees', payload)
  return data
}

export async function updateEmployee(id: number, payload: EmployeeUpdate): Promise<EmployeeOut> {
  const { data } = await http.patch<EmployeeOut>(`/api/v1/employees/${id}`, payload)
  return data
}

export async function fetchEmployee(id: number): Promise<EmployeeOut> {
  const { data } = await http.get<EmployeeOut>(`/api/v1/employees/${id}`)
  return data
}

export async function previewEmployeeImport(file: File): Promise<EmployeeImportPreviewOut> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<EmployeeImportPreviewOut>(
    '/api/v1/employees/import/preview',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
  return data
}

export async function commitEmployeeImport(importJobId: number): Promise<EmployeeImportCommitOut> {
  const { data } = await http.post<EmployeeImportCommitOut>(
    '/api/v1/employees/import/commit',
    null,
    { params: { import_job_id: importJobId } }
  )
  return data
}

export async function fetchImportJob(id: number): Promise<ImportJobOut> {
  const { data } = await http.get<ImportJobOut>(`/api/v1/imports/${id}`)
  return data
}

export async function downloadImportTemplate(): Promise<Blob> {
  const { data } = await http.get<Blob>('/api/v1/employees/import/template', {
    responseType: 'blob',
  })
  return data
}

export async function exportEmployees(params: {
  keyword?: string
  department_id?: number
  employment_status?: string
}): Promise<Blob> {
  const { data } = await http.get<Blob>('/api/v1/employees/export', {
    params,
    responseType: 'blob',
  })
  return data
}
