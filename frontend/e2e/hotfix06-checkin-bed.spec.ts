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

test('HOTFIX-06: check-in list shows bed after reserve/confirm', async ({ page, request }) => {
  const token = await apiLogin(request)
  const h = auth(token)
  const code = `H6${Date.now().toString().slice(-6)}`

  const area = await request.post(`${BASE}/api/v1/dorm-areas`, {
    headers: h,
    data: { area_code: `A${code}`, area_name: `入住区${code}` },
  })
  const building = await request.post(`${BASE}/api/v1/buildings`, {
    headers: h,
    data: {
      area_id: (await area.json()).id,
      building_code: `B${code}`,
      building_name: `入住楼${code}`,
    },
  })
  const floor = await request.post(`${BASE}/api/v1/floors`, {
    headers: h,
    data: { building_id: (await building.json()).id, floor_no: 3 },
  })
  const room = await request.post(`${BASE}/api/v1/rooms`, {
    headers: h,
    data: { floor_id: (await floor.json()).id, room_no: `R${code}`, capacity: 1 },
  })
  const roomId = (await room.json()).id
  const bedsJson = await (
    await request.get(`${BASE}/api/v1/rooms/${roomId}/beds`, { headers: h })
  ).json()
  const beds = Array.isArray(bedsJson) ? bedsJson : bedsJson.items || []
  const bedNo = beds[0].bed_no

  const emp = await request.post(`${BASE}/api/v1/employees`, {
    headers: h,
    data: {
      employee_no: `E${code}`,
      full_name: `入住甲${code}`,
      employment_status: 'active',
      accommodation_required: true,
    },
  })
  const empId = (await emp.json()).id

  // create + approve
  const app = await request.post(`${BASE}/api/v1/checkin-applications`, {
    headers: h,
    data: { employee_id: empId, application_type: 'new' },
  })
  const appId = (await app.json()).id
  await request.post(`${BASE}/api/v1/checkin-applications/${appId}/approve`, {
    headers: h,
    data: {},
  })

  await login(page)
  await page.goto('/checkins')
  await page.getByPlaceholder('申请单号 / 工号 / 姓名').fill(`E${code}`)
  await page.getByRole('button', { name: '查询' }).click()
  await page.waitForTimeout(500)

  const row = page.getByRole('row', { name: new RegExp(`E${code}`) }).first()
  await expect(row).toBeVisible()
  // approved without bed → 未分配
  await expect(row.getByText('未分配')).toBeVisible()

  // reserve via API (UI reserve path covered by M6), then verify browser list
  await request.post(`${BASE}/api/v1/checkin-applications/${appId}/reserve`, {
    headers: h,
    data: { bed_id: beds[0].id },
  })
  await page.reload()
  await page.waitForTimeout(500)
  await page.getByPlaceholder('申请单号 / 工号 / 姓名').fill(`E${code}`)
  await page.getByRole('button', { name: '查询' }).click()
  await page.waitForTimeout(500)
  const row2 = page.getByRole('row', { name: new RegExp(`E${code}`) }).first()
  await expect(row2.getByText(`入住楼${code}`)).toBeVisible()
  await expect(row2.getByText(`R${code}`)).toBeVisible()
  await expect(row2.getByText(bedNo)).toBeVisible()

  // confirm check-in
  const confirmBtn = row2.getByRole('button', { name: /确认入住/ }).first()
  await confirmBtn.click()
  const box = page.locator('.el-message-box').getByRole('button', { name: /确定|OK|确认/ })
  if (await box.count()) await box.click()
  await page.waitForTimeout(800)

  await page.getByRole('button', { name: '查询' }).click()
  await page.waitForTimeout(400)
  const row3 = page.getByRole('row', { name: new RegExp(`E${code}`) }).first()
  await expect(row3.getByText('已入住').or(row3.getByText('checked_in'))).toBeVisible()
  await expect(row3.getByText(bedNo)).toBeVisible()

  // refresh page — bed still correct
  await page.reload()
  await page.waitForTimeout(600)
  await page.getByPlaceholder('申请单号 / 工号 / 姓名').fill(`E${code}`)
  await page.getByRole('button', { name: '查询' }).click()
  await page.waitForTimeout(400)
  const row4 = page.getByRole('row', { name: new RegExp(`E${code}`) }).first()
  await expect(row4.getByText(bedNo)).toBeVisible()
})
