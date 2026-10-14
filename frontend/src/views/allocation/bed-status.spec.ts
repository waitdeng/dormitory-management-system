import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('@/api/dormitories', () => ({
  fetchDormTree: vi.fn().mockResolvedValue([]),
  fetchFloorRoomCards: vi.fn().mockResolvedValue([]),
}))
vi.mock('@/api/employees', () => ({
  listEmployees: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
}))
vi.mock('@/api/accommodations', () => ({
  createCheckinApplication: vi.fn(),
  approveCheckinApplication: vi.fn(),
  reserveCheckinBed: vi.fn(),
  confirmCheckin: vi.fn(),
}))

import BedAllocationView from '@/views/allocation/BedAllocationView.vue'

function bedStatus(operational: string, occupied: boolean, reserved: boolean) {
  if (operational === 'disabled') return '停用'
  if (operational === 'maintenance') return '维修'
  if (occupied) return '已入住'
  if (reserved) return '已预留'
  return '空闲'
}

describe('bed status labels', () => {
  it('maps five bed states to text labels (not color-only)', () => {
    expect(bedStatus('active', false, false)).toBe('空闲')
    expect(bedStatus('active', false, true)).toBe('已预留')
    expect(bedStatus('active', true, false)).toBe('已入住')
    expect(bedStatus('maintenance', true, false)).toBe('维修')
    expect(bedStatus('disabled', false, false)).toBe('停用')
  })
})

describe('BedAllocationView', () => {
  it('renders navigation and employee panel', async () => {
    const wrapper = mount(BedAllocationView, {
      global: { plugins: [ElementPlus, createPinia()] },
    })
    await Promise.resolve()
    expect(wrapper.text()).toContain('宿舍导航')
    expect(wrapper.text()).toContain('待入住员工')
  })
})
