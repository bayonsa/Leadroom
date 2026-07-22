import type { Page } from '@playwright/test'

export const runName = 'london_dental_review'
export const runId = 'run-review-test'

export const runDetail = {
  run: {
    id: runId, run_name: runName, status: 'completed',
    counts: { candidates: 1, selected: 1, completed: 1, failed: 0 },
    created_at: '2026-07-16T10:00:00Z', updated_at: '2026-07-16T10:05:00Z',
  },
  candidates: [{
    title: 'Harley Street Dental Studio', url: 'https://harleystreet.example',
    homepage: 'https://harleystreet.example', domain: 'harleystreet.example',
    snippet: 'Dental clinic | 90-92 Harley Street | London', status: 'completed', source: 'web', sources: ['web'],
    crawl_mode: 'deep', crawl_pages_checked: 7, crawl_page_limit: 20, crawl_contacts_found: 2,
  }],
  leads: [{
    business_name: 'Harley Street Dental Studio', website: 'https://harleystreet.example',
    city_or_area: 'London', business_type: 'Dental clinic', services: ['Dental implants'],
    generic_email: 'hello@harleystreet.example', emails: ['hello@harleystreet.example'],
    phone: '020 7946 0123', phones: ['020 7946 0123'], contact_page: 'https://harleystreet.example/contact',
    booking_page: '', instagram_or_social: '', has_online_booking: false,
    website_quality_note: 'Clear services and contact details.', lead_score: 9,
    lead_reason: 'Verified business contact details.', domain: 'harleystreet.example', enrichment_errors: [],
    field_evidence: { generic_email: { value: 'hello@harleystreet.example', source_url: 'https://harleystreet.example/contact', method: 'html_mailto' } },
  }],
}

export async function mockShell(page: Page) {
  await page.route('**/api/v1/health', (route) => route.fulfill({ json: { status: 'ok', database: 'ok' } }))
  await page.route('**/api/v1/settings/email-accounts', (route) => route.fulfill({ json: { accounts: [], default_account_id: '' } }))
  await page.route('**/api/v1/settings', (route) => route.fulfill({ json: {
    workspace_name: 'Leadroom', workspace_subtitle: 'Signal desk', logo_data_url: '',
    theme: 'brushstroke', email_configured: false, email_accounts: [], default_email_account_id: '', default_model: 'ollama/llama3.2:3b',
    model_provider: 'ollama', model_name: 'llama3.2:3b', model_endpoint: 'http://localhost:11434',
    api_key_configured: false, smtp_password_configured: false, blocked_domains: [],
    limits: { max_results_per_query: 100, max_sites: 500 }, search_providers: ['hybrid', 'osm_local', 'auto'],
  } }))
}

export async function mockWorkspaceData(page: Page) {
  await mockShell(page)
  await page.route('**/api/v1/runs', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/repository', (route) => route.fulfill({ json: { count: 1, leads: [{
    business_name: 'Example Salon', domain: 'example.com', website: 'https://example.com',
    city_or_area: 'London', emails: ['info@example.com'], phones: ['020 1234 5678'],
    niches: ['salons'], locations: ['London'], sources: ['web'], source_run_ids: ['run-example'],
    lead_score: 8, created_at: '2026-07-16T10:00:00Z', updated_at: '2026-07-16T10:00:00Z',
  }] } }))
  await page.route('**/api/v1/compliance/suppressions', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/outreach/drafts', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/local-data/status', (route) => route.fulfill({ json: {
    ready: true, database: 'online', engine: 'PostgreSQL + PostGIS', dataset: 'OpenStreetMap Great Britain',
    businesses: 5, with_website: 3, with_phone: 2, with_email: 1, message: 'Local discovery is ready.',
    update_status: 'idle', update_schedule: 'Daily',
  } }))
  await page.route('**/api/v1/settings/ollama/models', (route) => route.fulfill({ json: { models: [] } }))
  await page.route('**/api/v1/settings/ollama/catalog', (route) => route.fulfill({ json: { models: [] } }))
}

export async function mockRunWorkspace(page: Page) {
  await mockShell(page)
  await page.route('**/api/v1/runs', (route) => route.fulfill({ json: [runDetail.run] }))
  await page.route(`**/api/v1/runs/${runId}`, async (route) => {
    return route.fulfill({ json: runDetail })
  })
  await page.route(`**/api/v1/runs/${runId}/leads/harleystreet.example`, (route) => (
    route.fulfill({ json: runDetail.leads[0] })
  ))
}
