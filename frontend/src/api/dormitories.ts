import { http } from './client'
import type {
  BedCreate,
  BedOut,
  BuildingCreate,
  BuildingOut,
  BuildingUpdate,
  DormAreaCreate,
  DormAreaOut,
  DormAreaUpdate,
  DormTreeNode,
  FloorCreate,
  FloorOut,
  FloorUpdate,
  PageEnvelope,
  RoomCreate,
  RoomOut,
  RoomUpdate,
} from '@/types'

export async function listAreas(params: {
  page?: number
  page_size?: number
  keyword?: string
  status?: string
}): Promise<PageEnvelope<DormAreaOut>> {
  const { data } = await http.get<PageEnvelope<DormAreaOut>>('/api/v1/dorm-areas', { params })
  return data
}

export async function createArea(payload: DormAreaCreate): Promise<DormAreaOut> {
  const { data } = await http.post<DormAreaOut>('/api/v1/dorm-areas', payload)
  return data
}

export async function updateArea(id: number, payload: DormAreaUpdate): Promise<DormAreaOut> {
  const { data } = await http.patch<DormAreaOut>(`/api/v1/dorm-areas/${id}`, payload)
  return data
}

export async function listBuildings(params: {
  page?: number
  page_size?: number
  area_id?: number
  keyword?: string
  status?: string
}): Promise<PageEnvelope<BuildingOut>> {
  const { data } = await http.get<PageEnvelope<BuildingOut>>('/api/v1/buildings', { params })
  return data
}

export async function createBuilding(payload: BuildingCreate): Promise<BuildingOut> {
  const { data } = await http.post<BuildingOut>('/api/v1/buildings', payload)
  return data
}

export async function updateBuilding(id: number, payload: BuildingUpdate): Promise<BuildingOut> {
  const { data } = await http.patch<BuildingOut>(`/api/v1/buildings/${id}`, payload)
  return data
}

export async function listFloors(
  buildingId: number,
  params: { page?: number; page_size?: number; status?: string } = {}
): Promise<PageEnvelope<FloorOut>> {
  const { data } = await http.get<PageEnvelope<FloorOut>>(
    `/api/v1/buildings/${buildingId}/floors`,
    { params }
  )
  return data
}

export async function createFloor(payload: FloorCreate): Promise<FloorOut> {
  const { data } = await http.post<FloorOut>('/api/v1/floors', payload)
  return data
}

export async function updateFloor(id: number, payload: FloorUpdate): Promise<FloorOut> {
  const { data } = await http.patch<FloorOut>(`/api/v1/floors/${id}`, payload)
  return data
}

export async function listRooms(params: {
  page?: number
  page_size?: number
  floor_id?: number
  building_id?: number
  keyword?: string
  status?: string
}): Promise<PageEnvelope<RoomOut>> {
  const { data } = await http.get<PageEnvelope<RoomOut>>('/api/v1/rooms', { params })
  return data
}

export async function createRoom(payload: RoomCreate): Promise<RoomOut> {
  const { data } = await http.post<RoomOut>('/api/v1/rooms', payload)
  return data
}

export async function updateRoom(id: number, payload: RoomUpdate): Promise<RoomOut> {
  const { data } = await http.patch<RoomOut>(`/api/v1/rooms/${id}`, payload)
  return data
}

export async function fetchRoom(id: number): Promise<RoomOut> {
  const { data } = await http.get<RoomOut>(`/api/v1/rooms/${id}`)
  return data
}

export async function listRoomBeds(roomId: number, status?: string): Promise<BedOut[]> {
  const { data } = await http.get<BedOut[]>(`/api/v1/rooms/${roomId}/beds`, {
    params: status ? { status } : undefined,
  })
  return data
}

export async function createBed(roomId: number, payload: Omit<BedCreate, 'room_id'>): Promise<BedOut> {
  const { data } = await http.post<BedOut>(`/api/v1/rooms/${roomId}/beds`, {
    ...payload,
    room_id: roomId,
  })
  return data
}

export async function setBedStatus(
  bedId: number,
  action: 'enable' | 'disable' | 'maintenance'
): Promise<BedOut> {
  const { data } = await http.post<BedOut>(`/api/v1/beds/${bedId}/${action}`)
  return data
}

