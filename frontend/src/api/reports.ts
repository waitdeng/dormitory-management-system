import { http } from './client'
import type {
  AccommodationLedgerRow,
  CheckinCheckoutEventRow,
  DashboardOccupancyItem,
  DashboardSummary,
  DashboardTrendPoint,
  DepartmentStatRow,
  ExceptionReportRow,
  PageEnvelope,
  TransferReportRow,
  VacantBedRow,
} from '@/types'

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await http.get<DashboardSummary>('/api/v1/dashboard/summary')
  return data
}

export async function fetchDashboardOccupancy(): Promise<{ items: DashboardOccupancyItem[] }> {
  const { data } = await http.get<{ items: DashboardOccupancyItem[] }>(
    '/api/v1/dashboard/occupancy'
  )
  return data
}

export async function fetchDashboardTrends(days = 14): Promise<{ items: DashboardTrendPoint[] }> {
  const { data } = await http.get<{ items: DashboardTrendPoint[] }>('/api/v1/dashboard/trends', {
    params: { days },
  })
  return data
}

export async function fetchAccommodationLedger(params: {
  page?: number
  page_size?: number
  keyword?: string
  department_id?: number
  building_id?: number
}): Promise<PageEnvelope<AccommodationLedgerRow>> {
  const { data } = await http.get<PageEnvelope<AccommodationLedgerRow>>(
    '/api/v1/reports/accommodations',
    { params }
  )
  return data
}

export async function fetchVacantBeds(params: {
  page?: number
  page_size?: number
  building_id?: number
  floor_id?: number
}): Promise<PageEnvelope<VacantBedRow>> {
  const { data } = await http.get<PageEnvelope<VacantBedRow>>('/api/v1/reports/vacant-beds', {
    params,
  })
  return data
}

export async function fetchDepartmentStats(params: {
  page?: number
  page_size?: number
}): Promise<PageEnvelope<DepartmentStatRow>> {
  const { data } = await http.get<PageEnvelope<DepartmentStatRow>>('/api/v1/reports/departments', {
    params,
  })
  return data
}

export async function fetchCheckinCheckoutReport(params: {
  page?: number
  page_size?: number
  date_from?: string
  date_to?: string
  event_type?: string
}): Promise<PageEnvelope<CheckinCheckoutEventRow>> {
  const { data } = await http.get<PageEnvelope<CheckinCheckoutEventRow>>(
    '/api/v1/reports/checkin-checkout',
    { params }
  )
  return data
}

export async function fetchTransferReport(params: {
  page?: number
  page_size?: number
  status?: string
}): Promise<PageEnvelope<TransferReportRow>> {
  const { data } = await http.get<PageEnvelope<TransferReportRow>>('/api/v1/reports/transfers', {
    params,
  })
  return data
}

export async function fetchExceptionReport(params: {
  page?: number
  page_size?: number
  status?: string
  alert_type?: string
}): Promise<PageEnvelope<ExceptionReportRow>> {
  const { data } = await http.get<PageEnvelope<ExceptionReportRow>>('/api/v1/reports/exceptions', {
    params,
  })
  return data
}

export async function exportReport(
  reportType: string,
  params: Record<string, string | number | undefined> = {}
): Promise<Blob> {
  const { data } = await http.get<Blob>(`/api/v1/reports/${reportType}/export`, {
    params,
    responseType: 'blob',
  })
  return data
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
