import { expect, test, type Page } from '@playwright/test'

const initialSettings = {
  model_provider: 'ollama', model_name: 'llama3.2:3b', default_model: 'ollama/llama3.2:3b',
  model_endpoint: 'http://localhost:11434', ollama_base_url: 'http://localhost:11434', api_key_configured: false,
  blocked_domains: ['github.com', 'wikipedia.org'], workspace_name: 'Leadroom', workspace_subtitle: 'Signal desk', logo_data_url: '', theme: 'brushstroke',
  smtp_host: '', smtp_port: 587, smtp_security: 'starttls', smtp_username: '', smtp_password_configured: false,
  smtp_from_email: '', smtp_from_name: '', smtp_reply_to: '', email_accounts: [], default_email_account_id: '', email_configured: false,
}

async function mockSettings(page: Page) {
  let current = { ...initialSettings }
  let emailAccounts: Array<Record<string, unknown>> = []
  let pullPolls = 0
  const savedPayloads: Record<string, unknown>[] = []
  let storage = {
    data_root: 'C:\\Users\\Test\\AppData\\Local\\Leadroom', downloads_root: 'C:\\Users\\Test\\AppData\\Local\\LeadroomDownloads', active_data_root: 'C:\\Users\\Test\\AppData\\Local\\Leadroom',
    database_path: 'C:\\Users\\Test\\AppData\\Local\\Leadroom\\lead_scraper.db', database_exists: true, database_bytes: 12_500_000, workspace_bytes: 18_000_000,
    cache_dir: 'C:\\Users\\Test\\AppData\\Local\\LeadroomDownloads\\cache', browser_dir: 'C:\\Users\\Test\\AppData\\Local\\LeadroomDownloads\\playwright', ollama_dir: 'C:\\Users\\Test\\AppData\\Local\\LeadroomDownloads\\ollama\\models',
    data_disk: { free_bytes: 150_000_000_000, total_bytes: 500_000_000_000 }, downloads_disk: { free_bytes: 700_000_000_000, total_bytes: 1_000_000_000_000 }, restart_required: false, ollama_restart_required: false,
  }
  await page.route('**/api/v1/health', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok', database: 'ok' }) }))
  await page.route('**/api/v1/local-data/status', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ready: true, database: 'online', message: 'Local discovery is ready.', businesses: 1200, with_website: 800, with_phone: 900, with_email: 240, dataset: 'OpenStreetMap Great Britain', update_status: 'idle', update_schedule: 'Daily at 03:30' }) }))
  await page.route('**/api/v1/settings/storage/browse', (route) => route.fulfill({ json: { path: 'D:\\Leadroom' } }))
  await page.route('**/api/v1/settings/storage', async (route) => {
    if (route.request().method() === 'PUT') {
      const payload = await route.request().postDataJSON()
      storage = { ...storage, ...payload, database_path: `${payload.data_root}\\lead_scraper.db`, restart_required: true, ollama_restart_required: true }
    }
    await route.fulfill({ json: storage })
  })
  await page.route('**/api/v1/settings/ollama/models', (route) => route.fulfill({ json: { status: 'ok', endpoint: 'http://localhost:11434', selected_model: current.model_name, models: [
    { name: 'llama3.2:3b', size: 2_000_000_000, details: { parameter_size: '3.2B', quantization_level: 'Q4_K_M' } },
    { name: 'qwen2.5:7b', size: 4_700_000_000, details: { parameter_size: '7.6B', quantization_level: 'Q4_K_M' } },
  ] } }))
  await page.route('**/api/v1/settings/ollama/catalog?*', (route) => route.fulfill({ json: { status: 'ok', selected_model: current.model_name, installed: ['llama3.2:3b', 'qwen2.5:7b'], models: [
    { name: 'gemma3', family: 'gemma3', description: 'A capable local model family.', capabilities: ['vision'], variants: ['4b', '12b'], cloud: false, local: true, url: 'https://ollama.com/library/gemma3' },
    { name: 'glm-cloud', family: 'glm-cloud', description: 'Cloud only.', capabilities: ['tools'], variants: [], cloud: true, local: false, url: 'https://ollama.com/library/glm-cloud' },
  ] } }))
  await page.route('**/api/v1/settings/ollama/pull', (route) => route.fulfill({ status: 202, json: { id: 'pull-test', model: 'gemma3:4b', status: 'queued', message: 'Waiting to download', completed: 0, total: 0, percent: 0, error: '' } }))
  await page.route('**/api/v1/settings/ollama/pulls/pull-test', (route) => { pullPolls += 1; const done = pullPolls > 1; return route.fulfill({ json: { id: 'pull-test', model: 'gemma3:4b', status: done ? 'completed' : 'downloading', message: done ? 'Model installed' : 'Downloading model', completed: done ? 100 : 45, total: 100, percent: done ? 100 : 45, error: '' } }) })
  await page.route('**/api/v1/settings/ollama/benchmark', (route) => route.fulfill({ json: { model: 'qwen2.5:7b', score: 9, verdict: 'recommended', duration_seconds: 4.2, tokens_per_second: 31.5, checks: [
    { label: 'Valid structured output', passed: true, points: 2 }, { label: 'Business name', passed: true, points: 2 }, { label: 'Email accuracy', passed: true, points: 2 }, { label: 'Phone accuracy', passed: true, points: 1 }, { label: 'Location accuracy', passed: true, points: 1 }, { label: 'Services accuracy', passed: false, points: 2 },
  ], sample: {} } }))
  await page.route('**/api/v1/settings/test-email', (route) => route.fulfill({ json: { status: 'ok', provider: 'smtp' } }))
  await page.route('**/api/v1/settings/email-accounts/**', async (route) => {
    const accountId = route.request().url().split('/email-accounts/')[1].split('/')[0]
    const account = emailAccounts.find((item) => item.id === accountId)
    if (route.request().url().endsWith('/test')) return route.fulfill({ json: { status: 'ok', account_id: accountId, label: account?.label, sender: account?.from_email } })
    if (route.request().url().endsWith('/default')) emailAccounts = emailAccounts.map((item) => ({ ...item, is_default: item.id === accountId }))
    else if (route.request().method() === 'DELETE') emailAccounts = emailAccounts.filter((item) => item.id !== accountId)
    else if (route.request().method() === 'PUT') {
      const payload = await route.request().postDataJSON()
      emailAccounts = emailAccounts.map((item) => item.id === accountId ? { ...item, ...payload, password_configured: Boolean(payload.password) || item.password_configured } : item)
    }
    const defaultAccount = emailAccounts.find((item) => item.is_default) ?? emailAccounts[0]
    if (defaultAccount) emailAccounts = emailAccounts.map((item) => ({ ...item, is_default: item.id === defaultAccount.id }))
    return route.fulfill({ json: { accounts: emailAccounts, default_account_id: defaultAccount?.id ?? '' } })
  })
  await page.route('**/api/v1/settings/email-accounts', async (route) => {
    if (route.request().method() === 'POST') {
      const payload = await route.request().postDataJSON()
      const account = { ...payload, id: `sender-${emailAccounts.length + 1}`, password: undefined, password_configured: Boolean(payload.password), is_default: emailAccounts.length === 0 }
      emailAccounts = [...emailAccounts, account]
    }
    const defaultAccount = emailAccounts.find((item) => item.is_default) ?? emailAccounts[0]
    return route.fulfill({ json: { accounts: emailAccounts, default_account_id: defaultAccount?.id ?? '' } })
  })
  await page.route('**/api/v1/settings', async (route) => {
    if (route.request().method() === 'PUT') {
      const savedPayload = await route.request().postDataJSON()
      savedPayloads.push(savedPayload)
      const payload = savedPayload as typeof savedPayload & { model_provider: string; model_name: string; model_endpoint: string; blocked_domains: string[]; workspace_name: string; workspace_subtitle: string; logo_data_url: string; api_key?: string }
      current = { ...current, ...payload, workspace_name: payload.workspace_name.trim() || 'Leadroom', workspace_subtitle: payload.workspace_subtitle.trim() || 'Signal desk', default_model: `${payload.model_provider === 'ollama' ? 'ollama' : 'oneapi'}/${payload.model_name}`, api_key_configured: Boolean(payload.api_key) }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(current) })
  })
  await page.route('**/api/v1/settings/theme', async (route) => {
    const payload = await route.request().postDataJSON() as { theme: typeof current.theme }
    current = { ...current, theme: payload.theme }
    await route.fulfill({ json: current })
  })
  return () => savedPayloads
}

