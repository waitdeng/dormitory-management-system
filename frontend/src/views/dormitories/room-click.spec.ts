import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('@/api/dormitories', () => ({
  fetchDormTree: vi.fn().mockResolvedValue([]),
  fetchRoom: vi.fn().mockResolvedValue({
    id: 12,
    floor_id: 3,
    room_no: 'R101',
    room_type: 'standard',
    capacity: 4,
    gender_policy: 'any',
    status: 'active',
    description: null,
    bed_count: 2,
    active_bed_count: 2,
    created_at: null,
    updated_at: null,
  }),
  listRooms: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  listRoomBeds: vi.fn().mockResolvedValue([]),
  listAreas: vi.fn(),
  createArea: vi.fn(),
  updateArea: vi.fn(),
  listBuildings: vi.fn(),
  createBuilding: vi.fn(),
  updateBuilding: vi.fn(),
  listFloors: vi.fn(),
  createFloor: vi.fn(),
  updateFloor: vi.fn(),
  createRoom: vi.fn(),
  updateRoom: vi.fn(),
  createBed: vi.fn(),
  setBedStatus: vi.fn(),
  listAvailableBeds: vi.fn(),
  fetchFloorRoomCards: vi.fn(),
}))

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, notifyError: vi.fn() }
})

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    hasPermission: () => true,
    permissions: ['dorm:view', 'dorm:create', 'dorm:update', 'bed:manage'],
  }),
}))

import { mount, flushPromises } from '@vue/test-utils'
import DormitoriesView from './DormitoriesView.vue'
import { listRooms, fetchRoom, listRoomBeds } from '@/api/dormitories'

describe('BUG-003 room tree click', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not request rooms with floor_id=0 and opens real room beds', async () => {
    const wrapper = mount(DormitoriesView, {
      global: {
        stubs: {
          ElCard: true,
          ElTree: true,
          ElButton: true,
          ElTable: true,
          ElTableColumn: true,
          ElDialog: true,
          ElForm: true,
          ElFormItem: true,
          ElInput: true,
          ElSelect: true,
          ElOption: true,
          ElTag: true,
          ElSwitch: true,
          ElPagination: true,
          ElEmpty: true,
        },
      },
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      onNodeClick: (node: unknown) => void
    }
    vm.onNodeClick({
      id: 12,
      node_type: 'room',
      code: 'R101',
      name: 'R101',
      status: 'active',
      extra: { capacity: 4, floor_id: 3 },
      children: [],
    })
    await flushPromises()

    expect(fetchRoom).toHaveBeenCalledWith(12)
    expect(listRoomBeds).toHaveBeenCalledWith(12)
    for (const call of (listRooms as ReturnType<typeof vi.fn>).mock.calls) {
      const params = call[0] || {}
      if (params.floor_id !== undefined) {
        expect(params.floor_id).toBeGreaterThan(0)
      }
    }
  })
})
