import { http } from './client'
import type {
  EmployeeStatusEventOut,
  NotificationOut,
  OffboardingResult,
  PageEnvelope,
  WorkflowAlertOut,
  WorkflowSummary,
  WorkflowTodoOut,
} from '@/types'

// ---- Offboarding ----

export async function startOffboarding(
  employeeId: number,
  payload: {
    reason?: string | null
    notes?: string | null
    termination_date?: string | null
    idempotency_key?: string | null
  } = {}
): Promise<OffboardingResult> {
  const { data } = await http.post<OffboardingResult>(
    `/api/v1/employees/${employeeId}/offboarding`,
    payload
  )
  return data
}

export async function terminateEmployee(
  employeeId: number,
  payload: {
    reason?: string | null
    notes?: string | null
    termination_date?: string | null
    idempotency_key?: string | null
  } = {}
): Promise<OffboardingResult> {
  const { data } = await http.post<OffboardingResult>(
    `/api/v1/employees/${employeeId}/terminate`,
    payload
  )
  return data
}

export async function listStatusEvents(
  employeeId: number
): Promise<{ items: EmployeeStatusEventOut[] }> {
  const { data } = await http.get<{ items: EmployeeStatusEventOut[] }>(
    `/api/v1/employees/${employeeId}/status-events`
  )
  return data
}

export async function listPendingOffboardingCheckouts(params: {
  page?: number
  page_size?: number
}): Promise<PageEnvelope<Record<string, unknown>>> {
  const { data } = await http.get<PageEnvelope<Record<string, unknown>>>(
    '/api/v1/offboarding/pending-checkouts',
    { params }
  )
  return data
}

// ---- Todos ----

export async function listTodos(params: {
  page?: number
  page_size?: number
  status?: string
  todo_type?: string
  business_type?: string
  employee_id?: number
  assignee_role?: string
  keyword?: string
}): Promise<PageEnvelope<WorkflowTodoOut>> {
  const { data } = await http.get<PageEnvelope<WorkflowTodoOut>>('/api/v1/workflow/todos', {
    params,
  })
  return data
}

export async function todosSummary(): Promise<WorkflowSummary> {
  const { data } = await http.get<WorkflowSummary>('/api/v1/workflow/todos/summary')
  return data
}

export async function completeTodo(id: number): Promise<WorkflowTodoOut> {
  const { data } = await http.post<WorkflowTodoOut>(`/api/v1/workflow/todos/${id}/complete`)
  return data
}

export async function cancelTodo(id: number, reason?: string): Promise<WorkflowTodoOut> {
  const { data } = await http.post<WorkflowTodoOut>(`/api/v1/workflow/todos/${id}/cancel`, null, {
    params: reason ? { reason } : undefined,
  })
  return data
}

// ---- Alerts ----

export async function listAlerts(params: {
  page?: number
  page_size?: number
  status?: string
  alert_type?: string
  employee_id?: number
  keyword?: string
}): Promise<PageEnvelope<WorkflowAlertOut>> {
  const { data } = await http.get<PageEnvelope<WorkflowAlertOut>>('/api/v1/workflow/alerts', {
    params,
  })
  return data
}

export async function alertsSummary(): Promise<WorkflowSummary> {
  const { data } = await http.get<WorkflowSummary>('/api/v1/workflow/alerts/summary')
  return data
}

export async function resolveAlert(id: number, reason?: string): Promise<WorkflowAlertOut> {
  const { data } = await http.post<WorkflowAlertOut>(
    `/api/v1/workflow/alerts/${id}/resolve`,
    null,
    { params: reason ? { reason } : undefined }
  )
  return data
}

// ---- Scanner / notifications ----

export async function runScanner(): Promise<Record<string, unknown>> {
  const { data } = await http.post<Record<string, unknown>>('/api/v1/scanner/run')
  return data
}

export async function listNotifications(params: {
  page?: number
  page_size?: number
  unread_only?: boolean
}): Promise<PageEnvelope<NotificationOut>> {
  const { data } = await http.get<PageEnvelope<NotificationOut>>(
    '/api/v1/workflow/notifications',
    { params }
  )
  return data
}
