import { expect, test } from '@playwright/test'
import { mockRunWorkspace, mockShell, runDetail, runName } from './run-fixture'

test('run review and lead evidence workflow', async ({ page }, testInfo) => {
  const consoleErrors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  await mockRunWorkspace(page)

  await page.goto('/runs')
  await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible()
  await expect(page.locator('[role="status"]:visible')).toContainText(/Local API online|Systems ready/)
  const navigationStarted = Date.now()
  await page.getByRole('link', { name: runName, exact: true }).click()
  await expect(page.getByRole('heading', { name: runName })).toBeVisible()
  expect(Date.now() - navigationStarted).toBeLessThan(2000)
  await expect(page.getByText('Harley Street Dental Studio')).toBeVisible()

  const candidatesTab = page.getByRole('tab', { name: /Candidates/ })
  await candidatesTab.focus()
  await candidatesTab.press('ArrowRight')
  await expect(page.getByText('7 of 20 pages · 2 contacts')).toBeVisible()
  await expect(page.getByLabel('7 of 20 pages checked')).toBeVisible()
  await page.getByRole('tab', { name: /Progress/ }).press('End')
  await expect(page.getByRole('tab', { name: /Leads/ })).toBeFocused()
  await expect(page.getByRole('tabpanel', { name: /Leads/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Harley Street Dental Studio/ })).toBeVisible()
  await page.getByRole('button', { name: /Harley Street Dental Studio/ }).click()
  await expect(page.getByRole('dialog', { name: 'Harley Street Dental Studio' })).toBeVisible()
  await expect(page.getByText('hello@harleystreet.example').first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Review outreach eligibility' })).toBeVisible()

  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(hasOverflow).toBe(false)
  expect(consoleErrors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('lead-detail.png'), fullPage: true })
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('dialog', { name: 'Harley Street Dental Studio' })).toBeHidden()
  expect(consoleErrors).toEqual([])
})

test('new run form remains usable at target viewport', async ({ page }, testInfo) => {
  await page.route('**/api/v1/discovery/history?*', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ previous_runs: 3, seen_domains: 28, completed_leads: 17 }),
    })
  })
  await page.goto('/new')
  await expect(page.getByRole('heading', { name: 'Find your next market' })).toBeVisible()
  await page.getByLabel('Business niche').fill('independent salons')
  await expect(page.getByText('28 sites already seen')).toBeVisible()
  await page.getByLabel('Reuse saved').check()
  await expect(page.getByLabel('Reuse saved')).toBeChecked()
  await page.getByText('Advanced settings').click()
  await expect(page.getByRole('radio', { name: /^Deep/ })).toBeChecked()
  await page.getByRole('radio', { name: /^Exhaustive/ }).check()
  await expect(page.getByText('40', { exact: true })).toBeVisible()
  await expect(page.getByText('link depth')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Find candidates' })).toBeEnabled()
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(hasOverflow).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('new-run.png'), fullPage: true })
})

test('outreach queue enforces visible human review controls', async ({ page }, testInfo) => {
  const consoleErrors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  await mockShell(page)
  await page.route('**/api/v1/runs', (route) => route.fulfill({ json: [runDetail.run] }))
  await page.route('**/api/v1/outreach/drafts', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{
      id: 'draft-review-test', run_id: 'run-review-test', lead_domain: 'harleystreet.example',
      recipient_email: 'hello@harleystreet.example', subscriber_type: 'corporate', consent_confirmed: false,
      lawful_basis_note: 'Public business contact evidence recorded for review.',
      subject: 'A note for Harley Street Dental Studio', body: 'A concise evidence-based outreach draft.',
      status: 'draft', approved_by: '', created_at: '2026-07-16T10:00:00Z',
    }]),
  }))
  await page.route('**/api/v1/compliance/suppressions', (route) => route.fulfill({ contentType: 'application/json', body: '[]' }))
  await page.goto('/outreach')
  await expect(page.getByRole('heading', { name: 'Outreach review' })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Draft creation mode' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Bulk campaign/ })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('Human approval before delivery')).toBeVisible()
  await expect(page.getByText('A note for Harley Street Dental Studio')).toBeVisible()
  const approve = page.getByRole('button', { name: 'Approve' })
  await expect(approve).toBeDisabled()
  await page.getByLabel('Reviewer').fill('QA Reviewer')
  await page.getByLabel('Corporate status checked').check()
  await page.getByLabel('Privacy notice checked').check()
  await expect(approve).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
  expect(consoleErrors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('outreach-review.png'), fullPage: false })
})
