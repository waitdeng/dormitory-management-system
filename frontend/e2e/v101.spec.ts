import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const ADMIN = process.env.DMS_ADMIN_USERNAME || 'admin'
const PASSWORD = process.env.DMS_ADMIN_PASSWORD || 'admin12345'
const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill(ADMIN)
  await page.getByPlaceholder('请输入密码').fill(PASSWORD)
  await page.getByRole('button', { name: /登\s*录/ }).click()
  await page.waitForURL(/dashboard/, { timeout: 20_000 })
}

async function apiLogin(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${BASE}/api/v1/auth/login`, {
    data: { username: ADMIN, password: PASSWORD },
  })
  expect(res.ok(), await res.text()).toBeTruthy()
  return (await res.json()).access_token as string
}

function auth(token: string) {
  return { Authorization: `Bearer ${token}` }
}

test.describe('V1.0.1 UI fixes', () => {
  test('BUG-003/UX-004: room tree click opens beds without validation error', async ({
    page,
    request,
  }) => {
    const token = await apiLogin(request)
    const h = auth(token)
    const code = `V101${Date.now().toString().slice(-6)}`

    const area = await request.post(`${BASE}/api/v1/dorm-areas`, {
      headers: h,
      data: { area_code: `A${code}`, area_name: `区域${code}` },
    })
    const areaId = (await area.json()).id
    const building = await request.post(`${BASE}/api/v1/buildings`, {
      headers: h,
      data: { area_id: areaId, building_code: `B${code}`, building_name: `楼${code}` },
    })
    const buildingId = (await building.json()).id
    const floor = await request.post(`${BASE}/api/v1/floors`, {
      headers: h,
      data: { building_id: buildingId, floor_no: 1 },
    })
    const floorId = (await floor.json()).id
    const room = await request.post(`${BASE}/api/v1/rooms`, {
      headers: h,
      data: { floor_id: floorId, room_no: `R${code}`, capacity: 2 },
    })
    const roomId = (await room.json()).id

    await login(page)

    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    const bad422: string[] = []
    page.on('response', async (res) => {
      if (res.status() === 422) bad422.push(res.url())
    })

    await page.goto('/dormitories')
    await page.waitForTimeout(800)

    // click floor then room in tree
    await page.getByRole('tree').getByText(`楼${code}`).click()
    await page.waitForTimeout(400)
    await page.getByRole('tree').getByText(`R${code}`).click()
    await page.waitForTimeout(800)

    // beds dialog should open for the room
    await expect(page.getByRole('dialog')).toBeVisible()
    // no 422 from floor_id=0
    expect(bad422.filter((u) => u.includes('/api/v1/rooms'))).toEqual([])
  })

  test('BUG-005: transfer target bed shows full location path', async ({ page, request }) => {
    const token = await apiLogin(request)
    const h = auth(token)
    const code = `T${Date.now().toString().slice(-6)}`

    const area = await request.post(`${BASE}/api/v1/dorm-areas`, {
      headers: h,
      data: { area_code: `TA${code}`, area_name: `调宿区${code}` },
    })
    const areaId = (await area.json()).id
    const building = await request.post(`${BASE}/api/v1/buildings`, {
      headers: h,
      data: { area_id: areaId, building_code: `TB${code}`, building_name: `调宿楼${code}` },
    })
    const buildingId = (await building.json()).id
    const floor = await request.post(`${BASE}/api/v1/floors`, {
      headers: h,
      data: { building_id: buildingId, floor_no: 2 },
    })
    const floorId = (await floor.json()).id
    const room = await request.post(`${BASE}/api/v1/rooms`, {
      headers: h,
      data: { floor_id: floorId, room_no: `TR${code}`, capacity: 2 },
    })
    const roomId = (await room.json()).id
    const bedsRes = await request.get(`${BASE}/api/v1/rooms/${roomId}/beds`, { headers: h })
    const bedsJson = await bedsRes.json()
    const beds = Array.isArray(bedsJson) ? bedsJson : bedsJson.items || []

    // verify API bed path
    const avail = await request.get(
      `${BASE}/api/v1/beds/available?limit=200&building_id=${buildingId}`,
      { headers: h }
    )
    const list = await avail.json()
    const hit = list.find((b: { id: number }) => b.id === beds[0].id)
    expect(hit).toBeTruthy()
    expect(String(hit.bed_path || '')).toContain(`调宿楼${code}`)
    expect(String(hit.bed_path || '')).toContain('2')

    await login(page)
    await page.goto('/transfers')
    await page.getByRole('button', { name: '新建调宿' }).click()
    // open target bed select
    await page.locator('.el-select').nth(1).click()
    await page.waitForTimeout(500)
    // option labels contain area/building/floor/room/bed path, not just bed no + room id
    const options = await page.locator('.el-select-dropdown__item').allTextContents()
    // Format must be 区域/楼栋/楼层/房间/床位 — not just bed_no + room_id
    const full = options.find((t) => t.includes('/') && t.split('/').length >= 4)
    expect(full, options.slice(0, 5).join(' | ')).toBeTruthy()
    expect(full).toMatch(/\d+/)
  })

  test('BUG-007: no-accommodation employee hidden from allocation list', async ({
    page,
    request,
  }) => {
    const token = await apiLogin(request)
    const h = auth(token)
    const code = `N${Date.now().toString().slice(-6)}`
    const created = await request.post(`${BASE}/api/v1/employees`, {
      headers: h,
      data: {
        employee_no: `E${code}`,
        full_name: `不需住宿${code}`,
        employment_status: 'active',
        accommodation_required: false,
      },
    })
    expect(created.ok(), await created.text()).toBeTruthy()

    await login(page)
    await page.goto('/bed-allocation')
    await page.getByRole('button', { name: /选择.*员工|待入住员工|选择员工/ }).first().click()
    await page.waitForTimeout(600)
    const body = await page.locator('body').innerText()
    expect(body).not.toContain(`不需住宿${code}`)
    expect(body).not.toContain(`E${code}`)
  })
})
