import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

describe('auth store permission gating', () => {
  it('hasPermission matches exact codes', () => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.permissions = ['report:view', 'dorm:view']
    auth.roles = ['dept_manager']
    expect(auth.hasPermission('report:view')).toBe(true)
    expect(auth.hasPermission('report:export')).toBe(false)
    expect(auth.hasAnyPermission('user:manage', 'dorm:view')).toBe(true)
    expect(auth.hasAnyPermission('user:manage', 'role:manage')).toBe(false)
  })
})
