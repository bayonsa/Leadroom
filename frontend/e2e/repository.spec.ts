import { expect, test, type Page } from '@playwright/test'

const leads = [
  {
    business_name: 'J Sons and Co.', website: 'https://jsonsco.com/', city_or_area: 'London', business_type: 'Contractor', services: ['Construction'],
    generic_email: 'info@jsonsco.com', emails: ['info@jsonsco.com', 'hello@jsonsco.com'], phone: '+44 20 8050 7969', phones: ['+44 20 8050 7969', '0800 043 2639'],
    contact_page: 'https://jsonsco.com/contact', booking_page: '', instagram_or_social: '', has_online_booking: false, website_quality_note: '', lead_score: 9,
    lead_reason: 'Verified public contact details.', domain: 'jsonsco.com', field_evidence: {}, enrichment_errors: [],
    niches: ['construction contractors'], locations: ['London UK'], sources: ['local', 'web'],
  },
  {
    business_name: 'Eden', website: 'https://edenbuild.co.uk/', city_or_area: 'Greater London', business_type: 'Builder', services: ['Renovation'],
    generic_email: 'info@edenbuild.co.uk', emails: ['info@edenbuild.co.uk'], phone: '0800 043 2639', phones: ['0800 043 2639'],
    contact_page: '', booking_page: '', instagram_or_social: '', has_online_booking: false, website_quality_note: '', lead_score: 9,
    lead_reason: 'Verified public contact details.', domain: 'edenbuild.co.uk', field_evidence: {}, enrichment_errors: [],
    niches: ['property developers'], locations: ['Greater London'], sources: ['web'],
  },
]

async function mockHealth(page: Page) {
  await page.route('**/api/v1/health', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok', database: 'ok' }) }))
}

test('candidate selection responds immediately and centers its check icon', async ({ page }) => {
  await mockHealth(page)
  let status = 'queued'
  await page.route('**/api/v1/runs/selection-test', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      run: { id: 'selection-test', run_name: 'selection_test', status: 'ready', counts: { queued: status === 'queued' ? 1 : 0 } },
      candidates: [{ title: 'Top Dental', url: 'https://topdental.example', homepage: 'https://topdental.example', snippet: 'Dental clinic', domain: 'topdental.example', status }],
      leads: [],
    }),
  }))
  await page.route('**/api/v1/runs/selection-test/candidates/topdental.example', async (route) => {
    const payload = await route.request().postDataJSON() as { selected: boolean }
    status = payload.selected ? 'queued' : 'cancelled'
    await new Promise((resolve) => setTimeout(resolve, 1000))
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ domain: 'topdental.example', selected: payload.selected }) })
  })

  await page.goto('/runs/selection-test')
  const candidate = page.locator('.candidate').filter({ hasText: 'Top Dental' })
  const checkbox = candidate.locator('input[type="checkbox"]')
  await expect(checkbox).toBeChecked()
  await checkbox.click()
  await expect(checkbox).not.toBeChecked({ timeout: 200 })

  const alignment = await candidate.evaluate((row) => {
    const mark = row.querySelector('.checkmark')!.getBoundingClientRect()
    const icon = row.querySelector('.checkmark svg')!.getBoundingClientRect()
    return {
      x: Math.abs(mark.left + mark.width / 2 - (icon.left + icon.width / 2)),
      y: Math.abs(mark.top + mark.height / 2 - (icon.top + icon.height / 2)),
      mark: [mark.width, mark.height],
      icon: [icon.width, icon.height],
    }
  })
  expect(alignment.mark).toEqual([20, 20])
  expect(alignment.icon).toEqual([14, 14])
  expect(alignment.x).toBeLessThanOrEqual(0.5)
  expect(alignment.y).toBeLessThanOrEqual(0.5)
})

