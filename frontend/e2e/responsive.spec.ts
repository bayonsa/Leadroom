import { expect, test } from '@playwright/test'
import { mockWorkspaceData } from './run-fixture'

const routes = ['/runs', '/repository', '/new', '/outreach', '/settings']
const viewports = [
  { width: 1366, height: 800 },
  { width: 1200, height: 800 },
  { width: 1024, height: 800 },
  { width: 900, height: 800 },
  { width: 768, height: 800 },
  { width: 390, height: 844 },
]

test('primary workspaces remain contained at desktop, tablet, and mobile widths', async ({ page }, testInfo) => {
  await mockWorkspaceData(page)
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    for (const route of routes) {
      await page.goto(route)
      await page.waitForLoadState('domcontentloaded')
      await expect(page.locator('.route-frame')).toBeVisible()
      const dimensions = await page.evaluate(() => {
        const routeFrame = document.querySelector<HTMLElement>('.route-frame')
        return {
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
          contentWidth: routeFrame?.scrollWidth ?? 0,
          contentClientWidth: routeFrame?.clientWidth ?? 0,
        }
      })
      expect(dimensions.documentWidth, `${route} overflows the ${viewport.width}px viewport`).toBeLessThanOrEqual(dimensions.viewportWidth + 1)
      expect(dimensions.contentWidth, `${route} clips content at ${viewport.width}px`).toBeLessThanOrEqual(dimensions.contentClientWidth + 1)
      if (viewport.width === 390) {
        await page.screenshot({ path: testInfo.outputPath(`${route.slice(1) || 'home'}-${viewport.width}.png`), fullPage: false })
      }
    }
    await page.goto('/repository')
    await expect(page.getByRole('heading', { name: 'Repository', exact: true })).toBeVisible()
    const repositoryLayout = await page.locator('.repository-panel').evaluate((panel) => ({
      width: panel.clientWidth,
      tableDisplay: getComputedStyle(panel.querySelector('table')!).display,
    }))
    if (repositoryLayout.width <= 1000) expect(repositoryLayout.tableDisplay).toBe('block')
    await page.screenshot({ path: testInfo.outputPath(`repository-${viewport.width}.png`), fullPage: false })
  }
})

test('mobile navigation traps focus, closes with Escape, and restores the trigger', async ({ page }) => {
  await mockWorkspaceData(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/runs')

  const trigger = page.getByRole('button', { name: 'Toggle navigation' })
  await trigger.click()
  await expect(page.locator('#primary-navigation')).toHaveClass(/sidebar-open/)
  await expect(page.locator('main')).toHaveAttribute('inert', '')

  await page.keyboard.press('Escape')
  await expect(page.locator('#primary-navigation')).not.toHaveClass(/sidebar-open/)
  await expect(trigger).toBeFocused()
})
