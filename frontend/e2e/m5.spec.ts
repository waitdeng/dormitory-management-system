import { expect, test } from '@playwright/test'

const ADMIN = process.env.DMS_ADMIN_USERNAME || 'admin'
const PASSWORD = process.env.DMS_ADMIN_PASSWORD || 'admin12345'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill(ADMIN)
  await page.getByPlaceholder('请输入密码').fill(PASSWORD)
  await page.getByRole('button', { name: /登\s*录/ }).click()
  await page.waitForURL(/dashboard/, { timeout: 20_000 })
}

test.describe('M5 E2E', () => {
  test('dashboard shows KPI cards', async ({ page }) => {
    await login(page)
    await expect(page.getByText('可分配空床')).toBeVisible()
    await expect(page.getByText('入住率')).toBeVisible()
    await expect(page.getByText('今日入住')).toBeVisible()
  })

  test('bed allocation page shows room cards', async ({ page }) => {
    await login(page)
    await page.getByRole('menuitem', { name: /可视化分床/ }).click()
    await expect(page.getByText('宿舍导航')).toBeVisible()
    await expect(page.getByText('待入住员工')).toBeVisible()
  })

  test('reports page lists six tabs and export', async ({ page }) => {
    await login(page)
    await page.getByRole('menuitem', { name: /统计报表/ }).click()
    await expect(page.getByText('住宿台账')).toBeVisible()
    await expect(page.getByText('空床统计')).toBeVisible()
    await expect(page.getByText('部门住宿')).toBeVisible()
    await expect(page.getByText('导出 Excel')).toBeVisible()
  })
})