async function contrastRatio(page: Page, selector: string) {
  return page.locator(selector).first().evaluate((element) => {
    const channels = (value: string) => (value.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number)
    const luminance = (value: string) => {
      const [red, green, blue] = channels(value).map((channel) => {
        const normalized = channel / 255
        return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * red + 0.7152 * green + 0.0722 * blue
    }
    const foreground = getComputedStyle(element).color
    let backgroundElement: Element | null = element
    let background = 'rgba(0, 0, 0, 0)'
    while (backgroundElement) {
      background = getComputedStyle(backgroundElement).backgroundColor
      const backgroundChannels = background.match(/[\d.]+/g) ?? []
      if (backgroundChannels.length < 4 || Number(backgroundChannels[3]) > 0) break
      backgroundElement = backgroundElement.parentElement
    }
    const light = Math.max(luminance(foreground), luminance(background))
    const dark = Math.min(luminance(foreground), luminance(background))
    return { ratio: (light + 0.05) / (dark + 0.05), foreground, background }
  })
}

for (const viewport of [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`email delivery settings save and test safely on ${viewport.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await mockSettings(page)
    await page.goto('/settings')

    const emailSettings = page.locator('.email-settings')
    await emailSettings.getByLabel('Account label').fill('Northstar Sales')
    await emailSettings.getByLabel('SMTP host').fill('smtp.example.test')
    await emailSettings.getByLabel('Username').fill('sender@example.test')
    await emailSettings.getByLabel('Password or app password').fill('app-password')
    await emailSettings.getByLabel('Sender name').fill('Northstar Studio')
    await emailSettings.getByLabel('From email').fill('sender@example.test')
    await emailSettings.getByLabel('Reply-to').fill('privacy@example.test')
    await emailSettings.getByRole('button', { name: 'Add account' }).click()

    await expect(emailSettings.getByRole('button', { name: /Northstar Sales/ })).toHaveAttribute('aria-pressed', 'true')
    await expect(emailSettings.getByText('Default sender')).toBeVisible()
    await emailSettings.getByRole('button', { name: 'Test account' }).click()
    await expect(emailSettings.getByText('Connection verified')).toBeVisible()
    await expect(emailSettings.getByText('sender@example.test is ready to send.')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
    await emailSettings.screenshot({ path: testInfo.outputPath(`email-accounts-${viewport.name}.png`) })
  })
}

test('theme selection applies immediately and persists', async ({ page }, testInfo) => {
  await mockSettings(page)
  await page.goto('/settings')

  await expect(page.getByRole('radio', { name: /Brushstroke/ })).toHaveAttribute('aria-checked', 'true')
  const initialLayoutY = await page.locator('.settings-layout').evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
  await page.getByRole('radio', { name: /Genesis/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'genesis')
  expect((await contrastRatio(page, '.eyebrow')).ratio).toBeGreaterThanOrEqual(4.5)
  await expect(page.getByText('Settings saved')).toBeVisible()
  const changedLayoutY = await page.locator('.settings-layout').evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
  expect(Math.abs(changedLayoutY - initialLayoutY)).toBeLessThanOrEqual(1)
  await expect(page.getByText('Settings saved')).toHaveCSS('position', 'fixed')
  await page.screenshot({ path: testInfo.outputPath('genesis-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /Flip7/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'flip7')
  const flip7PrimaryContrast = await contrastRatio(page, '.button.primary')
  expect(flip7PrimaryContrast.ratio, JSON.stringify(flip7PrimaryContrast)).toBeGreaterThanOrEqual(4.5)
  await page.screenshot({ path: testInfo.outputPath('flip7-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /RawBlock/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'rawblock')
  await page.screenshot({ path: testInfo.outputPath('rawblock-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /Evreghen/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'evreghen')
  await page.screenshot({ path: testInfo.outputPath('evreghen-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /Ember Studio/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'ember')
  await expect(page.locator('html')).not.toHaveClass(/theme-transitioning/)
  await page.waitForTimeout(250)
  await page.screenshot({ path: testInfo.outputPath('ember-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /InsightDeck/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'insightdeck')
  await page.screenshot({ path: testInfo.outputPath('insightdeck-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /Trust Blue Pay/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'trustblue')
  await expect(page.locator('html')).not.toHaveClass(/theme-transitioning/)
  await page.waitForTimeout(250)
  const trustBlueContrast = await contrastRatio(page, '.button.primary')
  expect(trustBlueContrast.ratio, JSON.stringify(trustBlueContrast)).toBeGreaterThanOrEqual(4.5)
  await page.screenshot({ path: testInfo.outputPath('trustblue-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /ZenGrid/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'zengrid')
  await expect(page.locator('html')).not.toHaveClass(/theme-transitioning/)
  await page.waitForTimeout(250)
  const zenGridContrast = await contrastRatio(page, '.button.primary')
  expect(zenGridContrast.ratio, JSON.stringify(zenGridContrast)).toBeGreaterThanOrEqual(4.5)
  await page.screenshot({ path: testInfo.outputPath('zengrid-settings.png'), fullPage: true })

  await page.getByRole('radio', { name: /Vercel Interface/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'vercel')
  await page.screenshot({ path: testInfo.outputPath('vercel-settings.png'), fullPage: true })

  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'vercel')
  await expect(page.getByRole('radio', { name: /Vercel Interface/ })).toHaveAttribute('aria-checked', 'true')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
})

test('reduced motion disables indefinite progress animation', async ({ page }) => {
  await mockSettings(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/settings')
  const animationNames = await page.evaluate(() => {
    const spinner = document.createElement('span')
    spinner.className = 'spin'
    const progress = document.createElement('div')
    progress.className = 'search-progress-track'
    progress.innerHTML = '<span></span>'
    document.body.append(spinner, progress)
    const names = [getComputedStyle(spinner).animationName, getComputedStyle(progress.firstElementChild!).animationName]
    spinner.remove()
    progress.remove()
    return names
  })
  expect(animationNames).toEqual(['none', 'none'])
})

test('empty workspace identity falls back to brand defaults', async ({ page }) => {
  await mockSettings(page)
  await page.goto('/settings')

  await page.getByLabel('Workspace name').fill('   ')
  await page.getByLabel('Subtitle').fill('')
  await page.getByRole('button', { name: 'Save changes' }).click()

  await expect(page.getByLabel('Workspace name')).toHaveValue('Leadroom')
  await expect(page.getByLabel('Subtitle')).toHaveValue('Signal desk')
  await expect(page.getByText('Settings saved')).toBeVisible()
  await expect(page.getByText('Invalid request')).toHaveCount(0)
  await expect(page.getByText('Settings saved')).toBeHidden({ timeout: 5000 })
})

for (const viewport of [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`storage locations can be selected without horizontal overflow on ${viewport.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await mockSettings(page)
    await page.goto('/settings')

    const panel = page.locator('.storage-settings')
    await expect(panel.getByRole('heading', { name: 'Storage' })).toBeVisible()
    await panel.getByRole('button', { name: 'Browse' }).first().click()
    await expect(panel.locator('input').first()).toHaveValue('D:\\Leadroom')
    await panel.getByRole('radio', { name: /Use selected folder/ }).check()
    await panel.getByRole('button', { name: 'Save storage locations' }).click()
    await expect(panel.getByText('Storage locations saved')).toBeVisible()
    await expect(panel.getByText('Restart pending')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
    await panel.screenshot({ path: testInfo.outputPath(`storage-${viewport.name}.png`) })
  })
}

test('Ollama model manager selects, benchmarks, and downloads models', async ({ page }, testInfo) => {
  await page.setViewportSize(testInfo.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1280, height: 1000 })
  await mockSettings(page)
  await page.goto('/settings')

  await expect(page.getByLabel('Model name')).toHaveCount(0)
  await page.getByRole('button', { name: /Active model/ }).click()
  await expect(page.getByRole('option', { name: /llama3.2:3b/ })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('ollama-model-picker.png'), fullPage: true })
  await page.getByRole('option', { name: /qwen2.5:7b/ }).click()
  await expect(page.getByRole('button', { name: /Active model qwen2.5:7b/ })).toBeVisible()
  await page.getByRole('button', { name: 'Test selected model' }).click()
  await expect(page.getByText('9').first()).toBeVisible()
  await expect(page.getByText('recommended')).toBeVisible()
  await expect(page.getByText('31.5 tokens/sec')).toBeVisible()

  await page.getByRole('button', { name: /Active model/ }).click()
  await page.getByLabel('Find model').fill('gemma3')
  await page.getByRole('option', { name: /gemma3:4b/ }).click()
  await expect(page.getByText('Installed', { exact: true })).toBeVisible({ timeout: 5000 })
  await expect(page.getByRole('button', { name: /Active model gemma3:4b/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
})

for (const viewport of [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`editable settings manage branding model and domain tags on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const savedPayloads = await mockSettings(page)
    await page.goto('/settings')

    await expect(page.getByRole('link', { name: 'Local data' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Local discovery index' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sync data' })).toBeVisible()

    await page.getByLabel('Workspace name').fill('Northstar')
    await page.getByLabel('Subtitle').fill('Prospect desk')
    await page.getByLabel('Block another domain').fill('directory.example')
    await page.getByRole('button', { name: 'Add filter' }).click()
    await expect(page.getByText('directory.example')).toBeVisible()
    await page.getByLabel('API').check()
    await page.getByLabel(/API key/).fill('secret-key')
    await page.getByRole('button', { name: 'Save changes' }).click()

    await expect(page.getByText('Settings saved')).toBeVisible()
    await expect(page.getByRole('link', { name: /Northstar/ }).first()).toBeVisible()
    await page.getByRole('button', { name: 'Remove wikipedia.org' }).click()
    await page.getByRole('button', { name: 'Save changes' }).click()
    expect(savedPayloads()[0]).toMatchObject({ api_key: 'secret-key' })
    expect(savedPayloads()[1]).toMatchObject({ workspace_name: 'Northstar', workspace_subtitle: 'Prospect desk', model_provider: 'openai_compatible', blocked_domains: ['directory.example', 'github.com'] })
    expect(savedPayloads()[1]).not.toHaveProperty('api_key')
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
  })
}
