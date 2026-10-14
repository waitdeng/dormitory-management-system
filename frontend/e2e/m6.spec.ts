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
  const body = await res.json()
  return body.access_token as string
}

function auth(token: string) {
  return { Authorization: `Bearer ${token}` }
}

async function seedDormAndEmployee(
  request: APIRequestContext,
  token: string,
  suffix: string
): Promise<{
  employee: { id: number; employee_no: string; full_name: string }
  floorId: number
  roomId: number
  beds: Array<{ id: number; bed_no: string }>
  code: string
}> {
  const h = auth(token)
  const code = `${suffix}${Date.now().toString().slice(-6)}`

  const area = await request.post(`${BASE}/api/v1/dorm-areas`, {
    headers: h,
    data: { area_code: `A${code}`, area_name: `E2E区域${code}` },
  })
  expect(area.ok(), await area.text()).toBeTruthy()
  const areaId = (await area.json()).id

  const building = await request.post(`${BASE}/api/v1/buildings`, {
    headers: h,
    data: {
      area_id: areaId,
      building_code: `B${code}`,
      building_name: `E2E楼${code}`,
    },
  })
  expect(building.ok(), await building.text()).toBeTruthy()
  const buildingId = (await building.json()).id

  const floor = await request.post(`${BASE}/api/v1/floors`, {
    headers: h,
    data: { building_id: buildingId, floor_no: 1, floor_name: `1F${code}` },
  })
  expect(floor.ok(), await floor.text()).toBeTruthy()
  const floorId = (await floor.json()).id

  const room = await request.post(`${BASE}/api/v1/rooms`, {
    headers: h,
    data: { floor_id: floorId, room_no: `R${code}`, capacity: 2 },
  })
  expect(room.ok(), await room.text()).toBeTruthy()
  const roomId = (await room.json()).id

  // Room create auto-provisions beds (prefix B, count = capacity)
  const bedsRes = await request.get(`${BASE}/api/v1/rooms/${roomId}/beds`, {
    headers: h,
  })
  expect(bedsRes.ok(), await bedsRes.text()).toBeTruthy()
  const bedsJson = await bedsRes.json()
  const beds = Array.isArray(bedsJson) ? bedsJson : bedsJson.items || []
  expect(beds.length).toBeGreaterThanOrEqual(2)

  const emp = await request.post(`${BASE}/api/v1/employees`, {
    headers: h,
    data: {
      employee_no: `E${code}`,
      full_name: `E2E员工${code}`,
      gender: 'male',
      employment_status: 'active',
    },
  })
  expect(emp.ok(), await emp.text()).toBeTruthy()
  const employee = await emp.json()

  return { employee, floorId, roomId, beds, code }
}

async function openAllocation(page: Page, code: string) {
  await page.getByRole('menuitem', { name: /可视化分床/ }).click()
  await expect(page.getByText('宿舍导航')).toBeVisible()
  const areaNode = page
    .locator('.el-tree-node', { hasText: `E2E区域${code}` })
    .first()
  await expect(areaNode).toBeVisible()
  await areaNode.locator('.el-tree-node__expand-icon').first().click()
  const buildingNode = areaNode
    .locator('.el-tree-node', { hasText: `E2E楼${code}` })
    .first()
  await expect(buildingNode).toBeVisible({ timeout: 10_000 })
  await buildingNode.locator('.el-tree-node__expand-icon').first().click()
  const floorNode = buildingNode
    .locator('.el-tree-node', { hasText: `1F${code}` })
    .first()
  await expect(floorNode).toBeVisible({ timeout: 10_000 })
  await floorNode.locator('.el-tree-node__content').first().click()
  await expect(page.getByText('房间床位')).toBeVisible()
}

