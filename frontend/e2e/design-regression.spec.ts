import { expect, test } from '@playwright/test'
import { mockRunWorkspace, mockWorkspaceData, runDetail, runName } from './run-fixture'

test('workspace opens with content and advanced controls stay progressive', async ({ page }, testInfo) => {
  await mockWorkspaceData(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible()

  await page.goto('/new')
  const bothSource = page.getByRole('radio', { name: /Both/ })
  const localSource = page.getByRole('radio', { name: /Local/ })
  const webSource = page.getByRole('radio', { name: /Web/ })
  await expect(bothSource).toBeChecked()
  await page.getByText('Local', { exact: true }).click()
  await expect(localSource).toBeChecked()
  await expect(page.getByText(/continue without a total limit/)).toBeVisible()
  await page.getByText('Web', { exact: true }).click()
  await expect(webSource).toBeChecked()
  await bothSource.check({ force: true })
  const advanced = page.getByText('Advanced settings', { exact: true })
  await expect(advanced).toBeVisible()
  await expect(page.getByLabel('Results per search')).toBeHidden()
  await advanced.click()
  await expect(page.getByLabel('Results per search')).toBeVisible()
  await expect(page.getByText('Local + web', { exact: true })).toBeVisible()
  await expect(page.getByText('Local and internet results are deduplicated and merged.')).toBeVisible()
  await expect(page.getByText('Find up to 10 candidates for review')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('source-selection.png'), fullPage: true })
})

test('run tabs expose selected state and the lead drawer behaves as a dialog', async ({ page }, testInfo) => {
  await page.route(/\/api\/v1\/runs\/[^/]+$/, async (route) => {
    const response = await route.fetch()
    const detail = await response.json()
    if (detail.candidates?.[0]) detail.candidates[0].snippet = 'office graphic design | 90â€“92 Pentonville Road'
    await route.fulfill({ response, json: detail })
  })
  await mockRunWorkspace(page)
  runDetail.candidates[0].snippet = 'office graphic design | 90–92 Pentonville Road'
  await page.goto('/runs')
  await page.getByRole('link', { name: runName, exact: true }).click()

  const candidatesTab = page.getByRole('tab', { name: /Candidates/ })
  const leadsTab = page.getByRole('tab', { name: /Leads/ })
  await expect(candidatesTab).toHaveAttribute('aria-selected', 'true')
  const candidate = page.locator('.candidate').first()
  await expect(candidate).toBeVisible()
  await expect(candidate).toContainText('90–92 Pentonville Road')
  await expect(candidate).not.toContainText('â€“')
  const webEvidence = candidate.getByRole('img', { name: 'Web result' })
  await expect(webEvidence).toHaveAttribute('title', 'This result comes from the web')
  const candidateBox = await candidate.boundingBox()
  expect(candidateBox?.height).toBeLessThanOrEqual(72)
  expect(await candidate.evaluate((row) => row.scrollWidth <= row.clientWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('compact-candidates.png'), fullPage: false })
  await leadsTab.click()
  await expect(leadsTab).toHaveAttribute('aria-selected', 'true')

  await page.getByRole('button', { name: /Harley Street Dental Studio/ }).click()
  const drawer = page.getByRole('dialog', { name: 'Harley Street Dental Studio' })
  await expect(drawer).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close details' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
})

test('mobile navigation has an explicit dismiss layer', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/new')
  const menu = page.getByRole('button', { name: 'Toggle navigation' })
  await menu.click()
  await expect(menu).toHaveAttribute('aria-expanded', 'true')
  await page.getByRole('button', { name: 'Close navigation' }).click()
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
})

test('local data engine reports coverage and returns a private-index result', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await mockWorkspaceData(page)
  await page.route('**/api/v1/local-data/status', (route) => route.fulfill({ json: {
    ready: true, database: 'online', engine: 'PostgreSQL + PostGIS', dataset: 'OpenStreetMap Great Britain',
    businesses: 5, with_website: 3, with_phone: 2, with_email: 1, message: 'Local discovery is ready.',
  } }))
  await page.route('**/api/v1/local-data/preview**', (route) => route.fulfill({ json: {
    count: 1, elapsed_ms: 42, results: [{ title: 'Elm Beauty Rooms', domain: 'osm-N-42', source: 'osm_local',
      source_id: 'osm-N-42', url: '', homepage: '', snippet: 'shop beauty', business_name: 'Elm Beauty Rooms',
      business_type: 'shop beauty', city_or_area: 'London', address: '', phone: '020 7946 0102', email: '',
      latitude: '51.51', longitude: '-0.14', osm_url: 'https://www.openstreetmap.org/node/42' }],
  } }))
  await page.goto('/local-data')
  await expect(page.getByRole('heading', { name: 'Local data engine' })).toBeVisible()
  await expect(page.getByText('Index online')).toBeVisible()
  await expect(page.locator('.engine-metrics').getByText('5', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Run local query' }).click()
  await expect(page.getByText('Elm Beauty Rooms')).toBeVisible()
  await expect(page.getByText('1 matches')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  expect(errors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('local-data.png'), fullPage: true })
})