test('recent runs expose stop, continue, and delete controls', async ({ page }) => {
  await mockHealth(page)
  let rows = [
    { id: 'active-run', run_name: 'active_search', status: 'searching', counts: {}, created_at: '2026-07-14T12:00:00Z', updated_at: '2026-07-14T12:01:00Z' },
    { id: 'stopped-run', run_name: 'stopped_search', status: 'stopped', counts: {}, created_at: '2026-07-14T11:00:00Z', updated_at: '2026-07-14T11:01:00Z' },
  ]
  await page.route('**/api/v1/runs', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(rows) }))
  await page.route('**/api/v1/runs/active-run/cancel', (route) => {
    rows = rows.map((run) => run.id === 'active-run' ? { ...run, status: 'stopped' } : run)
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(rows[0]) })
  })
  await page.route('**/api/v1/runs/stopped-run/continue', (route) => {
    rows = rows.map((run) => run.id === 'stopped-run' ? { ...run, status: 'searching' } : run)
    return route.fulfill({ contentType: 'application/json', status: 202, body: JSON.stringify({ run_id: 'stopped-run', status: 'accepted', kind: 'discovery' }) })
  })
  await page.route('**/api/v1/runs/stopped-run', (route) => {
    if (route.request().method() !== 'DELETE') return route.fallback()
    rows = rows.filter((run) => run.id !== 'stopped-run')
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'stopped-run', status: 'deleted' }) })
  })

  await page.goto('/runs')
  await expect(page.getByRole('link', { name: 'active_search' }).locator('.run-avatar')).toHaveText('A')
  await expect(page.getByRole('link', { name: 'stopped_search' }).locator('.run-avatar')).toHaveText('S')
  await expect(page.getByRole('button', { name: 'Stop active_search' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Continue stopped_search' })).toBeVisible()
  await page.getByRole('button', { name: 'Stop active_search' }).click()
  await expect(page.getByRole('button', { name: 'Continue active_search' })).toBeVisible()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete stopped_search' }).click()
  await expect(page.getByRole('link', { name: 'stopped_search' })).toHaveCount(0)
})

test('initial discovery opens a controllable search job', async ({ page }) => {
  await mockHealth(page)
  await page.route('**/api/v1/discovery/history?*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ previous_runs: 0, seen_domains: 0, completed_leads: 0 }) }))
  await page.route('**/api/v1/runs', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ run: { id: 'progress-run', run_name: 'progress_run', status: 'searching', counts: {} }, candidates: [], leads: [] }) })
  })
  await page.route('**/api/v1/runs/progress-run', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ run: { id: 'progress-run', run_name: 'progress_run', status: 'searching', counts: {} }, candidates: [], leads: [] }) }))

  await page.goto('/new')
  await page.getByLabel('Business niche').fill('independent salons')
  await expect(page.getByLabel('Run name')).toHaveValue(/^independent_salons_\d{8}_\d{6}_\d{3}$/)
  await page.getByRole('button', { name: 'Find candidates' }).click()

  await expect(page.getByText('Search in progress')).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Searching for candidates' })).toBeVisible()
  await expect(page.getByText('Contacting the search provider')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'progress_run' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stop' })).toBeVisible()
})

test('a completed run can save its lead batch to the repository', async ({ page }) => {
  await mockHealth(page)
  await page.route('**/api/v1/runs/repository-test', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ run: { id: 'repository-test', run_name: 'repository_test', status: 'completed', counts: { completed: 2 } }, candidates: leads.map((lead) => ({ title: lead.business_name, url: lead.website, homepage: lead.website, snippet: '', domain: lead.domain, status: 'completed' })), leads }),
  }))
  let importedDomains: string[] = []
  await page.route('**/api/v1/repository/import', async (route) => {
    importedDomains = (await route.request().postDataJSON()).domains
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ added: 2, updated: 0, total: 2 }) })
  })

  await page.goto('/runs/repository-test')
  await page.getByRole('tab', { name: /Leads/ }).click()
  const save = page.getByRole('button', { name: 'Save all 2' })
  await expect(save).toBeVisible()
  await save.click()

  expect(importedDomains).toEqual(['jsonsco.com', 'edenbuild.co.uk'])
  await expect(page.getByText('2 added, 0 updated')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open repository' })).toBeVisible()
})