test.describe('M6 P0-2 真实分床流程', () => {
  test('选员工 → 选空床 → 提交分配 → 确认入住 → 状态刷新', async ({ page, request }) => {
    const token = await apiLogin(request)
    const { employee, floorId, beds, code } = await seedDormAndEmployee(
      request,
      token,
      'ALLOC'
    )
    const freeBedNo = beds[0].bed_no

    await login(page)
    await openAllocation(page, code)

    // select employee
    await page.getByRole('button', { name: '选择员工' }).click()
    await page.getByPlaceholder('工号 / 姓名').fill(employee.employee_no)
    await page.getByPlaceholder('工号 / 姓名').press('Enter')
    await page.getByRole('cell', { name: employee.employee_no }).first().click()
    await expect(page.locator('.emp-line', { hasText: employee.full_name })).toBeVisible()

    // free bed is clickable and labeled 空闲
    const freeBedBtn = page.getByRole('button', { name: new RegExp(`${freeBedNo}.*空闲`) })
    await expect(freeBedBtn).toBeEnabled()

    // allocate
    await freeBedBtn.click()
    await expect(page.getByText('确认分床')).toBeVisible()
    await page.getByRole('button', { name: /^OK$/ }).click()

    await expect(page.getByText('分配成功')).toBeVisible({ timeout: 15_000 })

    // status refresh: bed no longer available
    await expect(
      page.getByRole('button', { name: new RegExp(`${freeBedNo}.*已入住`) })
    ).toBeVisible({ timeout: 15_000 })

    // backend agrees
    const cards = await request.get(
      `${BASE}/api/v1/floors/${floorId}/room-cards`,
      { headers: auth(token) }
    )
    expect(cards.ok()).toBeTruthy()
    const body = await cards.json()
    const flat = body.flatMap((r: { beds: Array<{ id: number; available: boolean; occupied: boolean }> }) => r.beds)
    const target = flat.find((b: { id: number }) => b.id === beds[0].id)
    expect(target).toBeTruthy()
    expect(target.occupied).toBe(true)
    expect(target.available).toBe(false)
  })

  test('不可用床位无法错误分配', async ({ page, request }) => {
    const token = await apiLogin(request)
    const { employee, floorId, roomId, beds, code } = await seedDormAndEmployee(
      request,
      token,
      'LOCK'
    )

    // disable second bed via API
    const dis = await request.post(
      `${BASE}/api/v1/beds/${beds[1].id}/disable`,
      { headers: auth(token), data: {} }
    )
    expect(dis.ok(), await dis.text()).toBeTruthy()

    await login(page)
    await openAllocation(page, code)

    await page.getByRole('button', { name: '选择员工' }).click()
    await page.getByPlaceholder('工号 / 姓名').fill(employee.employee_no)
    await page.getByPlaceholder('工号 / 姓名').press('Enter')
    await page.getByRole('cell', { name: employee.employee_no }).first().click()

    const disabledBed = page.getByRole('button', {
      name: new RegExp(`${beds[1].bed_no}.*停用`),
    })
    await expect(disabledBed).toBeVisible()
    await expect(disabledBed).toBeDisabled()

    // occupied path: allocate first bed via API then UI shows 已入住 disabled
    const app = await request.post(`${BASE}/api/v1/checkin-applications`, {
      headers: auth(token),
      data: { employee_id: employee.id, application_type: 'new' },
    })
    const appId = (await app.json()).id
    await request.post(`${BASE}/api/v1/checkin-applications/${appId}/approve`, {
      headers: auth(token),
      data: {},
    })
    await request.post(`${BASE}/api/v1/checkin-applications/${appId}/reserve`, {
      headers: auth(token),
      data: { bed_id: beds[0].id },
    })
    await request.post(`${BASE}/api/v1/checkin-applications/${appId}/confirm`, {
      headers: auth(token),
      data: {},
    })

    await page.getByRole('button', { name: /刷新状态/ }).click()
    const occupiedBed = page.getByRole('button', {
      name: new RegExp(`${beds[0].bed_no}.*已入住`),
    })
    await expect(occupiedBed).toBeVisible({ timeout: 15_000 })
    await expect(occupiedBed).toBeDisabled()
  })

  test('并发分床 409 冲突时明确提示并刷新数据', async ({ page, request }) => {
    const token = await apiLogin(request)
    const { employee, floorId, beds, code } = await seedDormAndEmployee(
      request,
      token,
      'CONF'
    )
    const freeBedNo = beds[0].bed_no

    await login(page)
    await openAllocation(page, code)

    await page.getByRole('button', { name: '选择员工' }).click()
    await page.getByPlaceholder('工号 / 姓名').fill(employee.employee_no)
    await page.getByPlaceholder('工号 / 姓名').press('Enter')
    await page.getByRole('cell', { name: employee.employee_no }).first().click()

    // Another admin claims the bed via API after UI shows it free (race)
    const otherEmp = await request.post(`${BASE}/api/v1/employees`, {
      headers: auth(token),
      data: {
        employee_no: `RACE${Date.now().toString().slice(-6)}`,
        full_name: 'E2E竞争者',
        gender: 'female',
        employment_status: 'active',
      },
    })
    const otherId = (await otherEmp.json()).id
    const app2 = await request.post(`${BASE}/api/v1/checkin-applications`, {
      headers: auth(token),
      data: { employee_id: otherId, application_type: 'new' },
    })
    const app2Id = (await app2.json()).id
    await request.post(`${BASE}/api/v1/checkin-applications/${app2Id}/approve`, {
      headers: auth(token),
      data: {},
    })
    await request.post(`${BASE}/api/v1/checkin-applications/${app2Id}/reserve`, {
      headers: auth(token),
      data: { bed_id: beds[0].id },
    })

    // UI still shows free until refresh — click allocate
    const freeBedBtn = page.getByRole('button', {
      name: new RegExp(`${freeBedNo}.*空闲`),
    })
    await expect(freeBedBtn).toBeEnabled()
    await freeBedBtn.click()
    await page.getByRole('button', { name: /^OK$/ }).click()

    // explicit conflict message + refresh to occupied/reserved
    await expect(
      page.getByText(/已被其他管理员分配|床位冲突/)
    ).toBeVisible({ timeout: 15_000 })
    await expect(
      page
        .getByRole('button', { name: new RegExp(`${freeBedNo}.*(已预留|已入住)`) })
        .first()
    ).toBeVisible({ timeout: 15_000 })
  })
})
