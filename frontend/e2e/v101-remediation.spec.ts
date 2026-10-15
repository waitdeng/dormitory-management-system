import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

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

/** Minimal xlsx via Python is not available here — use CSV-like xlsx from API template. */
async function writeRoomImportXlsx(
  request: APIRequestContext,
  token: string,
  rows: Array<Array<string | number | null>>
): Promise<string> {
  const h = auth(token)
  const tpl = await request.get(`${BASE}/api/v1/rooms/import/template`, { headers: h })
  expect(tpl.ok()).toBeTruthy()
  // Build a real xlsx with the same header via a tiny OOXML workbook from the template bytes
  // and openpyxl-free row injection is hard; instead create via backend preview contract:
  // we use a minimal xlsx writer implemented below.
  const file = path.join(os.tmpdir(), `room-import-${Date.now()}.xlsx`)
  fs.writeFileSync(file, buildXlsx(rows))
  return file
}

/** Minimal XLSX writer (single sheet, inline strings) — enough for openpyxl read. */
function buildXlsx(rows: Array<Array<string | number | null>>): Buffer {
  const esc = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const sheetRows = rows
    .map((row, ri) => {
      const cells = row
        .map((val, ci) => {
          const ref = `${colName(ci)}${ri + 1}`
          if (val === null || val === undefined) return ''
          if (typeof val === 'number') return `<c r="${ref}"><v>${val}</v></c>`
          return `<c r="${ref}" t="inlineStr"><is><t>${esc(String(val))}</t></is></c>`
        })
        .join('')
      return `<row r="${ri + 1}">${cells}</row>`
    })
    .join('')
  const sheet = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetRows}</sheetData></worksheet>`
  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="rooms" sheetId="1" r:id="rId1"/></sheets></workbook>`
  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`
  const wbRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`
  // zip via store-only is non-trivial without a lib; use Python through a data URL in test? 
  // Playwright test runs in Node — use a simple ZIP writer.
  return zipStore([
    ['[Content_Types].xml', contentTypes],
    ['_rels/.rels', rels],
    ['xl/workbook.xml', workbook],
    ['xl/_rels/workbook.xml.rels', wbRels],
    ['xl/worksheets/sheet1.xml', sheet],
  ])
}

function colName(i: number): string {
  let s = ''
  let n = i
  do {
    s = String.fromCharCode(65 + (n % 26)) + s
    n = Math.floor(n / 26) - 1
  } while (n >= 0)
  return s
}

/** Store-only ZIP (no compression) — valid for openpyxl. */
function zipStore(files: Array<[string, string]>): Buffer {
  const chunks: Buffer[] = []
  const central: Buffer[] = []
  let offset = 0
  for (const [name, content] of files) {
    const nameBuf = Buffer.from(name, 'utf8')
    const data = Buffer.from(content, 'utf8')
    const crc = crc32(data)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(0, 6)
    local.writeUInt16LE(0, 8) // store
    local.writeUInt16LE(0, 10)
    local.writeUInt16LE(0, 12)
    local.writeUInt32LE(crc, 14)
    local.writeUInt32LE(data.length, 18)
    local.writeUInt32LE(data.length, 22)
    local.writeUInt16LE(nameBuf.length, 26)
    local.writeUInt16LE(0, 28)
    chunks.push(local, nameBuf, data)
    const cd = Buffer.alloc(46)
    cd.writeUInt32LE(0x02014b50, 0)
    cd.writeUInt16LE(20, 4)
    cd.writeUInt16LE(20, 6)
    cd.writeUInt16LE(0, 8)
    cd.writeUInt16LE(0, 10)
    cd.writeUInt16LE(0, 12)
    cd.writeUInt16LE(0, 14)
    cd.writeUInt32LE(crc, 16)
    cd.writeUInt32LE(data.length, 20)
    cd.writeUInt32LE(data.length, 24)
    cd.writeUInt16LE(nameBuf.length, 28)
    cd.writeUInt16LE(0, 30)
    cd.writeUInt16LE(0, 32)
    cd.writeUInt16LE(0, 34)
    cd.writeUInt16LE(0, 36)
    cd.writeUInt32LE(0, 38)
    cd.writeUInt32LE(offset, 42)
    central.push(cd, nameBuf)
    offset += local.length + nameBuf.length + data.length
  }
  const cdBuf = Buffer.concat(central)
  const eocd = Buffer.alloc(22)
  eocd.writeUInt32LE(0x06054b50, 0)
  eocd.writeUInt16LE(0, 4)
  eocd.writeUInt16LE(0, 6)
  eocd.writeUInt16LE(files.length, 8)
  eocd.writeUInt16LE(files.length, 10)
  eocd.writeUInt32LE(cdBuf.length, 12)
  eocd.writeUInt32LE(offset, 16)
  eocd.writeUInt16LE(0, 20)
  return Buffer.concat([...chunks, cdBuf, eocd])
}

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c >>> 0
  }
  return t
})()

