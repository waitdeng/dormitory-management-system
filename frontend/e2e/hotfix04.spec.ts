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
  expect(res.ok()).toBeTruthy()
  return (await res.json()).access_token as string
}


async function selectFloorInTree(
  page: Page,
  areaName: string,
  buildingName: string,
  floorName: string
) {
  // Element Plus: clicking a node expands it (expand-on-click-node default true)
  const area = page.locator('.el-tree-node__content', { hasText: areaName }).first()
  await area.waitFor({ state: 'visible', timeout: 20_000 })
  await area.click()
  await page.waitForTimeout(400)

  const building = page.locator('.el-tree-node__content', { hasText: buildingName }).first()
  await building.waitFor({ state: 'visible', timeout: 20_000 })
  await building.click()
  await page.waitForTimeout(400)

  const floor = page.locator('.el-tree-node__content', { hasText: floorName }).first()
  await floor.waitFor({ state: 'visible', timeout: 20_000 })
  await floor.click()
  await page.waitForTimeout(700)
}

function auth(token: string) {
  return { Authorization: `Bearer ${token}` }
}

async function seed(request: APIRequestContext, token: string, suffix: string) {
  const h = auth(token)
  const code = `${suffix}${Date.now().toString().slice(-6)}`
  const area = await request.post(`${BASE}/api/v1/dorm-areas`, {
    headers: h,
    data: { area_code: `A${code}`, area_name: `热修区${code}` },
  })
  const areaId = (await area.json()).id
  const building = await request.post(`${BASE}/api/v1/buildings`, {
    headers: h,
    data: { area_id: areaId, building_code: `B${code}`, building_name: `热修楼${code}` },
  })
  const buildingId = (await building.json()).id
  const floor = await request.post(`${BASE}/api/v1/floors`, {
    headers: h,
    data: { building_id: buildingId, floor_no: 1, floor_name: `1F${code}` },
  })
  const floorId = (await floor.json()).id
  const room = await request.post(`${BASE}/api/v1/rooms`, {
    headers: h,
    data: { floor_id: floorId, room_no: `R${code}`, capacity: 2 },
  })
  const roomId = (await room.json()).id
  const bedsRes = await request.get(`${BASE}/api/v1/rooms/${roomId}/beds`, { headers: h })
  const bedsJson = await bedsRes.json()
  const beds = Array.isArray(bedsJson) ? bedsJson : bedsJson.items || []
  return { code, areaId, buildingId, floorId, roomId, beds }
}