test('a completed run can continue with the next search batch', async ({ page }, testInfo) => {
  await mockHealth(page)
  let phase: 'completed' | 'searching' | 'ready' = 'completed'
  let requestedSource = ''
  await page.route('**/api/v1/runs/continuation-test', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      run: { id: 'continuation-test', run_name: 'continuous_search', status: phase, counts: phase === 'ready' ? { completed: 2, queued: 1 } : { completed: 2 }, discovery: { mode: 'new_only', next_search_page: phase === 'ready' ? 3 : 2 } },
      candidates: [...leads.map((lead) => ({ title: lead.business_name, url: lead.website, homepage: lead.website, snippet: '', domain: lead.domain, status: 'completed' })), ...(phase === 'ready' ? [{ title: 'Third Lead', url: 'https://third.example/', homepage: 'https://third.example/', snippet: 'London business', domain: 'third.example', status: 'queued' }] : [])],
      leads,
    }),
  }))
  await page.route('**/api/v1/runs/continuation-test/discover-more?source=*', async (route) => {
    requestedSource = new URL(route.request().url()).searchParams.get('source') ?? ''
    phase = 'searching'
    setTimeout(() => { phase = 'ready' }, 700)
    await route.fulfill({ contentType: 'application/json', status: 202, body: JSON.stringify({ run_id: 'continuation-test', status: 'accepted', kind: 'discovery' }) })
  })

  await page.goto('/runs/continuation-test')
  await page.getByRole('button', { name: /Web 2/ }).click()
  const nextBatch = page.getByRole('button', { name: 'Search more web' })
  await expect(nextBatch).toBeVisible()
  await nextBatch.click()
  expect(requestedSource).toBe('web')

  await expect(page.getByText('Search in progress')).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Searching for candidates' })).toBeVisible()
  await expect(page.getByText('Third Lead')).toBeVisible()
  await expect(page.getByRole('button', { name: /Web 3/ })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('tab', { name: /Candidates/ })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('candidate-source-tabs.png'), fullPage: false })
})

test('repository presents merged contacts without page overflow', async ({ page }, testInfo) => {
  await mockHealth(page)
  await page.route('**/api/v1/repository', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ count: 2, leads: leads.map((lead, index) => ({ ...lead, source_run_ids: index ? ['run-2'] : ['run-1', 'run-2'], created_at: '2026-07-14T12:00:00Z', updated_at: '2026-07-14T13:00:00Z' })) }),
  }))

  await page.goto('/repository')
  await expect(page.getByRole('heading', { name: 'Repository' })).toBeVisible()
  await expect(page.getByText('+44 20 8050 7969')).toBeVisible()
  await expect(page.getByText('hello@jsonsco.com')).toBeVisible()
  await expect(page.getByText('2 runs')).toBeVisible()
  await expect(page.getByRole('cell', { name: /construction contractors/ })).toBeVisible()
  await expect(page.getByRole('img', { name: 'Local file' })).toHaveAttribute('title', 'This lead includes local database evidence')
  await page.getByLabel('Filter by source').selectOption('local')
  await expect(page.getByText('1 leads')).toBeVisible()
  await expect(page.getByText('J Sons and Co.')).toBeVisible()
  await page.getByLabel('Filter by source').selectOption('')
  await page.getByLabel('Search saved leads').fill('Eden')
  await expect(page.getByText('1 leads')).toBeVisible()
  await page.getByLabel('Search saved leads').fill('')
  await page.getByRole('button', { name: /Collection All leads/i }).click()
  const picker = page.getByRole('dialog', { name: 'Choose collections' })
  await picker.getByLabel('Search collections').fill('property')
  await picker.getByRole('checkbox', { name: /property developers/i }).check()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Collection property developers', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Eden edenbuild.co.uk' })).toBeVisible()
  await expect(page.getByText('J Sons and Co.')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
  await page.screenshot({ path: testInfo.outputPath(`repository-${testInfo.project.name}.png`), fullPage: true })
})

