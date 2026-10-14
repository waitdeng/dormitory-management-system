import { http } from './client'
import type {
  AccommodationRecordOut,
  CheckinApplicationCreate,
  CheckinApplicationOut,
  CheckoutCreate,
  CheckoutRecordOut,
  PageEnvelope,
  TransferCreate,
  TransferRecordOut,
} from '@/types'

// ---- Check-in applications ----

export async function listCheckinApplications(params: {
  page?: number
  page_size?: number
  status?: string
  employee_id?: number
  keyword?: string
}): Promise<PageEnvelope<CheckinApplicationOut>> {
  const { data } = await http.get<PageEnvelope<CheckinApplicationOut>>(
    '/api/v1/checkin-applications',
    { params }
  )
  return data
}

export async function createCheckinApplication(
  payload: CheckinApplicationCreate
): Promise<CheckinApplicationOut> {
  const { data } = await http.post<CheckinApplicationOut>(
    '/api/v1/checkin-applications',
    payload
  )
  return data
}

export async function fetchCheckinApplication(
  id: number
): Promise<CheckinApplicationOut> {
  const { data } = await http.get<CheckinApplicationOut>(`/api/v1/checkin-applications/${id}`)
  return data
}

export async function approveCheckinApplication(id: number): Promise<CheckinApplicationOut> {
  const { data } = await http.post<CheckinApplicationOut>(
    `/api/v1/checkin-applications/${id}/approve`,
    {}
  )
  return data
}

export async function rejectCheckinApplication(
  id: number,
  reason?: string
): Promise<CheckinApplicationOut> {
  const { data } = await http.post<CheckinApplicationOut>(
    `/api/v1/checkin-applications/${id}/reject`,
    { reason }
  )
  return data
}

export async function reserveCheckinBed(
  id: number,
  bedId: number
): Promise<CheckinApplicationOut> {
  const { data } = await http.post<CheckinApplicationOut>(
    `/api/v1/checkin-applications/${id}/reserve`,
    { bed_id: bedId }
  )
  return data
}

export async function confirmCheckin(id: number): Promise<CheckinApplicationOut> {
  const { data } = await http.post<CheckinApplicationOut>(
    `/api/v1/checkin-applications/${id}/confirm`,
    {}
  )
  return data
}

export async function cancelCheckinApplication(
  id: number,
  reason?: string
): Promise<CheckinApplicationOut> {
  const { data } = await http.post<CheckinApplicationOut>(
    `/api/v1/checkin-applications/${id}/cancel`,
    { reason }
  )
  return data
}

// ---- Accommodations ----

export async function listActiveAccommodations(params: {
  page?: number
  page_size?: number
  employee_id?: number
  bed_id?: number
  building_id?: number
}): Promise<PageEnvelope<AccommodationRecordOut>> {
  const { data } = await http.get<PageEnvelope<AccommodationRecordOut>>(
    '/api/v1/accommodations/active',
    { params }
  )
  return data
}

export async function listAccommodationHistory(params: {
  page?: number
  page_size?: number
  employee_id?: number
  include_active?: boolean
}): Promise<PageEnvelope<AccommodationRecordOut>> {
  const { data } = await http.get<PageEnvelope<AccommodationRecordOut>>(
    '/api/v1/accommodations/history',
    { params }
  )
  return data
}

// ---- Transfers ----

export async function listTransfers(params: {
  page?: number
  page_size?: number
  status?: string
  employee_id?: number
  keyword?: string
}): Promise<PageEnvelope<TransferRecordOut>> {
  const { data } = await http.get<PageEnvelope<TransferRecordOut>>('/api/v1/transfers', {
    params,
  })
  return data
}

export async function createTransfer(payload: TransferCreate): Promise<TransferRecordOut> {
  const { data } = await http.post<TransferRecordOut>('/api/v1/transfers', payload)
  return data
}

export async function reserveTransferTarget(
  id: number,
  targetBedId?: number
): Promise<TransferRecordOut> {
  const { data } = await http.post<TransferRecordOut>(`/api/v1/transfers/${id}/reserve`, {
    target_bed_id: targetBedId,
  })
  return data
}

export async function completeTransfer(id: number): Promise<TransferRecordOut> {
  const { data } = await http.post<TransferRecordOut>(`/api/v1/transfers/${id}/complete`, {})
  return data
}

export async function cancelTransfer(
  id: number,
  reason?: string
): Promise<TransferRecordOut> {
  const { data } = await http.post<TransferRecordOut>(`/api/v1/transfers/${id}/cancel`, {
    reason,
  })
  return data
}

// ---- Checkouts ----

export async function listCheckouts(params: {
  page?: number
  page_size?: number
  status?: string
  employee_id?: number
  keyword?: string
}): Promise<PageEnvelope<CheckoutRecordOut>> {
  const { data } = await http.get<PageEnvelope<CheckoutRecordOut>>('/api/v1/checkouts', {
    params,
  })
  return data
}

export async function createCheckout(payload: CheckoutCreate): Promise<CheckoutRecordOut> {
  const { data } = await http.post<CheckoutRecordOut>('/api/v1/checkouts', payload)
  return data
}

export async function recordCheckoutInspection(
  id: number,
  payload: {
    key_returned?: boolean
    access_card_returned?: boolean
    belongings_cleared?: boolean
    room_inspected?: boolean
    inspection_notes?: string
  }
): Promise<CheckoutRecordOut> {
  const { data } = await http.patch<CheckoutRecordOut>(
    `/api/v1/checkouts/${id}/inspection`,
    payload
  )
  return data
}

export async function completeCheckout(id: number): Promise<CheckoutRecordOut> {
  const { data } = await http.post<CheckoutRecordOut>(`/api/v1/checkouts/${id}/complete`, {})
  return data
}

export async function cancelCheckout(
  id: number,
  reason?: string
): Promise<CheckoutRecordOut> {
  const { data } = await http.post<CheckoutRecordOut>(`/api/v1/checkouts/${id}/cancel`, {
    reason,
  })
  return data
}