export async function fetchDormTree(includeDisabled = false): Promise<DormTreeNode[]> {
  const { data } = await http.get<DormTreeNode[]>('/api/v1/dormitories/tree', {
    params: { include_disabled: includeDisabled },
  })
  return data
}

export async function listAvailableBeds(params: {
  area_id?: number
  building_id?: number
  floor_id?: number
  gender_policy?: string
  limit?: number
} = {}): Promise<BedOut[]> {
  const { data } = await http.get<BedOut[]>('/api/v1/beds/available', { params })
  return data
}

export async function fetchFloorRoomCards(
  floorId: number,
  genderPolicy?: string
): Promise<import('@/types').RoomCardOut[]> {
  const { data } = await http.get<import('@/types').RoomCardOut[]>(
    `/api/v1/floors/${floorId}/room-cards`,
    { params: genderPolicy ? { gender_policy: genderPolicy } : {} }
  )
  return data
}

// ---- V1.0.1 ----

export async function deleteDormResource(
  kind: 'area' | 'building' | 'floor' | 'room' | 'bed',
  id: number
): Promise<{ deleted: boolean; id: number }> {
  const pathMap = {
    area: `/api/v1/dorm-areas/${id}`,
    building: `/api/v1/buildings/${id}`,
    floor: `/api/v1/floors/${id}`,
    room: `/api/v1/rooms/${id}`,
    bed: `/api/v1/beds/${id}`,
  } as const
  const { data } = await http.delete(pathMap[kind])
  return data
}

export async function revealRoomAccessCode(roomId: number): Promise<{ room_id: number; access_code: string | null }> {
  const { data } = await http.get(`/api/v1/rooms/${roomId}/access-code`)
  return data
}

export async function setRoomAccessCode(
  roomId: number,
  accessCode: string | null
): Promise<RoomOut> {
  const { data } = await http.put(`/api/v1/rooms/${roomId}/access-code`, {
    access_code: accessCode,
  })
  return data
}

export async function listRoomTypes(): Promise<
  Array<{
    id: number
    type_code: string
    type_name: string
    default_capacity: number
    description: string | null
    status: string
  }>
> {
  const { data } = await http.get('/api/v1/room-types')
  return data
}

export async function createRoomType(payload: {
  type_code: string
  type_name: string
  default_capacity: number
  description?: string | null
  status?: string
}): Promise<unknown> {
  const { data } = await http.post('/api/v1/room-types', payload)
  return data
}

export async function updateRoomType(
  id: number,
  payload: { type_name?: string; default_capacity?: number; description?: string | null; status?: string }
): Promise<unknown> {
  const { data } = await http.patch(`/api/v1/room-types/${id}`, payload)
  return data
}

export async function disableRoomType(id: number): Promise<unknown> {
  const { data } = await http.post(`/api/v1/room-types/${id}/disable`)
  return data
}

export async function downloadRoomImportTemplate(): Promise<Blob> {
  const { data } = await http.get('/api/v1/rooms/import/template', { responseType: 'blob' })
  return data
}

export async function previewRoomImport(file: File): Promise<unknown> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post('/api/v1/rooms/import/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    skipErrorToast: true,
  })
  return data
}

export async function commitRoomImport(file: File): Promise<unknown> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post('/api/v1/rooms/import/commit', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    skipErrorToast: true,
  })
  return data
}

export async function downloadAllocImportTemplate(): Promise<Blob> {
  const { data } = await http.get('/api/v1/allocations/import/template', { responseType: 'blob' })
  return data
}

export async function previewAllocImport(file: File): Promise<unknown> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post('/api/v1/allocations/import/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    skipErrorToast: true,
  })
  return data
}

export async function commitAllocImport(file: File): Promise<unknown> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post('/api/v1/allocations/import/commit', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    skipErrorToast: true,
  })
  return data
}

export async function updateBed(
  bedId: number,
  payload: { bed_no?: string; description?: string | null }
): Promise<BedOut> {
  const { data } = await http.patch<BedOut>(`/api/v1/beds/${bedId}`, payload)
  return data
}

export async function deleteRoomType(id: number): Promise<{ deleted: boolean; id: number }> {
  const { data } = await http.delete(`/api/v1/room-types/${id}`)
  return data
}