test('repository lead can be edited, moved, and removed from its row', async ({ page }) => {
  await mockHealth(page)
  let savedLead = { ...leads[0], source_run_ids: ['run-1'], created_at: '2026-07-14T12:00:00Z', updated_at: '2026-07-14T13:00:00Z' }
  let updatePayload: Record<string, unknown> = {}
  await page.route('**/api/v1/repository', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ count: 1, leads: [savedLead] }) }))
  await page.route('**/api/v1/repository/jsonsco.com', async (route) => {
    updatePayload = await route.request().postDataJSON()
    savedLead = { ...savedLead, niches: [String(updatePayload.collection)] }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(savedLead) })
  })

  await page.goto('/repository')
  await expect(page.getByRole('button', { name: 'Edit jsonsco.com' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove jsonsco.com' })).toBeVisible()
  await page.getByRole('button', { name: 'Move jsonsco.com', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'J Sons and Co.' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('combobox', { name: 'Collection' }).fill('dental clinics')
  await page.getByRole('button', { name: 'Move lead' }).click()

  expect(updatePayload).toEqual({ collection: 'dental clinics' })
  await page.getByRole('button', { name: /Collection All leads/i }).click()
  await expect(page.getByRole('checkbox', { name: /dental clinics/i })).toBeVisible()
})

test('collection manager merges categories without deleting leads', async ({ page }) => {
  await mockHealth(page)
  let repositoryLeads = leads.map((lead, index) => ({ ...lead, source_run_ids: [`run-${index}`], created_at: '2026-07-14T12:00:00Z', updated_at: '2026-07-14T13:00:00Z' }))
  let mergePayload: Record<string, unknown> = {}
  await page.route('**/api/v1/repository', (route) => route.fulfill({ json: { count: repositoryLeads.length, leads: repositoryLeads } }))
  await page.route('**/api/v1/repository/collections/merge', async (route) => {
    mergePayload = await route.request().postDataJSON()
    const sources = mergePayload.sources as string[]
    repositoryLeads = repositoryLeads.map((lead) => sources.some((source) => lead.niches.includes(source)) ? { ...lead, niches: [String(mergePayload.target)] } : lead)
    await route.fulfill({ json: { status: 'merged', sources, target: mergePayload.target, updated_leads: 2 } })
  })

  await page.goto('/repository')
  await page.getByRole('button', { name: 'Manage collections' }).click()
  const manager = page.getByRole('dialog', { name: 'Manage collections' })
  await manager.getByRole('checkbox', { name: /construction contractors/i }).check()
  await manager.getByRole('checkbox', { name: /property developers/i }).check()
  await manager.getByLabel('Target collection name').fill('Building services')
  await manager.getByRole('button', { name: 'Merge' }).click()

  expect(mergePayload).toEqual({ sources: ['construction contractors', 'property developers'], target: 'Building services' })
  await expect(manager.getByText('Building services')).toBeVisible()
  await expect(manager.getByText('1 total')).toBeVisible()
})

test('collection picker stays compact with one thousand categories', async ({ page }) => {
  await mockHealth(page)
  const categories = Array.from({ length: 1000 }, (_, index) => `Category ${String(index).padStart(4, '0')}`)
  const lead = { ...leads[0], niches: categories, source_run_ids: ['run-scale'], created_at: '2026-07-14T12:00:00Z', updated_at: '2026-07-14T13:00:00Z' }
  await page.route('**/api/v1/repository', (route) => route.fulfill({ json: { count: 1, leads: [lead] } }))

  await page.goto('/repository')
  await page.getByRole('button', { name: /Collection All leads/i }).click()
  const picker = page.getByRole('dialog', { name: 'Choose collections' })
  await expect(picker.getByRole('checkbox')).toHaveCount(100)
  await expect(picker.getByText('Showing 100 of 1000')).toBeVisible()
  await picker.getByLabel('Search collections').fill('Category 0999')
  await expect(picker.getByRole('checkbox', { name: /Category 0999/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
})
