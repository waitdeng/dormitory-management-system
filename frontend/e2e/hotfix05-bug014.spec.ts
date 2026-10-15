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

function auth(token: string) {
  return { Authorization: `Bearer ${token}` }
}

async function selectFloor(page: Page, area: string, building: string, floor: string) {
  await page.locator('.el-tree-node__content', { hasText: area }).first().click()
  await page.waitForTimeout(400)
  await page.locator('.el-tree-node__content', { hasText: building }).first().click()
  await page.waitForTimeout(400)
  await page.locator('.el-tree-node__content', { hasText: floor }).first().click()
  await page.waitForTimeout(600)
}

test.describe('HOTFIX-05 BUG-014 allocation candidates', () => {
  test('only active employees appear; footer-only confirm; allocate once', async ({
    page,
    request,
  }) => {
    const token = await apiLogin(request)
    const h = auth(token)
    const code = `B14${Date.now().toString().slice(-6)}`

    const area = await request.post(`${BASE}/api/v1/dorm-areas`, {
      headers: h,
      data: { area_code: `A${code}`, area_name: `候选区${code}` },
    })
    const building = await request.post(`${BASE}/api/v1/buildings`, {
      headers: h,
      data: {
        area_id: (await area.json()).id,
        building_code: `B${code}`,
        building_name: `候选楼${code}`,
      },
    })
    const floor = await request.post(`${BASE}/api/v1/floors`, {
      headers: h,
      data: { building_id: (await building.json()).id, floor_no: 1, floor_name: `1F${code}` },
    })
    const room = await request.post(`${BASE}/api/v1/rooms`, {
      headers: h,
      data: { floor_id: (await floor.json()).id, room_no: `R${code}`, capacity: 2 },
    })
    const roomId = (await room.json()).id
    const bedsJson = await (
      await request.get(`${BASE}/api/v1/rooms/${roomId}/beds`, { headers: h })
    ).json()
    const beds = Array.isArray(bedsJson) ? bedsJson : bedsJson.items || []

    const activeEmp = await request.post(`${BASE}/api/v1/employees`, {
      headers: h,
      data: {
        employee_no: `EA${code}`,
        full_name: `在职甲${code}`,
        employment_status: 'active',
        accommodation_required: true,
      },
    })
    const probationEmp = await request.post(`${BASE}/api/v1/employees`, {
      headers: h,
      data: {
        employee_no: `EP${code}`,
        full_name: `试用乙${code}`,
        employment_status: 'probation',
        accommodation_required: true,
      },
    })
    expect(activeEmp.ok() && probationEmp.ok()).toBeTruthy()

    await login(page)
    await page.goto('/bed-allocation')
    await selectFloor(page, `候选区${code}`, `候选楼${code}`, `1F${code}`)

    await page.getByRole('button', { name: new RegExp(`${beds[0].bed_no}.*空闲`) }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText(/目标床位/)).toBeVisible()

    // no top-right confirm — only one 确认分配 (footer)
    await expect(dialog.getByRole('button', { name: '确认分配' })).toHaveCount(1)

    // search both
    await dialog.getByPlaceholder('姓名 / 工号 / 部门搜索').fill(code)
    await dialog.getByRole('button', { name: '搜索' }).click()
    await page.waitForTimeout(400)

    const body = await dialog.innerText()
    expect(body).toContain(`在职甲${code}`)
    expect(body).not.toContain(`试用乙${code}`)
    expect(body).toContain('在职')

    // pick active employee and confirm from footer button only
    await dialog.getByRole('cell', { name: `在职甲${code}` }).click()
    const confirm = dialog.getByRole('button', { name: '确认分配' })
    await expect(confirm).toBeEnabled()
    await confirm.click()
    await expect(page.getByText('分配成功')).toBeVisible({ timeout: 15_000 })
  })
})
