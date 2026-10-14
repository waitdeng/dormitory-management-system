import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('@/api/reports', () => ({
  fetchAccommodationLedger: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  fetchVacantBeds: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  fetchDepartmentStats: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  fetchCheckinCheckoutReport: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  fetchTransferReport: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  fetchExceptionReport: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  exportReport: vi.fn(),
  downloadBlob: vi.fn(),
}))

import ReportsView from '@/views/reports/ReportsView.vue'

describe('ReportsView', () => {
  it('shows all six report tabs and export button', () => {
    const wrapper = mount(ReportsView, {
      global: { plugins: [ElementPlus, createPinia()] },
    })
    const text = wrapper.text()
    expect(text).toContain('住宿台账')
    expect(text).toContain('空床统计')
    expect(text).toContain('部门住宿')
    expect(text).toContain('入退宿明细')
    expect(text).toContain('调宿明细')
    expect(text).toContain('异常报表')
    expect(text).toContain('导出 Excel')
  })
})
