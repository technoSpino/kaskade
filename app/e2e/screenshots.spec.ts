import { expect, test, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

// Visual review set (TASK.md follow-up #13): six pages × six themes at 1280 px,
// plus a close-up of the Heute timeline per theme. Runs only on demand:
//   npm run build && npm run screenshots:kaskade
// Uses the throwaway E2E instance (clock pinned to Tue 09:30 of plan week 1),
// so no personal data ends up in the committed images.
// KASKADE_SCREENSHOTS=filled seeds a realistic profile first (phase 2B, cards, hours, a Satz-Check)
// and writes to screenshots/filled/.
const FILLED = process.env.KASKADE_SCREENSHOTS === 'filled'
const OUT = join(process.cwd(), '..', 'docs', 'kaskade', 'screenshots', ...(FILLED ? ['filled'] : []))
const THEMES = ['signal', 'nacht', 'papier', 'bauhaus', 'fokus', 'magazin']

test.skip(!process.env.KASKADE_SCREENSHOTS, 'set KASKADE_SCREENSHOTS=1 to update the review screenshots')
test.use({ viewport: { width: 1280, height: 900 } })

async function withTheme(page: Page, theme: string) {
  await page.addInitScript((t) => {
    try { localStorage.setItem('kaskade-theme', t) } catch { /* ignore */ }
  }, theme)
}

async function shoot(page: Page, theme: string, name: string) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(500) // let the route fade-in finish
  await page.screenshot({ path: join(OUT, `${theme}-${name}.png`), fullPage: true, animations: 'disabled' })
}

test.beforeAll(async ({ request }) => {
  mkdirSync(OUT, { recursive: true })
  if (FILLED) {
    execFileSync('../server/.venv/bin/python', ['../server/scripts/seed_demo.py'], {
      env: { ...process.env, KASKADE_DATA_DIR: join(process.cwd(), '.e2e-data'), KASKADE_NOW: '2026-10-13T07:30:00+00:00' }
    })
  } else {
    // One block done so the timeline shows done / current / upcoming / pause.
    await request.post('http://127.0.0.1:8001/api/plan/done', { data: { block: 'karten', done: true } })
  }
})

for (const theme of THEMES) {
  test(`review set: ${theme}`, async ({ page }) => {
    await withTheme(page, theme)
    // Browser clock = the server's pinned clock, so the "jetzt" marker shows.
    await page.clock.setFixedTime(new Date('2026-10-13T07:30:00Z'))

    await page.goto('/')
    await expect(page.getByTestId('timeline')).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    await page.getByTestId('timeline').screenshot({ path: join(OUT, `${theme}-timeline.png`) })
    await shoot(page, theme, 'heute')

    await page.goto('/karten')
    await expect(page.getByTestId('karte')).toBeVisible()
    await page.keyboard.press('Space')
    await expect(page.getByTestId('karte-back')).toBeVisible()
    await shoot(page, theme, 'karten')

    await page.goto('/lesen/t01')
    await page.getByTestId('reader-view-beides').click() // case lens + new words
    await shoot(page, theme, 'lesen')

    await page.goto('/satz-check')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await shoot(page, theme, 'satz-check')

    await page.goto('/pruefung')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await shoot(page, theme, 'pruefung')

    await page.goto('/fahrplan')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await shoot(page, theme, 'fahrplan')
  })
}
