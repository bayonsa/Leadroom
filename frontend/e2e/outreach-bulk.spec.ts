import { expect, test } from '@playwright/test'

test('builds and approves an outreach batch without repeating lead forms', async ({ page }, testInfo) => {
  const consoleErrors: string[] = []
  const createdPayloads: Array<Record<string, unknown>> = []
  const approvalPayloads: Array<Record<string, unknown>> = []
  const sendPayloads: Array<Record<string, unknown>> = []
  let drafts: Array<Record<string, unknown>> = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })

  await page.route('**/api/v1/health', (route) => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
  await page.route('**/api/v1/settings', (route) => route.fulfill({ json: { workspace_name: 'Leadroom', workspace_subtitle: 'Signal desk', logo_data_url: '', email_configured: true, email_accounts: [{ id: 'sales-mailbox', label: 'Northstar Sales', from_email: 'sales@northstar.example', is_default: true }], default_email_account_id: 'sales-mailbox' } }))
  await page.route('**/api/v1/settings/email-accounts', (route) => route.fulfill({ json: { accounts: [{ id: 'sales-mailbox', label: 'Northstar Sales', host: 'smtp.example.test', port: 587, security: 'starttls', username: 'sales@northstar.example', password_configured: true, from_email: 'sales@northstar.example', from_name: 'Northstar Sales', reply_to: '', is_default: true }], default_account_id: 'sales-mailbox' } }))
  await page.route('**/api/v1/runs', (route) => route.fulfill({ json: [{ id: 'run-bulk', run_name: 'London dental clinics', status: 'completed', counts: { completed: 3 }, created_at: '2026-07-16T10:00:00Z' }] }))
  await page.route('**/api/v1/compliance/suppressions', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/outreach/preflight', async (route) => {
    expect((await route.request().postDataJSON()).run_id).toBe('run-bulk')
    await route.fulfill({ json: { run_id: 'run-bulk', total: 3, eligible: 2, blocked: 1, results: [
      { domain: 'alpha.example', business_name: 'Alpha Dental', email: 'info@alpha.example', lead_score: 9, eligible: true, reasons: [] },
      { domain: 'beta.example', business_name: 'Beta Dental', email: 'hello@beta.example', lead_score: 8, eligible: true, reasons: [] },
      { domain: 'blocked.example', business_name: 'Blocked Dental', email: '', lead_score: 4, eligible: false, reasons: ['No verified email', 'Lead score is below 7'] },
    ] } })
  })
  await page.route('**/api/v1/outreach/drafts/bulk', async (route) => {
    const payload = await route.request().postDataJSON()
    createdPayloads.push(payload)
    drafts = (payload.domains as string[]).map((domain, index) => ({
      id: `draft-${index}`, run_id: 'run-bulk', lead_domain: domain,
      recipient_email: domain === 'alpha.example' ? 'info@alpha.example' : 'hello@beta.example',
      subscriber_type: 'corporate', consent_confirmed: false, lawful_basis_note: payload.lawful_basis_note,
      subject: `Introduction for ${domain}`, body: 'Evidence-based outreach message.', status: 'draft', approved_by: '', created_at: '2026-07-16T10:00:00Z',
    }))
    await route.fulfill({ status: 201, json: { created: 2, skipped: 0, drafts, errors: [] } })
  })
  await page.route('**/api/v1/outreach/drafts/approve-bulk', async (route) => {
    const payload = await route.request().postDataJSON()
    approvalPayloads.push(payload)
    drafts = drafts.map((draft) => ({ ...draft, status: 'approved', approved_by: payload.reviewed_by }))
    await route.fulfill({ json: { approved: drafts.length, drafts } })
  })
  await page.route('**/api/v1/outreach/drafts', (route) => route.fulfill({ json: drafts }))
  await page.route('**/api/v1/outreach/send/job-test', (route) => {
    drafts = drafts.map((draft) => ({ ...draft, status: 'sent', delivery_status: 'sent', provider_message_id: '<sent@example.test>' }))
    return route.fulfill({ json: { id: 'job-test', status: 'completed', message: 'Sent 2 of 2 emails.', total: 2, completed: 2, sent: 2, failed: 0, percent: 100, current_draft_id: '', stop_requested: false, results: [] } })
  })
  await page.route('**/api/v1/outreach/send', async (route) => {
    sendPayloads.push(await route.request().postDataJSON())
    drafts = drafts.map((draft) => ({ ...draft, status: 'queued' }))
    return route.fulfill({ status: 202, json: { id: 'job-test', status: 'queued', message: 'Waiting to send', total: 2, completed: 0, sent: 0, failed: 0, percent: 0, current_draft_id: '', stop_requested: false, results: [] } })
  })

  await page.goto('/outreach')
  await expect(page.getByRole('button', { name: /Bulk campaign/ })).toHaveAttribute('aria-pressed', 'true')
  await page.getByLabel('Source run').selectOption('run-bulk')
  await page.getByLabel('Subscriber type').selectOption('corporate')
  await page.getByLabel('Sender identity').fill('Northstar Studio')
  await page.getByLabel('Lawful-basis note').fill('Public corporate contact details verified on the business website.')
  await page.getByLabel('Opt-out address').fill('privacy@northstar.example')
  await page.getByLabel('Base message').fill('A relevant service introduction for London dental practices.')
  await page.getByLabel('Tone').selectOption('warm')
  await page.getByLabel('Links').fill('https://northstar.example/opt-in\nhttps://northstar.example/case-study')
  await page.getByRole('button', { name: 'Check eligibility' }).click()

  await expect(page.getByText('Alpha Dental')).toBeVisible()
  await expect(page.getByText('No verified email / Lead score is below 7')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create 2 drafts' })).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
  await page.getByRole('button', { name: 'Create 2 drafts' }).click()
  await expect(page.getByText('Introduction for alpha.example')).toBeVisible()
  expect(createdPayloads[0].domains).toEqual(['alpha.example', 'beta.example'])
  expect(createdPayloads[0]).toMatchObject({ tone: 'warm', ai_personalize: true, links: ['https://northstar.example/opt-in', 'https://northstar.example/case-study'] })

  const selectors = page.locator('.audit-selector input:not(:disabled)')
  await selectors.nth(0).check()
  await selectors.nth(1).check()
  await expect(page.getByText('2 selected')).toBeVisible()
  await page.locator('.bulk-audit-toolbar').getByLabel('Reviewer').fill('Campaign Reviewer')
  await page.locator('.bulk-audit-toolbar').getByLabel('Status checked').check()
  await page.locator('.bulk-audit-toolbar').getByLabel('Privacy checked').check()
  await page.getByRole('button', { name: 'Approve 2' }).click()
  expect(approvalPayloads[0].draft_ids).toEqual(['draft-0', 'draft-1'])
  await expect(page.getByText('2 selected')).toBeHidden()
  await selectors.nth(0).check()
  await selectors.nth(1).check()
  await page.getByRole('button', { name: 'Send 2' }).click()
  await expect(page.getByText('Sent 2 of 2 emails.')).toBeVisible()
  expect(sendPayloads[0]).toMatchObject({ draft_ids: ['draft-0', 'draft-1'], email_account_id: 'sales-mailbox' })
  expect(consoleErrors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('bulk-outreach.png'), fullPage: false })
})