function crc32(buf: Buffer): number {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) {
    c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  }
  return (c ^ 0xffffffff) >>> 0
}

test.describe('V1.0.1 remediation UI', () => {
  test('FEAT-002: room type create / edit / disable', async ({ page }) => {
    await login(page)
    await page.goto('/dormitories')
    await page.getByRole('button', { name: '房型维护' }).click()
    await expect(page.getByRole('dialog').getByText('房型维护')).toBeVisible()

    const code = `RT${Date.now().toString().slice(-6)}`
    await page.getByRole('button', { name: '新建房型' }).click()
    await page.locator('.el-dialog').last().locator('input').first().fill(code)
    await page.locator('.el-dialog').last().locator('input').nth(1).fill(`标准间${code}`)
    await page.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText(`标准间${code}`)).toBeVisible()

    // edit
    await page
      .getByRole('dialog')
      .getByRole('row', { name: new RegExp(code) })
      .getByRole('button', { name: '编辑' })
      .click()
    await page.locator('.el-dialog').last().locator('input').nth(1).fill(`豪华${code}`)
    await page.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText(`豪华${code}`)).toBeVisible()

    // disable
    await page
      .getByRole('dialog')
      .getByRole('row', { name: new RegExp(code) })
      .getByRole('button', { name: '停用' })
      .click()
    await page.locator('.el-message-box').getByRole('button', { name: /确定|OK|确认/ }).click()
    await expect(
      page.getByRole('dialog').getByRole('row', { name: new RegExp(code) }).getByText('停用')
    ).toBeVisible()
  })

  test('FEAT-002: room import dialog preview + commit', async ({ page, request }) => {
    const token = await apiLogin(request)
    const h = auth(token)
    const code = `IMP${Date.now().toString().slice(-6)}`

    const area = await request.post(`${BASE}/api/v1/dorm-areas`, {
      headers: h,
      data: { area_code: `IA${code}`, area_name: `导入区${code}` },
    })
    const areaId = (await area.json()).id
    const building = await request.post(`${BASE}/api/v1/buildings`, {
      headers: h,
      data: { area_id: areaId, building_code: `IB${code}`, building_name: `导入楼${code}` },
    })
    const buildingId = (await building.json()).id
    const floor = await request.post(`${BASE}/api/v1/floors`, {
      headers: h,
      data: { building_id: buildingId, floor_no: 1 },
    })
    const floorId = (await floor.json()).id

    const file = await writeRoomImportXlsx(request, token, [
      ['区域编码', '楼栋编码', '楼层号', '房间号', '房型编码', '容量', '性别政策', '门禁密码', '备注'],
      [`IA${code}`, `IB${code}`, 1, `R${code}`, 'standard', 2, 'any', '0042', 'e2e'],
      [`IA${code}`, `IB${code}`, 1, `R${code}`, 'standard', 2, 'any', null, 'dup'],
    ])

    await login(page)
    await page.goto('/dormitories')
    await page.getByRole('button', { name: '批量导入' }).click()
    await expect(page.getByRole('dialog').getByText('房间批量导入')).toBeVisible()

    // upload file
    await page.locator('input[type=file]').setInputFiles(file)
    await page.getByRole('button', { name: '上传预览' }).click()
    await expect(page.getByText(/总计 \d+ 行/)).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.el-table').getByText('错误').first()).toBeVisible()

    await page.getByRole('button', { name: '确认提交' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: /确定|OK|确认/ }).click()
    await expect(page.getByText(/导入完成/)).toBeVisible({ timeout: 15_000 })

    // room exists via API
    const rooms = await request.get(`${BASE}/api/v1/rooms?floor_id=${floorId}&keyword=R${code}`, {
      headers: h,
    })
    const items = (await rooms.json()).items as Array<{ room_no: string; has_access_code: boolean }>
    const hit = items.find((r) => r.room_no === `R${code}`)
    expect(hit).toBeTruthy()
    expect(hit!.has_access_code).toBe(true)

    // leading zero preserved
    const reveal = await request.get(`${BASE}/api/v1/rooms/${(hit as any).id}/access-code`, {
      headers: h,
    })
    expect((await reveal.json()).access_code).toBe('0042')
  })
})