test.describe('HOTFIX-04', () => {
  test('FIX-009: tree edit floor and delete protection', async ({ page, request }) => {
    const token = await apiLogin(request)
    const s = await seed(request, token, 'HF')

    await login(page)
    await page.goto('/dormitories')
    await page.getByRole('tree').getByText(`热修楼${s.code}`).click()
    await page.waitForTimeout(300)
    await page.getByRole('tree').getByText(`1F${s.code}`).click()
    await page.waitForTimeout(300)
    await page.getByRole('button', { name: '编辑楼层' }).click()
    const dlg = page.locator('.el-dialog').last()
    await dlg.locator('input').nth(1).fill(`一层改${s.code}`)
    await page.getByRole('button', { name: '保存' }).click()
    await expect(page.getByRole('tree').getByText(`一层改${s.code}`)).toBeVisible({ timeout: 10_000 })

    // delete room with beds must be blocked via UI confirm + error
    await page.getByRole('tree').getByText(`R${s.code}`).click()
    // room click opens beds dialog (BUG-003 behavior) — close it first
    await page.waitForTimeout(400)
    const closeBtn = page.locator('.el-dialog').last().locator('.el-dialog__headerbtn')
    if (await closeBtn.count()) {
      await closeBtn.first().click().catch(() => {})
      await page.waitForTimeout(200)
    }
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    await page.getByRole('button', { name: '删除节点' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: /删除|确定|OK/ }).click()
    await expect(page.locator('.el-message, .el-notification').first()).toBeVisible({ timeout: 10_000 })
    // room still present
    await expect(page.getByRole('tree').getByText(`R${s.code}`)).toBeVisible()
  })

  test('FIX-010: room type delete blocked when referenced', async ({ page, request }) => {
    const token = await apiLogin(request)
    const h = auth(token)
    const code = `RT${Date.now().toString().slice(-6)}`
    const created = await request.post(`${BASE}/api/v1/room-types`, {
      headers: h,
      data: { type_code: code, type_name: `热修房型${code}`, default_capacity: 2, status: 'active' },
    })
    const typeId = (await created.json()).id
    const s = await seed(request, token, 'RT')
    await request.patch(`${BASE}/api/v1/rooms/${s.roomId}`, {
      headers: h,
      data: { room_type: code },
    })

    await login(page)
    await page.goto('/dormitories')
    await page.getByRole('button', { name: '房型维护' }).click()
    await page
      .getByRole('dialog')
      .getByRole('row', { name: new RegExp(code) })
      .getByRole('button', { name: '删除' })
      .click()
    await page.locator('.el-message-box').getByRole('button', { name: /删除|确定|OK/ }).click()
    await expect(page.getByText(/引用|停用/).first()).toBeVisible({ timeout: 10_000 })
    // still listed
    await expect(page.getByRole('dialog').getByText(`热修房型${code}`)).toBeVisible()
  })

  test('UX-011: allocation filters and reset', async ({ page, request }) => {
    const token = await apiLogin(request)
    const s = await seed(request, token, 'FT')
    await login(page)
    await page.goto('/bed-allocation')
    await selectFloorInTree(page, `热修区${s.code}`, `热修楼${s.code}`, `1F${s.code}`)

    // filter by bed status empty
    await page.locator('.filter-bar .el-select').first().click()
    await page.locator('.el-select-dropdown__item', { hasText: '空闲' }).click()
    await expect(page.locator('.stats')).toContainText('空闲')

    // keyword
    await page.getByPlaceholder('房间号 / 床位号').fill(`R${s.code}`)
    await expect(page.locator('.room-card').first()).toBeVisible()

    // reset
    await page.getByRole('button', { name: '重置' }).click()
    await expect(page.getByPlaceholder('房间号 / 床位号')).toHaveValue('')
  })

  test('UX-012: click bed → pick employee → confirm allocate once', async ({ page, request }) => {
    const token = await apiLogin(request)
    const s = await seed(request, token, 'UX')
    const h = auth(token)
    const emp = await request.post(`${BASE}/api/v1/employees`, {
      headers: h,
      data: {
        employee_no: `E${s.code}`,
        full_name: `点床员工${s.code}`,
        employment_status: 'active',
        accommodation_required: true,
      },
    })
    expect(emp.ok()).toBeTruthy()

    await login(page)
    await page.goto('/bed-allocation')
    await selectFloorInTree(page, `热修区${s.code}`, `热修楼${s.code}`, `1F${s.code}`)

    // click first available bed
    await page
      .locator('.room-card button', { hasText: '空闲' })
      .first()
      .click()

    // dialog shows full path and confirm button
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('dialog').getByText(/目标床位/)).toBeVisible()
    const confirmBtn = page
      .getByRole('dialog')
      .getByRole('button', { name: '确认分配' })
      .first()
    await expect(confirmBtn).toBeDisabled()

    // search and pick employee
    await page.getByPlaceholder('姓名 / 工号 / 部门搜索').fill(`E${s.code}`)
    await page.getByRole('button', { name: '搜索' }).click()
    await page.getByRole('cell', { name: `点床员工${s.code}` }).click()
    await expect(confirmBtn).toBeEnabled()

    // confirm once — must allocate without clicking bed again
    await confirmBtn.click()
    await expect(page.locator('.el-message', { hasText: '分配成功' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('dialog')).toBeHidden({ timeout: 10_000 })

    // bed now occupied
    await expect(page.locator('.room-card').first().getByText('已入住').first()).toBeVisible()
  })
})
