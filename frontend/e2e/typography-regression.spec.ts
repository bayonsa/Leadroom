import { expect, test } from '@playwright/test'
import { mockWorkspaceData } from './run-fixture'

const routes = ['/runs', '/new', '/repository', '/outreach', '/settings']

test('primary screens use the shared typography system', async ({ page }) => {
  await mockWorkspaceData(page)

  for (const route of routes) {
    await page.goto(route)

    const violations = await page.locator('body').evaluate((body) => {
      const allowedSizes = new Set(['12px', '14px', '18px', '36px'])
      const allowedWeights = new Set(['400', '500', '600', '700'])

      return [...body.querySelectorAll('*')].flatMap((element) => {
        if (!(element instanceof HTMLElement) && !(element instanceof SVGElement)) return []
        const style = getComputedStyle(element)
        const familyIsValid =
          style.fontFamily.includes('DM Sans Variable') ||
          style.fontFamily.includes('Source Code Pro Variable')
        const spacingIsValid = style.letterSpacing === 'normal' || style.letterSpacing === '0px'
        if (
          familyIsValid &&
          allowedSizes.has(style.fontSize) &&
          allowedWeights.has(style.fontWeight) &&
          spacingIsValid
        ) return []

        return [{
          tag: element.tagName,
          className: element.getAttribute('class') ?? '',
          text: element.textContent?.trim().slice(0, 50) ?? '',
          family: style.fontFamily,
          size: style.fontSize,
          weight: style.fontWeight,
          spacing: style.letterSpacing,
        }]
      })
    })

    expect(violations, `Typography violations on ${route}`).toEqual([])
  }
})
