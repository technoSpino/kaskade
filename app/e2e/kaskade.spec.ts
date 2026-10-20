import { expect, test, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const DATA_DIR = join(process.cwd(), '.e2e-data') // the E2E API's KASKADE_DATA_DIR
const TMP = join(DATA_DIR, 'fixtures')

// Original test subtitles (written for these tests).
const SRT = `1
00:00:00,500 --> 00:00:02,000
Guten Morgen, wie geht es dir?

2
00:00:02,500 --> 00:00:04,000
Danke, mir geht es gut.

3
00:00:04,500 --> 00:00:06,000
Hast du heute Zeit für einen Kaffee?

4
00:00:06,500 --> 00:00:08,000
Leider nicht, ich muss arbeiten.
`

/** A 9-second silent grey WebM clip, generated with ffmpeg. */
function testClip(): string {
  mkdirSync(TMP, { recursive: true })
  const out = join(TMP, 'clip.webm')
  if (!existsSync(out)) {
    execFileSync('ffmpeg', [
      '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=320x180:d=9',
      '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono', '-t', '9',
      '-c:v', 'libvpx', '-b:v', '100k', '-c:a', 'libopus', out
    ])
  }
  return out
}

// Smoke tests against the running Kaskade services. Each test collects console
// errors and fails if any appear.
function watchConsole(page: Page) {
  const errors: string[] = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', (e) => errors.push(String(e)))
  return errors
}

/** `seconds` of silence as a WAV (8 kHz, 8 bit, mono). */
function silentWav(seconds: number): Buffer {
  const rate = 8000
  const n = Math.round(rate * seconds)
  const b = Buffer.alloc(44 + n, 128)
  b.write('RIFF', 0); b.writeUInt32LE(36 + n, 4); b.write('WAVE', 8)
  b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22)
  b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate, 28); b.writeUInt16LE(1, 32); b.writeUInt16LE(8, 34)
  b.write('data', 36); b.writeUInt32LE(n, 40)
  return b
}

// #28: Karten plays each card's audio by itself. The E2E API has no Piper voice, so card audio is
// stubbed with 1.5 s of silence (counted per card); the "browser fallback" test removes the stub.
const CARD_AUDIO = silentWav(1.5)
const audioHits = new Map<string, number>()
test.beforeEach(async ({ page }) => {
  await page.route('**/api/cards/*/audio', (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/')[3])
    audioHits.set(id, (audioHits.get(id) ?? 0) + 1)
    return route.fulfill({ status: 200, contentType: 'audio/wav', body: CARD_AUDIO, headers: { 'Cache-Control': 'no-store' } })
  })
})

test('Heute loads with the day plan, block timer and done toggle', async ({ page }) => {
  const errors = watchConsole(page)
  // Browser clock = the API's pinned clock (Tue 09:30 Berlin).
  await page.clock.setFixedTime(new Date('2026-10-13T07:30:00Z'))
  await page.goto('/')
  await expect(page.getByTestId('heute')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Hauptnavigation' })).toBeVisible()
  // Server clock: Tuesday, week 1 — #27: no Prüfungsteil, the block ends with Lesen at 11:30
  await expect(page.getByText('Woche 1 · Wohnen und Nachbarn')).toBeVisible()
  await expect(page.getByTestId('block-pruefung')).toHaveCount(0)

  // #16: every block names its exact item — 2A, week 1, Tuesday: library text t04 in free reading
  await expect(page.getByTestId('assign-lesen')).toContainText('Streit wegen der Musik')
  await expect(page.getByTestId('assign-input')).toContainText('Besichtigung einer Wohnung')
  // Timeline: labelled segments, exactly one highlighted (09:30 → Schauen), the rest upcoming.
  const timeline = page.getByTestId('timeline')
  await expect(timeline).toContainText('Karten')
  await expect(timeline).not.toContainText('Prüfung')
  await expect(timeline.locator('[data-state]')).toHaveCount(4) // Karten, Schauen, Pause, Lesen
  await expect(timeline).toHaveAttribute('aria-label', /10:35 Lesen \(55 min, offen\)$/)
  // #27: the longer lesen block names a second exact item after the text
  await expect(page.getByTestId('then-lesen-0')).toContainText('Danach')
  await expect(timeline.locator('[data-state="current"]')).toHaveCount(1)
  await expect(timeline.locator('[data-state="current"]')).toContainText('Schauen')
  // Starting the free-reading block opens the suggested text; the timer keeps running in the header.
  await page.getByTestId('start-lesen').click()
  await expect(page).toHaveURL(/\/lesen\/t\d+/)
  await expect(page.getByTestId('header-timer')).toContainText('Freies Lesen')
  await page.getByTestId('header-timer').click()
  await expect(page.getByTestId('header-timer')).toHaveCount(0)

  await page.goto('/')
  await expect(page.getByTestId('feed-row')).toContainText('/api/feed.xml')
  await page.getByTestId('done-input').click()
  await expect(page.getByTestId('done-input')).toContainText('Erledigt')
  await expect(timeline.locator('[data-state="done"]')).toContainText('✓ Schauen')
  expect(errors).toEqual([])
})

/** Turn the pinned plan day into a preview day (weekend or before the start) by rewriting /api/today. */
async function asPreviewDay(page: Page, kind: 'weekend' | 'beforeStart') {
  await page.route('**/api/today', async (route) => {
    const res = await route.fetch()
    const t = await res.json()
    const preview = { date: '2026-10-19', weekday: 'Mo', week: 2, day: t.day, theme: t.theme, goal: t.goal, exam: t.exam, mockExam: null }
    await route.fulfill({
      response: res,
      json: { ...t, day: null, theme: null, exam: null, weekday: 'Sa', weekend: true, beforeStart: kind === 'beforeStart', preview }
    })
  })
}

test('Heute on a weekend: Start buttons are disabled with a hint and do nothing', async ({ page }) => {
  const errors = watchConsole(page)
  await asPreviewDay(page, 'weekend')
  await page.goto('/')
  await expect(page.getByText('Wochenende — kein Lernblock.')).toBeVisible()
  // pinned clock → no hours yet: one line instead of an empty chart
  await expect(page.getByTestId('heute-hours-empty')).toContainText('Noch keine Zeit erfasst')
  for (const id of ['karten', 'input', 'lesen']) {
    await expect(page.getByTestId(`start-${id}`)).toHaveAttribute('aria-disabled', 'true')
  }
  await expect(page.getByTestId('done-karten')).toHaveCount(0)

  // Keyboard focus shows the hint (aria-describedby), clicking does nothing.
  await page.getByTestId('start-karten').focus()
  await expect(page.getByTestId('tip-karten')).toBeVisible()
  await expect(page.getByTestId('tip-karten')).toHaveText(/^Wochenende — der Lernblock läuft Mo–Fr\./)
  await page.getByTestId('start-karten').press('Escape')
  await expect(page.getByTestId('tip-karten')).toBeHidden()
  await page.getByTestId('start-input').hover()
  await expect(page.getByTestId('tip-input')).toBeVisible()
  // Playwright won't click aria-disabled elements on its own (good) — force it, and press Enter too.
  await page.getByTestId('start-input').click({ force: true })
  await page.getByTestId('start-input').press('Enter')
  await expect(page).toHaveURL(/127\.0\.0\.1:5174\/$/)
  await expect(page.getByTestId('header-timer')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('Heute before the plan start names the start date', async ({ page }) => {
  await asPreviewDay(page, 'beforeStart')
  await page.goto('/')
  await page.getByTestId('start-lesen').focus()
  await expect(page.getByTestId('tip-lesen')).toHaveText(/^Dein Plan startet am Mo, 12\. Oktober\./)
})

test('Aufgabe: plan writing task can be submitted', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/aufgabe/s01')
  await expect(page.getByRole('heading', { name: 'Ein Beet im Hof' })).toBeVisible()
  await page.getByTestId('wt-text').fill('Liebe Lea, stell dir vor, wir haben jetzt einen Garten im Hof! Mein Beet ist klein, aber schön. Komm doch am Samstag vorbei! Viele Grüße')
  await page.getByTestId('wt-submit').click()
  await expect(page.getByText('✓ Gespeichert')).toBeVisible()
  expect(errors).toEqual([])
})

test('Wortschatz-Test can be answered and shows a result', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/wortschatz')
  await page.getByTestId('vt-start').click()
  const word = page.getByTestId('vt-word')
  await expect(word).toBeVisible()
  // Answer "ja" for the first half, then "nein" — via keyboard J/N.
  for (let i = 0; i < 400; i++) {
    if (await page.getByTestId('vocab-result').isVisible()) break
    await page.keyboard.press(i % 2 ? 'n' : 'j')
  }
  await expect(page.getByTestId('vocab-result')).toBeVisible()
  await expect(page.getByTestId('vocab-result')).toContainText('Wörter bekannt')
  expect(errors).toEqual([])
})

test('Einstufung runs end to end (with pause and resume) and shows a result', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/einstufung')
  await page.getByTestId('pl-start').click()

  // 1 Wortschatz
  await page.getByTestId('vt-start').click()
  for (let i = 0; i < 400; i++) {
    if (await page.getByTestId('reading-test').isVisible()) break
    await page.keyboard.press(i % 3 ? 'j' : 'n')
  }
  // Pause and come back: the step is restored.
  await page.goto('/')
  await page.goto('/einstufung')
  await expect(page.getByTestId('reading-test')).toBeVisible()

  // 2 Lesen: always answer A, Enter = weiter
  for (let i = 0; i < 10; i++) {
    await page.keyboard.press('a')
    await page.keyboard.press('Enter')
  }
  // 3 Satz-Check skipped
  await page.getByTestId('sc-skip').click()
  // 4 Schreiben
  await page.getByTestId('wt-text').fill('Liebe Jana, ich bin vor zwei Wochen umgezogen. Die Wohnung ist hell und ruhig. Komm mich doch bald besuchen! Viele Grüße')
  await page.getByTestId('wt-submit').click()
  await page.getByTestId('pl-next').click()
  // 5 Sprechen: three short recordings with the fake microphone
  for (let i = 0; i < 3; i++) {
    await page.getByTestId('sp-record').click()
    await page.waitForTimeout(700)
    await page.getByTestId('sp-stop').click()
    await expect(page.getByText(`${i + 1} ✓`)).toBeVisible()
  }
  await page.getByTestId('sp-done').click()
  await page.getByTestId('pl-finish').click()

  const result = page.getByTestId('placement-result')
  await expect(result).toBeVisible()
  await expect(result).toContainText('Deine Phase')
  await expect(result).toContainText('3 Aufnahmen gespeichert')
  await expect(page.getByTestId('phase')).toBeVisible()
  expect(errors).toEqual([])
})

test('Karten: reveal, rate, "kenne ich schon" and undo', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/karten')
  const satz = page.getByTestId('karte-satz')
  await expect(satz).toBeVisible()
  const first = await satz.textContent()

  await page.keyboard.press('Space')
  await expect(page.getByTestId('karte-back')).toBeVisible()
  await expect(page.getByTestId('karte-gewusst')).toContainText('Gewusst')  // #25: two buttons, the time decides
  await expect(page.getByTestId('karte-nicht')).toContainText('Nicht gewusst')
  await page.keyboard.press('3') // keys 1–4 still work, silently
  await expect(satz).not.toHaveText(first!)

  const second = await satz.textContent()
  await page.keyboard.press('k')
  await expect(page.getByText('kenne ich schon. Kommt nicht wieder.')).toBeVisible()
  await expect(satz).not.toHaveText(second!)

  await page.keyboard.press('z')
  await expect(satz).toHaveText(second!)
  // the known card does not come back after "kenne ich" (without undo)
  await page.getByTestId('karte-known').click()
  await expect(satz).not.toHaveText(second!)
  expect(errors).toEqual([])
})

test('Lesen: reader with word states, case lens, glossary and "gelesen"', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/lesen')
  await page.getByTestId('text-t01').click()
  await expect(page.getByTestId('reader')).toContainText('Ärger mit der Heizung')
  // analysed text: new words highlighted, case letters shown
  await expect(page.locator('.at-word[data-state="neu"]').first()).toBeVisible()
  await expect(page.locator('.at-sup').first()).toBeVisible()
  await page.locator('.at-word', { hasText: /^Heizung$/ }).first().click()
  await expect(page.getByTestId('word-panel')).toContainText('„heating“')
  // View toggle: Neue Wörter / Kasus / Beides (remembered)
  await expect(page.getByTestId('reader-view-beides')).toHaveAttribute('aria-checked', 'true')
  await page.getByTestId('reader-view-neu').click()
  await expect(page.locator('.at-sup')).toHaveCount(0)
  await expect(page.locator('.at-neu').first()).toBeVisible()
  await page.getByTestId('reader-view-kasus').click()
  await expect(page.locator('.at-neu')).toHaveCount(0)
  await expect(page.locator('.at-sup').first()).toBeVisible()
  await page.reload()
  await expect(page.getByTestId('reader-view-kasus')).toHaveAttribute('aria-checked', 'true')
  await page.getByTestId('reader-view-beides').click()
  await page.getByTestId('reader-help').click()
  await expect(page.locator('.at-neu')).toHaveCount(0)
  await expect(page.locator('.at-sup')).toHaveCount(0)
  await page.getByTestId('reader-done').click()
  await expect(page.getByText('✓ gelesen').first()).toBeVisible()
  await page.goto('/lesen')
  await expect(page.getByTestId('text-t01')).toContainText('gelesen')
  expect(errors).toEqual([])
})

test('Satz minen from a pasted text → card comes first in Karten', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/lesen')
  await page.getByTestId('eigener-text-link').click()
  await page.getByTestId('paste-text').fill('Gestern habe ich mit meinem Vermieter über die Reparatur gesprochen.')
  await page.getByTestId('paste-run').click()
  await expect(page.locator('.at-sup', { hasText: 'D' }).first()).toBeVisible()
  await page.locator('.at-word', { hasText: /^Vermieter$/ }).click()
  await expect(page.getByTestId('word-panel')).toContainText('mit + Dativ')
  await page.getByTestId('mine').click()
  await expect(page.getByText('Gemined — kommt als neue Karte.')).toBeVisible()
  await page.goto('/karten')
  await expect(page.getByTestId('karte')).toContainText('Gemined · Eigener Text')
  await expect(page.getByTestId('karte-satz')).toContainText('Vermieter')
  expect(errors).toEqual([])
})

test('Prüfungstraining: timed reading task, listening task and writing self-check', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/pruefung')
  await expect(page.getByTestId('ready-lesen')).toContainText('noch nicht geübt')
  await page.getByTestId('item-l4').click()
  await page.getByTestId('start-timed').click()
  await expect(page.getByTestId('countdown')).toBeVisible()
  for (let i = 1; i <= 5; i++) await page.getByTestId(`l4-${i}-r`).click()
  await page.getByTestId('practice-submit').click()
  await expect(page.getByTestId('practice-result')).toContainText('%')

  await page.goto('/pruefung/hoeren/h1')
  await page.getByTestId('start-free').click()
  for (let i = 1; i <= 4; i++) await page.getByTestId(`h1-${i}-f`).click()
  await page.getByTestId('practice-submit').click()
  await expect(page.getByText('Transkript anzeigen')).toBeVisible()

  await page.goto('/pruefung/schreiben/s01')
  await page.getByTestId('start-free').click()
  await page.getByTestId('practice-text').fill('Liebe Lea, wir haben jetzt einen Garten im Hof. Komm doch vorbei! Viele Grüße')
  await page.getByTestId('check-aufgabe').check()
  await page.getByTestId('check-anrede').check()
  await page.getByTestId('practice-submit').click()
  await expect(page.getByTestId('practice-result')).toContainText('2 / 4')

  await page.goto('/pruefung')
  await expect(page.getByTestId('ready-lesen')).toContainText('1 Versuche')
  expect(errors.filter((e) => !e.includes('404'))).toEqual([])
})

test('Immersion: manual entry shows up on Heute and in the list', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/')
  await page.getByTestId('imm-toggle').click()
  await page.getByTestId('imm-title').fill('Checker Tobi')
  await page.getByTestId('imm-minutes').fill('25')
  await page.getByTestId('imm-passiv').check()
  await page.getByTestId('imm-save').click()
  await expect(page.locator('span', { hasText: 'Passiv' }).filter({ hasText: '0,4 h' })).toBeVisible()
  await page.goto('/immersion')
  await expect(page.getByTestId('immersion')).toContainText('Checker Tobi')
  expect(errors).toEqual([])
})

test('Server down: friendly banner instead of a broken page', async ({ page }) => {
  await page.route('**/api/**', (route) => route.fulfill({ status: 502, contentType: 'text/html', body: '<html>Bad Gateway</html>' }))
  await page.goto('/')
  await expect(page.getByTestId('server-banner')).toContainText('kaskade-api')
  await page.goto('/karten')
  await expect(page.getByRole('alert').first()).toBeVisible()
  await page.unroute('**/api/**')
  await page.getByTestId('server-banner').getByRole('button').click()
  await expect(page.getByTestId('server-banner')).toHaveCount(0)
})

test('Fahrplan shows forecast, phases and checks', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/fahrplan')
  await expect(page.getByText('Prognose B2')).toBeVisible()
  await expect(page.getByText('Stunden bis B2')).toBeVisible()
  await expect(page.locator('[data-testid^="phase-"]', { hasText: 'Jetzt' })).toHaveCount(1)
  await expect(page.getByText('Nächster Satz-Check')).toBeVisible()
  // #27: the exam is paused; #23: ratings have an empty state until the first one
  await expect(page.getByTestId('fp-exam')).toHaveText('B1-Prüfung: pausiert — kommt zurück, wenn du ein Prüfungsdatum wählst.')
  await expect(page.getByTestId('fp-ratings')).toContainText('Wie viel verstanden?')
  expect(errors).toEqual([])
})

test('Karten audio button plays (server audio or browser fallback) without errors', async ({ page }) => {
  const errors = watchConsole(page)
  await page.unroute('**/api/cards/*/audio') // the real endpoint: 404 without Piper → browser voice
  await page.goto('/karten')
  await page.getByTestId('karte-audio').click()
  await page.keyboard.press('a')
  await page.waitForTimeout(300)
  expect(errors.filter((e) => !e.includes('404'))).toEqual([])
})

test('Stil dropdown switches all six themes on every main page without console errors', async ({ page }) => {
  const errors = watchConsole(page)
  const themes = ['signal', 'nacht', 'papier', 'bauhaus', 'fokus', 'magazin']
  for (const path of ['/', '/karten', '/einstufung', '/satz-check', '/wortschatz', '/fahrplan', '/lesen', '/lesen/t02', '/pruefung', '/pruefung/lesen/l3', '/immersion']) {
    await page.goto(path)
    for (const t of themes) {
      await page.getByTestId('theme-select').selectOption(t)
      await expect(page.locator('html')).toHaveAttribute('data-theme', t)
      // tokens resolve: the page background follows the theme
      const bg = await page.locator('.k-app').evaluate((el) => getComputedStyle(el).backgroundColor)
      expect(bg).not.toBe('')
    }
  }
  // the choice survives a reload (localStorage + server setting)
  await page.getByTestId('theme-select').selectOption('papier')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'papier')
  await expect(page.getByTestId('theme-select')).toHaveValue('papier')
  // Karten still work in a dark theme
  await page.getByTestId('theme-select').selectOption('nacht')
  await page.goto('/karten')
  await expect(page.getByTestId('karte-satz')).toBeVisible()
  await page.keyboard.press('Space')
  await expect(page.getByTestId('karte-back')).toBeVisible()
  expect(errors).toEqual([])
})

test('Satz-Check accepts an SRT + clip, pauses per cue and records ratings', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/satz-check')
  await expect(page.getByText('Datei wählen').first()).toBeAttached()
  await page.getByTestId('upload-media').setInputFiles(testClip())
  await expect(page.getByText('clip.webm')).toBeAttached()
  await page.getByTestId('upload-subs').setInputFiles({ name: 'test.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(SRT) })
  await page.getByTestId('upload-title').fill('E2E-Clip')
  await page.getByTestId('upload-submit').click()
  await expect(page.getByText('4 Sätze in diesen 3 Minuten')).toBeVisible()
  // The new clip is selected (radio + "✓ Ausgewählt"), step 2 has focus and a preview player.
  await expect(page.getByRole('radio', { name: /E2E-Clip/ })).toHaveAttribute('aria-checked', 'true')
  await expect(page.getByRole('radio', { name: /E2E-Clip/ })).toContainText('✓ Ausgewählt')
  await expect(page.getByTestId('sc-start')).toBeFocused()
  await expect(page.getByTestId('sc-preview')).toBeVisible()
  await page.getByTestId('sc-start').click()

  await page.getByTestId('sc-play').click()
  await expect(page.getByTestId('sc-caption')).toHaveText('Guten Morgen, wie geht es dir?')
  // The clip pauses at the end of the first cue.
  await expect.poll(() => page.locator('video').evaluate((v: HTMLVideoElement) => v.paused), { timeout: 8000 }).toBe(true)
  const t = await page.locator('video').evaluate((v: HTMLVideoElement) => v.currentTime)
  expect(t).toBeGreaterThan(1.9)
  expect(t).toBeLessThan(2.6)

  for (const key of ['1', '2', '1', '3']) await page.keyboard.press(key)
  await expect(page.getByTestId('sc-coverage')).toHaveText('75 %')
  await page.getByTestId('sc-save').click()
  await expect(page.getByText('✓ Gespeichert')).toBeVisible()
  await expect(page.getByTestId('sc-verdict')).toContainText('Phase 2A')
  await expect(page.getByText('Bisherige Satz-Checks')).toBeVisible()
  // The "zu schwer" line is short and made of known words → listening speed, practise it in a loop.
  const tempo = page.getByTestId('tempo-lines').first()
  await expect(tempo).toContainText('Leider nicht, ich muss arbeiten.')
  const loopHref = await tempo.getByRole('link', { name: /in Schleife üben/ }).getAttribute('href')
  expect(loopHref).toMatch(/\/schauen\/\d+\?t=6\.5&loop=1$/)

  // Lines rated "mit Hilfe" / "zu schwer" can be mined as sentence cards.
  const mine = page.getByTestId('mine-lines')
  await expect(mine).toContainText('Sätze zum Minen · 2')
  await mine.getByText('Leider nicht, ich muss arbeiten.').click()
  await mine.locator('.at-word', { hasText: /^arbeiten$/ }).click()
  await mine.getByTestId('mine').click()
  await expect(mine).toContainText('Gemined — kommt als neue Karte.')
  await expect(mine).toContainText('Sätze zum Minen · 1')

  await page.goto(loopHref!)
  await expect(page.getByTestId('watch-loop')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('watch-line')).toContainText('Leider nicht, ich muss arbeiten.')
  expect(errors).toEqual([])
})

test('Schauen & minen: play → auto-pause → tap a word → mine → card with clip audio', async ({ page, request }) => {
  const errors = watchConsole(page)
  const up = await request.post('http://127.0.0.1:8001/api/media/upload', {
    multipart: {
      title: 'E2E-Krimi',
      subtitles: { name: 'k.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(SRT) },
      media: { name: 'k.webm', mimeType: 'video/webm', buffer: readFileSync(testClip()) }
    }
  })
  expect(up.ok()).toBeTruthy()
  const clip = await up.json()

  await page.goto('/schauen')
  await page.getByTestId(`watch-${clip.id}`).click()
  await expect(page).toHaveURL(new RegExp(`/schauen/${clip.id}$`))
  await page.getByTestId('watch-play').click()
  const line = page.getByTestId('watch-line')
  await expect(line).toContainText('Guten Morgen, wie geht es dir?')
  // #29: no transcript for this clip — ARD's subtitles, no toggle, no KI label
  await expect(page.getByTestId('track-spoken')).toHaveCount(0)
  await expect(page.getByTestId('watch-ki')).toHaveCount(0)
  // Auto-pause at the end of the first line.
  await expect.poll(() => page.getByTestId('watch-video').evaluate((v: HTMLVideoElement) => v.paused), { timeout: 8000 }).toBe(true)

  // → next line, R replays it.
  await page.keyboard.press('ArrowRight')
  await expect(line).toContainText('Danke, mir geht es gut.')
  await page.keyboard.press('ArrowLeft')
  await expect(line).toContainText('Guten Morgen')

  // Tap a word → word panel → mine the whole line with its audio.
  await page.getByTestId('watch-video').evaluate((v: HTMLVideoElement) => v.pause())
  await line.locator('.at-word', { hasText: /^Morgen$/ }).click()
  await expect(page.getByTestId('word-panel')).toContainText('Guten Morgen, wie geht es dir?')
  await page.getByTestId('mine').click()
  await expect(page.getByTestId('word-panel')).toContainText('Gemined — kommt als neue Karte.')
  await expect(page.getByTestId('watch-mined')).toContainText('1 Satz gemined')

  // L = loop the line: playback keeps jumping back to its start instead of pausing.
  await page.keyboard.press('l')
  await expect(page.getByTestId('watch-loop')).toHaveAttribute('aria-pressed', 'true')
  await page.getByTestId('watch-replay').click()
  await page.waitForTimeout(3500)
  const looped = await page.getByTestId('watch-video').evaluate((v: HTMLVideoElement) => ({ t: v.currentTime, paused: v.paused }))
  expect(looped.paused).toBe(false)
  expect(looped.t).toBeLessThan(2.4)
  await page.getByTestId('watch-video').evaluate((v: HTMLVideoElement) => v.pause())

  const mined = await (await request.get('http://127.0.0.1:8001/api/mined')).json()
  const card = mined.find((c: { sentence: string }) => c.sentence === 'Guten Morgen, wie geht es dir?')
  expect(card.mediaId).toBe(clip.id)
  const audio = await request.get(`http://127.0.0.1:8001/api/cards/${card.id}/audio`)
  expect(audio.headers()['content-type']).toBe('audio/mp4')

  // Resume position is saved; mined cards come first in Karten (earlier tests may have mined others).
  await page.goto('/karten')
  await expect(page.getByTestId('karte')).toContainText('Gemined')
  const media = await (await request.get(`http://127.0.0.1:8001/api/media/${clip.id}`)).json()
  expect(media.position).toBeGreaterThan(0)
  expect(errors).toEqual([])
})

test('#18 Schauen: auto-pause after a tight line shows and mines that line, not the next', async ({ page, request }) => {
  const errors = watchConsole(page)
  // Like Tatort: a 0.12 s gap after line 1, then lines back to back (gap 0).
  const TIGHT = `1\n00:00:00,500 --> 00:00:02,000\nWo waren Sie gestern Abend?\n\n2\n00:00:02,120 --> 00:00:03,500\nIch war die ganze Zeit zu Hause.\n\n3\n00:00:03,500 --> 00:00:05,000\nDas kann niemand bestätigen.\n`
  const up = await request.post('http://127.0.0.1:8001/api/media/upload', {
    multipart: {
      title: 'E2E-Verhör',
      subtitles: { name: 't.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(TIGHT) },
      media: { name: 't.webm', mimeType: 'video/webm', buffer: readFileSync(testClip()) }
    }
  })
  const clip = await up.json()
  await page.goto(`/schauen/${clip.id}`)
  const line = page.getByTestId('watch-line')
  const video = page.getByTestId('watch-video')
  const paused = () => video.evaluate((v: HTMLVideoElement) => v.paused)

  await page.getByTestId('watch-play').click()
  await expect.poll(paused, { timeout: 8000 }).toBe(true)
  expect(await video.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThanOrEqual(2.0)
  await page.waitForTimeout(400) // nothing switches while paused
  await expect(line).toContainText('Wo waren Sie gestern Abend?')
  await expect(line).not.toContainText('ganze Zeit')

  // Word panel and "Satz minen" act on the line just heard.
  await line.locator('.at-word', { hasText: /^gestern$/ }).click()
  await expect(page.getByTestId('word-panel')).toContainText('Wo waren Sie gestern Abend?')
  await page.getByTestId('mine').click()
  await expect(page.getByTestId('watch-mined')).toContainText('1 Satz gemined')
  const mined = await (await request.get('http://127.0.0.1:8001/api/mined')).json()
  const card = mined.find((c: { sentence: string }) => c.sentence === 'Wo waren Sie gestern Abend?')
  expect(card.mediaId).toBe(clip.id)

  // Play on: line 2, then a pause at its end although line 3 starts at the same moment.
  await page.getByTestId('watch-play').click()
  await expect(line).toContainText('Ich war die ganze Zeit zu Hause.')
  await expect.poll(paused, { timeout: 8000 }).toBe(true)
  await page.waitForTimeout(400)
  await expect(line).toContainText('Ich war die ganze Zeit zu Hause.')
  // → goes to the next line from the one on screen (line 3), not past it.
  await page.keyboard.press('ArrowRight')
  await expect(line).toContainText('Das kann niemand bestätigen.')
  await video.evaluate((v: HTMLVideoElement) => v.pause())
  expect(errors).toEqual([])
})

test('#19 mined cards: no unsure case badge, same line again → add the word, edit and delete in Karten', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/lesen/eigener-text')
  // Parser says Akkusativ for "die Herrlichkeit", its role says subject: no badge rather than a wrong one.
  await page.getByTestId('paste-text').fill('Denn dein ist das Reich und die Kraft und die Herrlichkeit.')
  await page.getByTestId('paste-run').click()
  await page.locator('.at-word', { hasText: /^Herrlichkeit$/ }).click()
  await expect(page.getByTestId('word-panel')).toContainText('Herrlichkeit')
  await expect(page.getByTestId('word-panel').locator('.k-case')).toHaveCount(0)
  await page.locator('.at-word', { hasText: /^Reich$/ }).click()
  await expect(page.getByTestId('word-panel').locator('.k-case')).toHaveText('N')

  const line = 'Wenn man überhetzt, versaust du dir nachher die Chance.'
  await page.goto('/lesen/eigener-text')
  await page.getByTestId('paste-text').fill(line)
  await page.getByTestId('paste-run').click()
  await page.locator('.at-word', { hasText: /^versaust$/ }).click()
  await page.getByTestId('mine').click()
  await expect(page.getByTestId('mine-result')).toContainText('Gemined — kommt als neue Karte.')
  await page.getByTestId('mine').click()
  await expect(page.getByTestId('mine-result')).toContainText('Satz schon gemint — das Wort ist schon auf der Karte.')
  await page.locator('.at-word', { hasText: /^Chance$/ }).click()
  await page.getByTestId('mine').click()
  await expect(page.getByTestId('mine-result')).toHaveText('Satz schon gemint.')
  await page.getByTestId('mine-add-word').click()
  await expect(page.getByTestId('mine-result')).toContainText('„Chance“ steht jetzt mit auf der Karte.')

  await page.goto('/karten')
  const row = page.getByTestId('mined-list').locator('li', { hasText: line })
  await expect(row.locator('strong')).toHaveCount(2) // versaust + Chance on one card
  await expect(row).toContainText('Chance')
  await row.getByRole('button', { name: 'Bearbeiten' }).click()
  await page.getByTestId('edit-gloss').fill('to mess up, to ruin')
  await page.getByTestId('edit-case').selectOption('')
  await page.getByTestId('edit-save').click()
  await expect(row).toContainText('to mess up, to ruin')

  // The card on screen: a mined card can be edited right there.
  await page.getByTestId('karte-reveal').click()
  if ((await page.getByTestId('karte').textContent())?.includes('Gemined')) {
    await page.getByTestId('karte-edit').click()
    await expect(page.getByTestId('mined-editor')).toBeVisible()
    await expect(page.getByTestId('edit-lemma')).toBeFocused()
    await page.keyboard.press('Escape')
    await page.locator('body').click({ position: { x: 5, y: 5 } })
    await page.keyboard.press('1') // keys never rate a card while it's being edited
    await expect(page.getByTestId('mined-editor')).toBeVisible()
    await page.getByTestId('mined-editor').getByRole('button', { name: 'Abbrechen' }).click()
    await expect(page.getByTestId('karte-back')).toBeVisible()
  }

  await row.getByRole('button', { name: 'Bearbeiten' }).click()
  await page.getByTestId('edit-delete').click()
  await page.getByTestId('edit-delete-yes').click()
  await expect(page.getByTestId('mined-list').locator('li', { hasText: line })).toHaveCount(0)
  expect(errors).toEqual([])
})

test('#27 Prüfung page: the Schreiben/Sprechen tasks stay reachable, the exam is paused', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/pruefung')
  await expect(page.getByTestId('pruefung-paused')).toContainText('B1-Prüfung: pausiert')
  await page.getByTestId('aufgabe-p01').click()
  await expect(page).toHaveURL(/\/aufgabe\/p01$/)
  await expect(page.locator('h1')).toContainText('Ein Hoffest für das Haus')
  expect(errors).toEqual([])
})

test('Reader: quotes, punctuation and case letters never wrap away from their word', async ({ page }) => {
  for (const width of [360, 600, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/lesen/t01')
    await expect(page.locator('.at-group').first()).toBeVisible()
    const broken = await page.locator('.at-group').evaluateAll((els) =>
      els.filter((e) => e.getClientRects().length > 1).map((e) => e.textContent))
    expect(broken, `width ${width}`).toEqual([])
    // „ is always glued to the following word
    const lonely = await page.locator('.at-group').evaluateAll((els) =>
      els.map((e) => e.textContent ?? '').filter((t) => /^[„‚(«]$/.test(t.trim())))
    expect(lonely).toEqual([])
  }
})

test('Aus der Mediathek holen: progress, then the new clip is selected (API faked, no network)', async ({ page, request }) => {
  const errors = watchConsole(page)
  const up = await request.post('http://127.0.0.1:8001/api/media/upload', {
    multipart: { title: 'Tatort: Demo', subtitles: { name: 'd.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(SRT) } }
  })
  const clip = await up.json()
  let polls = 0
  await page.route('**/api/media/mediathek', (r) => r.fulfill({ status: 202, json: { jobId: 'j1' } }))
  await page.route('**/api/media/jobs/j1', (r) => {
    polls++
    const MB = 1024 * 1024
    return r.fulfill({
      json: polls < 3
        ? { status: 'running', phase: 'download', progress: 0.4, downloaded: 58 * MB, total: 145 * MB, speed: 8 * MB }
        : { status: 'done', phase: 'done', progress: 1, mediaId: clip.id }
    })
  })
  await page.goto('/satz-check')
  await page.getByText('Aus der Mediathek holen').click()
  await page.getByTestId('mediathek-url').fill('https://www.ardmediathek.de/video/tatort/demo')
  await page.getByTestId('mediathek-fetch').click()
  await expect(page.getByTestId('mediathek-progress')).toContainText('58 von 145 MB · 8 MB/s')
  await expect(page.getByRole('radio', { name: /Tatort: Demo/ })).toHaveAttribute('aria-checked', 'true', { timeout: 8000 })
  await expect(page.getByTestId('mediathek-progress')).toContainText('Fertig.')
  expect(errors).toEqual([])
})

test('YouTube: Mac one-liner and cookies.txt upload', async ({ page }) => {
  const errors = watchConsole(page)
  await page.goto('/satz-check')
  await page.getByText('Von YouTube holen').click()
  await expect(page.getByTestId('yt-mac-command')).toContainText('--convert-subs srt')
  const cookies = '# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tx\n'
  await page.getByTestId('yt-cookies').setInputFiles({ name: 'cookies.txt', mimeType: 'text/plain', buffer: Buffer.from(cookies) })
  await page.getByTestId('yt-cookies-upload').click()
  await expect(page.getByTestId('yt-cookies-on')).toContainText('Cookies hinterlegt')
  await page.getByTestId('yt-cookies-on').getByRole('button', { name: 'entfernen' }).click()
  await expect(page.getByTestId('yt-cookies-on')).toHaveCount(0)
  expect(errors).toEqual([])
})


/** Material für heute und morgen as of `iso` in the 2B plan (the API's ?today=&phase= preview). */
test('#20 every Starten on Heute opens its exact item, Mon–Fri of week 1', async ({ page, request }) => {
  const errors = watchConsole(page)
  // The plan's week-1 clips in the library (a test clip each, registered under its catalog key).
  const keys = ['tatort-schweigen', 'egp-698', 'egp-700', 'egp-684', 'soko-leipzig-das-auge', 'radio-tatort-uebertherapie']
  const media = async () => (await (await request.get('http://127.0.0.1:8001/api/media')).json()) as { id: number, key: string | null }[]
  for (const key of keys) {
    if ((await media()).some((m) => m.key === key)) continue
    const up = await request.post('http://127.0.0.1:8001/api/media/upload', {
      multipart: {
        title: `E2E ${key}`,
        subtitles: { name: 'k.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(SRT) },
        media: { name: 'k.webm', mimeType: 'video/webm', buffer: readFileSync(testClip()) }
      }
    })
    const clip = await up.json()
    execFileSync('python3', ['-c', 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("UPDATE media SET key=? WHERE id=?", (sys.argv[2], int(sys.argv[3]))); c.commit()',
      join(DATA_DIR, 'kaskade.db'), key, String(clip.id)])
  }
  const id = Object.fromEntries((await media()).filter((m) => m.key).map((m) => [m.key, m.id]))
  const watch = (key: string) => new RegExp(`/schauen/${id[key]}\\?von=\\d+&bis=\\d+$`)

  // block → where "Starten" goes; null = stays on Heute (the news links are listed under the block).
  // #27: no Prüfungsteil any more — three blocks a day.
  const days: [string, Record<string, RegExp | null>][] = [
    ['2026-10-12', { karten: /\/karten$/, input: watch('tatort-schweigen'), lesen: watch('egp-698') }],
    ['2026-10-13', { karten: /\/karten$/, input: watch('tatort-schweigen'), lesen: null }],
    ['2026-10-14', { karten: /\/karten$/, input: watch('tatort-schweigen'), lesen: /\/schauen\/\d+\?von=\d+&bis=\d+$/ }],
    ['2026-10-15', { karten: /\/karten$/, input: /\/schauen\/\d+\?von=\d+&bis=\d+$/, lesen: /\/schauen\/\d+\?von=\d+&bis=\d+$/ }],
    ['2026-10-16', { karten: /\/karten$/, input: /\/schauen\/\d+\?von=\d+&bis=\d+$/, lesen: /\/schauen\/\d+\?von=\d+&bis=\d+$/ }]
  ]
  const undone = new Set<string>()
  for (const [iso, blocks] of days) {
    await page.unroute('**/api/today')
    await page.route('**/api/today', (route) => route.continue({ url: `${new URL(route.request().url()).origin}/api/today?today=${iso}&phase=2B` }))
    for (const [block, to] of Object.entries(blocks)) {
      await page.goto('/')
      await expect(page.getByTestId(`done-${block}`)).toBeVisible()
      await expect(page.getByTestId('block-pruefung')).toHaveCount(0)
      // earlier tests may have ticked a block off or left its timer running: undo that first
      if ((await page.getByTestId(`done-${block}`).textContent())?.includes('Erledigt')) {
        undone.add(block)
        await page.getByTestId(`done-${block}`).click()
      }
      if (await page.getByTestId(`stop-${block}`).isVisible()) await page.getByTestId(`stop-${block}`).click()
      // what the server computes for that day now (#21: clip ranges roll from his position)
      const assigned = (await (await request.get(`http://127.0.0.1:8001/api/today?today=${iso}&phase=2B`)).json()).assignments
      if (assigned[block].part) await expect(page.getByTestId(`assign-${block}`), `${iso} ${block}`).toContainText(assigned[block].part)
      await page.getByTestId(`start-${block}`).click()
      if (to) {
        await expect(page, `${iso} ${block}`).toHaveURL(to)
        expect(page.url(), `${iso} ${block}`).toContain(assigned[block].start.to)  // exactly the line's item
      }
      else {
        await expect(page.getByTestId(`stop-${block}`)).toBeVisible()
        await expect(page, `${iso} ${block}`).toHaveURL(/\/$/)
      }
    }
  }
  // #24/#27 Friday: after the Radio Tatort comes the Schirach Lesetest — "Öffnen" opens the Leseprobe at S. 7
  await page.context().route('https://www.bic-media.com/**', (route) => route.fulfill({ status: 200, contentType: 'text/plain', body: 'Leseprobe' }))
  await page.goto('/')
  const test = page.getByTestId('then-lesen-0')
  await expect(test).toContainText('Lesetest: Schirach, Verbrechen — die ersten zwei Seiten von „Fähner“ · S. 7–8 · 25 min')
  const [popup] = await Promise.all([page.waitForEvent('popup'), page.getByTestId('open-lesen-0').click()])
  expect(popup.url()).toBe('https://www.bic-media.com/books/content/shortened/9783442770663.pdf#page=9')
  await popup.close()
  await request.post('http://127.0.0.1:8001/api/activity/stop')
  for (const block of undone) await request.post('http://127.0.0.1:8001/api/plan/done', { data: { block, done: true } })
  await page.unroute('**/api/today')
  expect(errors).toEqual([])
})

test('#21 the clip range on Heute starts at his saved position, and Starten opens exactly that', async ({ page, request }) => {
  const errors = watchConsole(page)
  const media = (await (await request.get('http://127.0.0.1:8001/api/media')).json()) as { id: number, key: string | null }[]
  const tatort = media.find((m) => m.key === 'tatort-schweigen')!  // registered by the #20 test above
  const before = (await (await request.get(`http://127.0.0.1:8001/api/media/${tatort.id}`)).json()).position ?? 0
  // He is at 66:40: Wednesday's part is the rest of the film, not the plan's 60:40–89:21
  await request.put(`http://127.0.0.1:8001/api/media/${tatort.id}/progress`, { data: { position: 4000 } })
  await page.route('**/api/today', (route) => route.continue({ url: `${new URL(route.request().url()).origin}/api/today?today=2026-10-14&phase=2B` }))
  await page.goto('/')
  await expect(page.getByTestId('assign-input')).toContainText('Tatort: Schweigen · 66:40–89:21 · 23 min')
  await expect(page.getByTestId('block-input')).toContainText('Tatort: Schweigen, 66:40–89:21 (Ende).')
  await page.getByTestId('start-input').click()
  await expect(page).toHaveURL(new RegExp(`/schauen/${tatort.id}\\?von=4000&bis=5361$`))
  await expect(page.getByTestId('watch-range')).toContainText('66:40')
  await page.unroute('**/api/today')
  await page.goto('about:blank') // Schauen saves its position on leaving — leave first, then restore
  await request.post('http://127.0.0.1:8001/api/activity/stop')
  await request.put(`http://127.0.0.1:8001/api/media/${tatort.id}/progress`, { data: { position: before } })
  expect(errors).toEqual([])
})

test('#20 a tab from before a deploy: Starten still opens its page', async ({ page }) => {
  // The tab's Karten chunk is gone after a rebuild: the server answers with index.html (as vite preview does).
  let served = 0
  await page.route(/\/assets\/KartenView-[^/]+\.js$/, (route) => {
    if (served++ === 0) return route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><html></html>' })
    return route.continue()
  })
  await page.route('**/api/today', (route) => route.continue({ url: `${new URL(route.request().url()).origin}/api/today?today=2026-10-12&phase=2B` }))
  await page.goto('/')
  await page.getByTestId('start-karten').click()
  await expect(page).toHaveURL(/\/karten$/)
  await expect(page.locator('h1')).toBeVisible()
  expect(served).toBe(2) // failed once, then loaded fresh
  await page.unroute('**/api/today')
  await page.request.post('http://127.0.0.1:8001/api/activity/stop')
})

async function materialsAt(page: Page, iso: string) {
  await page.route('**/api/materials', (route) => route.continue({ url: `${new URL(route.request().url()).origin}/api/materials?today=${iso}&phase=2B` }))
}

async function tatortClip(request) {
  // A 9-second test clip whose subtitles run to 89:20 — library length of the real Tatort.
  const srt = SRT + `\n5\n01:29:19,000 --> 01:29:20,000\nEnde.\n`
  const res = await request.post('/api/media/upload', {
    multipart: {
      subtitles: { name: 'tatort.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(srt) },
      media: { name: 'tatort.webm', mimeType: 'video/webm', buffer: readFileSync(testClip()) },
      title: 'Tatort: Schweigen (E2E-Testclip)'
    }
  })
  expect(res.ok()).toBeTruthy()
  return res.json()
}

test('Material für heute und morgen: Sunday shows Monday with the Tatort ready', async ({ page, request }) => {
  const errors = watchConsole(page)
  await tatortClip(request)
  await materialsAt(page, '2026-10-11')
  await page.goto('/')
  const card = page.getByTestId('materials')
  await expect(card.getByText('Heute (So 11.10.)')).toBeVisible()
  await expect(page.getByTestId('mat-today')).toContainText('Kein Lernblock.')
  await expect(card.getByText('Morgen (Mo 12.10.)')).toBeVisible()
  const tatort = page.getByTestId('mat-tomorrow-input')
  await expect(tatort).toContainText(/Tatort: Schweigen · \d+:\d\d–\d+:\d\d · \d+ min/) // #21: the range rolls from his position
  await expect(tatort).toContainText('✓ bereit')
  await expect(tatort).toContainText('Quelle: ARD Mediathek · NDR')
  await expect(page.getByTestId('mat-tomorrow-pruefung')).toHaveCount(0) // #27: no Prüfungsteil
  await expect(page.getByTestId('mat-tomorrow-lesen-1')).toContainText('nachrichtenleicht.de')  // "danach", fills the 60 min
  // Bald fällig: the week-2 book, due date first; Material itself has no purchase cards
  const due = page.getByTestId('due-schirach-verbrechen')
  await expect(due).toContainText('Fällig Mo 12.10. · morgen')
  await expect(due).toContainText('Ferdinand von Schirach: Verbrechen kaufen')
  await expect(due).toContainText('ab 19.10. im Plan, Woche 2')
  await expect(due).toContainText('E-Book reicht bis Sa 17.10.')
  await expect(page.getByTestId('due-language-reactor')).toContainText('Fällig Mo 19.10. · in 8 Tagen')
  await expect(page.getByTestId('materials')).not.toContainText('kaufen')
  await expect(page.getByText('Känguru')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('Material: Monday shows today and Tuesday, no microphone line any more', async ({ page }) => {
  await materialsAt(page, '2026-10-12')
  await page.goto('/')
  await expect(page.getByTestId('materials').getByText('Heute (Mo 12.10.)')).toBeVisible()
  await expect(page.getByTestId('materials').getByText('Morgen (Di 13.10.)')).toBeVisible()
  await expect(page.getByTestId('materials')).not.toContainText('Mikrofon')  // #27: no Sprechen task in the plan
  await expect(page.getByTestId('mat-tomorrow-input')).toContainText(/Tatort: Schweigen · \d+:\d\d–\d+:\d\d/)
  await expect(page.getByTestId('mat-tomorrow-lesen')).toContainText('Die drei Links stehen am Morgen hier')
  await expect(page.getByTestId('mat-tomorrow-lesen-1')).toContainText('Easy German Podcast')
})

test('Material on Friday: the next plan day is Monday', async ({ page }) => {
  await materialsAt(page, '2026-10-16')
  await page.goto('/')
  await expect(page.getByTestId('materials').getByText('Nächster Lerntag: Mo 19.10.')).toBeVisible()
  // #21: week 1's Tatort isn't watched here → Monday continues with it, nothing is skipped
  await expect(page.getByTestId('mat-next-input')).toContainText('Tatort: Schweigen')
  await expect(page.getByTestId('mat-next-lesen')).toContainText('Ferdinand von Schirach: Verbrechen')
  await expect(page.getByTestId('mat-next-lesen')).toContainText('„Fähner“ und „Tanatas Teeschale“')
  // not bought by Monday: overdue, marked — tick it off as bought
  const due = page.getByTestId('due-schirach-verbrechen')
  await expect(due).toContainText('Überfällig seit Mo 12.10.')
  await expect(due).toContainText('ISBN 978-3-442-77066-3')
  await page.getByTestId('due-done-schirach-verbrechen').click()
  await expect(page.getByTestId('due-schirach-verbrechen')).toHaveCount(0)
})

test('#32 Bald fällig: QualityLand as a Kindle ebook, due Sa 31.10., one shop link, no paper option', async ({ page, request }) => {
  const errors = watchConsole(page)
  await page.addInitScript(() => { try { localStorage.setItem('kaskade-theme', 'signal') } catch { /* about:blank */ } })
  // Fahrplan → Nächste Schritte lists it with the edition (Matt's 2B plan)
  const restore = asMatt()
  try {
    await page.goto('/fahrplan')
    await expect(page.getByTestId('fp-notice-kling-qualityland')).toContainText('Kindle-E-Book (Dunkle Edition) · ASIN B071436DMF · 9,99 € · ab 2.11. im Plan, Woche 4')
    await expect(page.getByTestId('fp-upcoming')).not.toContainText('Nordwind')
  } finally {
    restore()
  }
  await materialsAt(page, '2026-10-30')
  await page.goto('/')
  const due = page.getByTestId('due-kling-qualityland')
  await expect(due).toContainText('Fällig Sa 31.10. · morgen')
  await expect(due).toContainText('Marc-Uwe Kling: QualityLand kaufen')
  await expect(due).toContainText('ab 2.11. im Plan, Woche 4 · Kindle-E-Book (Dunkle Edition), ASIN B071436DMF, 9,99 €')
  await expect(due).not.toContainText('Taschenbuch')
  await expect(due).not.toContainText('E-Book reicht')
  await expect(due.getByRole('link')).toHaveCount(1)
  await expect(due.getByRole('link', { name: 'Amazon.de (Kindle) ↗' })).toHaveAttribute('href', 'https://www.amazon.de/dp/B071436DMF')
  // Friday → the next plan day is Monday 2.11.: the first chapters, by name
  const lesen = page.getByTestId('mat-next-lesen')
  await expect(lesen).toContainText('Marc-Uwe Kling: QualityLand')
  await expect(lesen).toContainText('Vom Anfang bis „QualityLand Reiseführer: Ohrwürmer“')
  for (const width of [1280, 480]) {
    await page.setViewportSize({ width, height: 900 })
    await due.screenshot({ path: join(SHOTS, `bald-faellig-qualityland-${width}.png`) })
  }
  await page.getByTestId('due-done-kling-qualityland').click()
  await expect(due).toHaveCount(0)
  await request.post('http://127.0.0.1:8001/api/books/kling-qualityland/bought', { data: { done: false } })
  expect(errors).toEqual([])
})

test('Schauen with a plan range: starts there and says "Ziel für heute erreicht" at the end', async ({ page, request }) => {
  const errors = watchConsole(page)
  const clip = await tatortClip(request)
  await page.goto(`/schauen/${clip.id}?von=2&bis=4`)
  await expect(page.getByTestId('watch-range')).toContainText('Heute: 0:02–0:04.')
  await expect(page.getByTestId('watch-clock')).toContainText('Ziel 0:04')
  await page.getByTestId('watch-autopause').uncheck()
  await page.getByTestId('watch-play').click()
  await expect(page.getByTestId('watch-goal')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByTestId('watch-goal')).toContainText('Ziel für heute erreicht ✓')
  expect(errors).toEqual([])
})

test('Deine Clips: the genre is editable', async ({ page, request }) => {
  const clip = await tatortClip(request)
  await page.goto('/schauen')
  const select = page.getByTestId(`tag-${clip.id}`)
  await expect(select).toHaveValue('krimi') // guessed from the title
  await select.selectOption('drama')
  await page.reload()
  await expect(page.getByTestId(`tag-${clip.id}`)).toHaveValue('drama')
})

/** Run SQL on the E2E database (setup and cleanup that has no API). Returns the first column of the first row. */
function sql(query: string, ...args: (string | number)[]): string {
  return execFileSync('python3', ['-c', [
    'import sqlite3, sys',
    'c = sqlite3.connect(sys.argv[1]); r = c.execute(sys.argv[2], sys.argv[3:]).fetchone(); c.commit()',
    'print("" if r is None else r[0])'
  ].join('\n'), join(DATA_DIR, 'kaskade.db'), query, ...args.map(String)]).toString().trim()
}

/** Matt's setup for a test (phase 2B from Mon 12.10.), restored afterwards. */
function asMatt() {
  const old = ['phase', 'planStart'].map((k) => [k, sql('SELECT value FROM settings WHERE key = ?', k)])
  for (const [k, v] of [['phase', '"2B"'], ['planStart', '"2026-10-12"']]) {
    sql('INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', k, v)
  }
  return () => {
    for (const [k, v] of old) {
      if (v) sql('UPDATE settings SET value = ? WHERE key = ?', v, k)
      else sql('DELETE FROM settings WHERE key = ?', k)
    }
  }
}

test('#23 Schauen: Z counts the line as too hard and plays the next one; the rating shows the share', async ({ page, request }) => {
  const errors = watchConsole(page)
  const restore = asMatt()
  const media = (await (await request.get('http://127.0.0.1:8001/api/media')).json()) as { id: number, key: string | null }[]
  const tatort = media.find((m) => m.key === 'tatort-schweigen')!  // registered by the #20 test
  const before = (await (await request.get(`http://127.0.0.1:8001/api/media/${tatort.id}`)).json()).position ?? 0
  await request.put(`http://127.0.0.1:8001/api/media/${tatort.id}/progress`, { data: { position: 0 } })
  sql("DELETE FROM ratings WHERE local_date = '2026-10-13' AND block = 'input'")
  sql('DELETE FROM hard_lines WHERE media_id = ?', tatort.id)
  // today's Schauen block is this clip: the rating question comes at the end of today's part
  const today = await (await request.get('http://127.0.0.1:8001/api/ratings/today')).json()
  expect(today.find((r: { block: string }) => r.block === 'input').mediaId).toBe(tatort.id)

  await page.goto(`/schauen/${tatort.id}?von=0&bis=7`)
  const line = page.getByTestId('watch-line')
  const video = page.getByTestId('watch-video')
  await page.getByTestId('watch-play').click()
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.paused), { timeout: 8000 }).toBe(true)
  await expect(line).toContainText('Guten Morgen, wie geht es dir?')
  await page.keyboard.press('z')
  await expect(page.getByTestId('watch-hard-note')).toContainText('„Guten Morgen, wie geht es dir?“ als zu schwer markiert · 1 heute')
  await expect(line).toContainText('Danke, mir geht es gut.')                     // the next line …
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => !v.paused && v.currentTime > 2.2), { timeout: 2000 }).toBe(true) // … plays
  const marks = (await (await request.get(`http://127.0.0.1:8001/api/media/${tatort.id}/hard`)).json()).marks
  expect(marks.map((m: { text: string }) => m.text)).toEqual(['Guten Morgen, wie geht es dir?'])  // logged, no card
  await expect(page.getByTestId('watch-mined')).toHaveCount(0)

  await page.getByTestId('watch-autopause').uncheck()
  await video.evaluate((v: HTMLVideoElement) => v.play())  // on to the end of today's part (0:07)
  await expect(page.getByTestId('rate-ask')).toBeVisible({ timeout: 12_000 })
  await expect(page.getByTestId('rate-share')).toHaveText('Heute 1 von 4 Zeilen als zu schwer markiert (25 %)')
  await page.getByTestId('rate-80').click()
  await expect(page.getByTestId('watch-rated')).toContainText('Verstanden: 80 %')
  const rows = (await (await request.get('http://127.0.0.1:8001/api/ratings')).json()).ratings
  const r = rows.find((x: { block: string, date: string }) => x.block === 'input' && x.date === '2026-10-13')
  expect([r.pct, r.hard, r.lines, r.kind]).toEqual([80, 1, 4, 'clip'])

  await page.goto('about:blank') // Schauen saves its position on leaving — leave first, then restore
  await request.put(`http://127.0.0.1:8001/api/media/${tatort.id}/progress`, { data: { position: before } })
  sql("DELETE FROM ratings WHERE local_date = '2026-10-13' AND block = 'input'")
  restore()
  expect(errors).toEqual([])
})

test('#23 Heute: the lesen block ends → "Wie viel hast du verstanden?" → stored, and under 70 % it says what the plan does', async ({ page, request }) => {
  const errors = watchConsole(page)
  const restore = asMatt()
  sql("DELETE FROM ratings WHERE local_date = '2026-10-13'")
  sql("DELETE FROM activity WHERE local_date = '2026-10-13' AND block = 'lesen'")  // earlier tests ran this block
  await request.post('http://127.0.0.1:8001/api/activity/stop')
  await request.post('http://127.0.0.1:8001/api/plan/done', { data: { block: 'lesen', done: false } })
  await page.goto('/')
  const lesen = page.getByTestId('block-lesen')
  await expect(page.getByTestId('assign-lesen')).toContainText('tagesschau.de · Inland')   // what he read on Tuesday
  await expect(lesen.getByTestId('rate-ask')).toHaveCount(0)
  await page.getByTestId('start-lesen').click()
  await expect(page.getByTestId('stop-lesen')).toBeVisible()
  await page.getByTestId('stop-lesen').click()
  const ask = lesen.getByTestId('rate-ask').first()
  await expect(ask).toContainText('Wie viel hast du verstanden?')
  await expect(ask).toContainText('tagesschau.de · Inland: 3 Artikel')
  await ask.getByTestId('rate-20').click()
  await expect(page.getByTestId('rated-lesen')).toHaveText('Verstanden: 20 %')
  const hard = page.getByTestId('too-hard')
  await expect(hard).toContainText('Zu schwer: tagesschau.de · Inland: 3 Artikel (20 %)')
  await expect(hard).toContainText('tagesschau.de ist aus dem Plan: Frei lesen kommt jetzt von nachrichtenleicht.de')
  const rows = (await (await request.get('http://127.0.0.1:8001/api/ratings')).json()).ratings
  expect(rows.map((x: { date: string, block: string, item: string, pct: number }) => [x.date, x.block, x.item, x.pct]))
    .toContainEqual(['2026-10-13', 'lesen', 'news:inland:2026-10-13', 20])
  // the podcast after it is asked about on its own
  await expect(page.getByTestId('then-lesen-0').getByTestId('rate-ask')).toBeVisible()

  sql("DELETE FROM ratings WHERE local_date = '2026-10-13'")
  restore()
  expect(errors).toEqual([])
})

test('#25 Karten: the time to reveal sets the rating, the bar counts cards and waits for stepped ones', async ({ page, request }) => {
  const errors = watchConsole(page)
  await page.addInitScript(() => localStorage.setItem('kaskade.karten.autoplay', '0')) // the time from showing the card (#28 below: from the end of its audio)
  await page.clock.install({ time: new Date('2026-10-13T07:30:00Z') })
  const card = async () => (await (await request.get('http://127.0.0.1:8001/api/cards/next')).json())
  const last = () => sql('SELECT rating || "," || reveal_ms || "," || auto FROM review_log ORDER BY id DESC LIMIT 1')

  // a short sentence revealed after 2 s → "Gewusst · Leicht" (≥ 4 words: Leicht up to ≥ 2.3 s)
  let next = await card()
  const quick = Math.min(2000, next.timing.easyMs - 200)
  await page.goto('/karten')
  await expect(page.getByTestId('karte-satz')).toHaveText(next.card.sentence)
  await page.clock.runFor(quick)
  await page.keyboard.press('Space')
  await expect(page.getByTestId('karte-gewusst-label')).toHaveText(/^Gewusst · Leicht · \d+ (Min|Std|Tag|Tage|Mon\.)$/) // FSRS fuzzes the interval
  await page.keyboard.press('Space') // within 400 ms of revealing: ignored (double tap)
  await expect(page.getByTestId('karte-gewusst')).toBeVisible()
  await page.clock.runFor(500)
  await page.keyboard.press('Space')
  await expect(page.getByTestId('karte-satz')).not.toHaveText(next.card.sentence)
  const [r1, ms1, auto1] = last().split(',').map(Number)  // the browser clock also ticks on its own a little
  expect([r1, auto1]).toEqual([4, 1]); expect(ms1).toBeGreaterThanOrEqual(quick); expect(ms1).toBeLessThan(quick + 1000)

  // after 20 s → "Schwer"; N → Nicht gewusst = Nochmal
  next = await card()
  await expect(page.getByTestId('karte-satz')).toHaveText(next.card.sentence)
  await page.clock.runFor(20_000)
  await page.getByTestId('karte-reveal').click()
  await expect(page.getByTestId('karte-gewusst-label')).toContainText('Gewusst · Schwer')
  await expect(page.getByTestId('karte-nicht')).toContainText(/Nicht gewusst · \d+ (Min|Std|Tag|Tage)/)
  await page.keyboard.press('n')
  await expect(page.getByTestId('karte-satz')).not.toHaveText(next.card.sentence)
  const [r2, ms2, auto2] = last().split(',').map(Number)
  expect([r2, auto2]).toEqual([1, 0]); expect(ms2).toBeGreaterThanOrEqual(20_000); expect(ms2).toBeLessThan(21_000)

  // Only a card in a step is left (back in 50 min): the bar stays below 100 % and says when it comes back
  await request.put('http://127.0.0.1:8001/api/cards/settings', { data: { newPerDay: 0 } })
  const waitingId = sql('SELECT card_id FROM review_log WHERE rating = 1 ORDER BY id DESC LIMIT 1')
  const others = sql("SELECT group_concat(id) FROM cards WHERE status = 'learning' AND id != ?", waitingId)
  for (const id of others ? others.split(',') : []) await request.post(`http://127.0.0.1:8001/api/cards/${id}/known`)
  sql("UPDATE cards SET due = '2026-10-13T08:20:00+00:00' WHERE id = ?", waitingId)
  await page.reload()
  await expect(page.getByTestId('karten-wait')).toContainText('Noch 1 Karte — kommt in 30 Min wieder')
  await expect(page.getByTestId('karten-fertig')).toHaveCount(0)
  expect(Number(await page.getByTestId('karten-bar').getAttribute('data-pct'))).toBeLessThan(100)
  await expect(page.getByTestId('karten-progress')).toContainText(/\d+ fertig · 1 offen/)
  await page.clock.runFor(60_000)
  await expect(page.getByTestId('karten-wait')).toContainText('kommt in 29 Min wieder') // live countdown
  // "Fertig" only once nothing is open
  await request.post(`http://127.0.0.1:8001/api/cards/${waitingId}/known`)
  await page.reload()
  await expect(page.getByTestId('karten-fertig')).toContainText('Fertig für heute')
  await expect(page.getByTestId('karten-bar')).toHaveAttribute('data-pct', '100')
  await request.put('http://127.0.0.1:8001/api/cards/settings', { data: { newPerDay: 20 } })
  expect(errors).toEqual([])
})

const SHOTS = process.env.KASKADE_SHOTS ?? join(DATA_DIR, 'shots')

test('#28 Karten: the audio plays by itself, the timer on the card starts after it; the box turns autoplay off', async ({ page, request, browserName }) => {
  test.skip(browserName === 'firefox', 'Firefox finds no audio output on this server (OnMediaSinkAudioError), so no clip ever ends')
  const errors = watchConsole(page)
  await page.addInitScript(() => { try { localStorage.setItem('kaskade-theme', 'signal') } catch { /* about:blank */ } }) // the screens in Signal (#15), whatever the Stil test left
  await page.clock.install({ time: new Date('2026-10-13T07:30:00Z') })
  const next = async () => (await (await request.get('http://127.0.0.1:8001/api/cards/next')).json())
  const last = () => sql('SELECT rating || "," || reveal_ms || "," || auto || "," || autoplay FROM review_log ORDER BY id DESC LIMIT 1')
  const satz = page.getByTestId('karte-satz')
  const clock = page.getByTestId('karte-clock')
  const box = page.getByTestId('karte-autoplay')
  // as Matt gets there: Heute → Karten (the click lets the browser play sound)
  const open = async () => { await page.goto('/'); await page.getByRole('link', { name: 'Karten', exact: true }).first().click() }

  // Screens in Signal: during the clip, timer running, revealed — at 1280 and 480 px (nothing rated)
  let card = await next()
  for (const width of [1280, 480]) {
    await page.setViewportSize({ width, height: 900 })
    await open()
    await expect(satz).toHaveText(card.card.sentence)
    await expect(clock).toHaveText('0:00 · Audio')
    await page.getByTestId('karte').screenshot({ path: join(SHOTS, `karte-audio-${width}.png`) })
    await expect(clock).not.toHaveText('0:00 · Audio', { timeout: 5000 })
    await page.clock.runFor(1500)
    await expect(clock).toHaveText(/^0:0[12] · (Leicht|Gut)$/)
    await page.getByTestId('karte').screenshot({ path: join(SHOTS, `karte-vorne-${width}.png`) })
    await page.keyboard.press('Space')
    await expect(page.getByTestId('karte-back')).toBeVisible()
    await page.screenshot({ path: join(SHOTS, `karte-hinten-${width}.png`), fullPage: true })
  }
  await page.setViewportSize({ width: 1280, height: 900 })

  // Box on (default): the clip plays once, the timer starts at its end; revealing 2 s later → Leicht
  audioHits.clear()
  await open()
  await expect(satz).toHaveText(card.card.sentence)
  await expect(box).toBeChecked()
  await expect(page.getByTestId('karte-front-hint')).toHaveText('Zuhören, einmal laut mitsprechen, dann aufdecken.')
  await expect(clock).toHaveText('0:00 · Audio')
  await expect(clock).toHaveText('0:00 · Leicht', { timeout: 5000 }) // 'ended' → the timer runs
  expect(audioHits.get(card.card.id)).toBe(1)
  const quick = Math.min(2000, card.timing.easyMs - 300) // the browser clock also ticks a little on its own
  await page.clock.runFor(quick)
  await page.keyboard.press('Space')
  await expect(page.getByTestId('karte-gewusst-label')).toContainText('Gewusst · Leicht')
  const frozen = await clock.textContent()
  expect(frozen).toMatch(/^[12],\d s · Leicht$/)
  await page.clock.runFor(3000)
  await expect(clock).toHaveText(frozen!) // stops at reveal
  await page.keyboard.press('Space')
  await expect(satz).not.toHaveText(card.card.sentence)
  const [r1, ms1, auto1, ap1] = last().split(',').map(Number)
  expect([r1, auto1, ap1]).toEqual([4, 1, 1]); expect(ms1).toBeGreaterThanOrEqual(quick); expect(ms1).toBeLessThan(quick + 1000)

  // The next card plays its own audio, once; without focus the timer says "pausiert"
  const second = await next()
  await expect(satz).toHaveText(second.card.sentence)
  await expect(clock).not.toHaveText('0:00 · Audio', { timeout: 5000 })
  expect(audioHits.get(second.card.id)).toBe(1)
  await page.evaluate(() => window.dispatchEvent(new Event('blur')))
  await expect(clock).toHaveText(/^0:0\d · pausiert$/)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(clock).toHaveText(/^0:0\d · (Leicht|Gut|Schwer)$/)

  // Leertaste on the focused box toggles it and doesn't reveal; the choice survives a reload
  await box.focus()
  await page.keyboard.press('Space')
  await expect(box).not.toBeChecked()
  await expect(page.getByTestId('karte-back')).toHaveCount(0)
  await expect(page.getByTestId('karte-front-hint')).toHaveText('Verstehst du den ganzen Satz? Einmal laut mitsprechen, dann aufdecken.')
  await page.reload()
  await expect(satz).toHaveText(second.card.sentence)
  await expect(box).not.toBeChecked()
  // Box off: no audio, the timer starts on show
  await expect(clock).toHaveText('0:00 · Leicht')
  await page.clock.runFor(1200)
  await expect(clock).toHaveText('0:01 · Leicht')
  expect(audioHits.get(second.card.id)).toBe(1)
  await page.getByTestId('karte-reveal').click()
  await page.getByTestId('karte-gewusst').click()
  await expect(satz).not.toHaveText(second.card.sentence)
  const [, ms2, , ap2] = last().split(',').map(Number)
  expect(ap2).toBe(0); expect(ms2).toBeGreaterThanOrEqual(1200)
  const third = await next()
  expect(audioHits.get(third.card.id) ?? 0).toBe(0)

  // Box on again; undo brings the card back and plays its audio again
  await box.click()
  await expect(box).toBeChecked()
  await page.keyboard.press('z')
  await expect(satz).toHaveText(second.card.sentence)
  await expect(clock).toHaveText('0:00 · Audio')
  await expect.poll(() => audioHits.get(second.card.id)).toBe(2)
  // unticking during the clip stops it and starts the timer
  await box.click()
  await expect(clock).toHaveText('0:00 · Leicht')
  expect(errors).toEqual([])
})

test('#28 Karten: the browser refuses autoplay → one quiet line, the timer runs at once, A still plays', async ({ page }) => {
  const errors = watchConsole(page)
  // Safari, page opened without a click: play() is rejected until a key press (Playwright's goto counts as a gesture in Chromium)
  await page.addInitScript(() => {
    let gesture = false
    window.addEventListener('keydown', () => { gesture = true }, true)
    const play = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function () {
      return gesture ? play.call(this) : Promise.reject(new DOMException('no gesture', 'NotAllowedError'))
    }
  })
  audioHits.clear()
  await page.goto('/karten')
  const clock = page.getByTestId('karte-clock')
  await expect(page.getByTestId('karte-blocked')).toHaveText('Autoplay vom Browser blockiert — A drücken')
  await expect(clock).toHaveText(/^0:0\d · (Leicht|Gut|Schwer)$/) // not stuck at "0:00 · Audio"
  await page.waitForTimeout(1100)
  await expect(clock).not.toHaveText('0:00 · Leicht')
  await page.keyboard.press('a')
  await expect(page.getByTestId('karte-blocked')).toHaveCount(0)
  await expect.poll(() => [...audioHits.values()].reduce((a, b) => a + b, 0)).toBeGreaterThanOrEqual(1)
  await expect(clock).not.toHaveText(/Audio|pausiert/) // replaying with A doesn't stop the timer
  await page.getByTestId('karte-reveal').click()
  await page.getByTestId('karte-nicht').click()
  await expect(page.getByTestId('karte-reveal')).toBeVisible()
  expect(sql('SELECT autoplay FROM review_log ORDER BY id DESC LIMIT 1')).toBe('0') // nothing played by itself: timed as without autoplay
  expect(errors).toEqual([])
})

/** #29: an invented Whisper transcript for the test clip (fuller than its SRT), imported like the Mac's. */
function whisperFixture(): string {
  const seg = (text: string, at: number, step: number, p = 0.92) => {
    const words = text.split(' ').map((w, i) => ({ w, s: +(at + i * step).toFixed(2), e: +(at + (i + 1) * step - 0.03).toFixed(2), p }))
    return { start: words[0].s, end: words.at(-1)!.e, text, no_speech_prob: 0.01, avg_logprob: -0.2, words }
  }
  return JSON.stringify({
    model: 'e2e',
    language: 'de',
    segments: [
      seg('Guten Morgen, wie geht es dir denn so?', 0.55, 0.13), // ends 1.56 — ARD's line runs to 2.0
      seg('Danke, mir geht es heute richtig gut.', 2.55, 0.19),
      // 4.5–6.0: Whisper heard nothing — ARD's line stands in
      seg('Leider nicht, ich muss noch arbeiten.', 6.55, 0.2),
      seg('Vielen Dank.', 8.6, 0.15, 0.5) // over no subtitle, unsure: a hallucination, dropped
    ]
  })
}

test('#29 Schauen: the spoken line (KI-Transkript) by default, ARD on the toggle, mining takes the spoken line', async ({ page, request }) => {
  const errors = watchConsole(page)
  await page.addInitScript(() => { try { localStorage.setItem('kaskade-theme', 'signal') } catch { /* about:blank */ } })
  const up = await request.post('http://127.0.0.1:8001/api/media/upload', {
    multipart: {
      title: 'E2E-Transkript',
      subtitles: { name: 'k.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(SRT) },
      media: { name: 'k.webm', mimeType: 'video/webm', buffer: readFileSync(testClip()) }
    }
  })
  const clip = await up.json()
  const file = sql('SELECT media_file FROM media WHERE id = ?', clip.id)
  mkdirSync(join(DATA_DIR, 'transcripts'), { recursive: true })
  writeFileSync(join(DATA_DIR, 'transcripts', file.replace(/\.[^.]+$/, '.whisper.json')), whisperFixture())
  const imported = JSON.parse(execFileSync('../server/.venv/bin/python', ['-m', 'kaskade.transcripts'],
    { cwd: '../server', env: { ...process.env, KASKADE_DATA_DIR: DATA_DIR } }).toString())
  expect(imported.withTranscript).toContain(clip.id)

  await page.goto(`/schauen/${clip.id}`)
  const line = page.getByTestId('watch-line')
  const video = page.getByTestId('watch-video')
  await expect(page.getByTestId('watch-ki')).toHaveText('KI-Transkript')
  await expect(page.getByTestId('track-spoken')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('4 Zeilen')).toBeVisible() // "Vielen Dank." over silence is gone
  await page.getByTestId('watch-play').click()
  await expect(line).toContainText('Guten Morgen, wie geht es dir denn so?')
  // auto-pause after the spoken line (ends 1.56 s), well before ARD's line would end (2.0 s)
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.paused), { timeout: 8000 }).toBe(true)
  const pausedAt = await video.evaluate((v: HTMLVideoElement) => v.currentTime)
  expect(pausedAt).toBeGreaterThanOrEqual(1.56); expect(pausedAt).toBeLessThan(1.9)
  await expect(line).toContainText('Guten Morgen, wie geht es dir denn so?')
  for (const width of [1280, 480]) {
    await page.setViewportSize({ width, height: 900 })
    await line.screenshot({ path: join(SHOTS, `schauen-zeile-${width}.png`) })
  }
  await page.setViewportSize({ width: 1280, height: 900 })

  // the toggle: ARD's line at the same time, remembered across a reload
  await page.getByTestId('track-ard').click()
  await expect(line).toContainText('Guten Morgen, wie geht es dir?')
  await expect(line).not.toContainText('denn so')
  await expect(page.getByTestId('watch-ki')).toHaveCount(0)
  await page.goto(`/schauen/${clip.id}?t=2.6`) // a new page load, at the second line
  await expect(page.getByTestId('track-ard')).toHaveAttribute('aria-pressed', 'true')
  await expect(line).toContainText('Danke, mir geht es gut.')
  await page.getByTestId('track-spoken').click()

  // mining a spoken line: its text and its word times
  await expect(line).toContainText('Danke, mir geht es heute richtig gut.')
  await video.evaluate((v: HTMLVideoElement) => v.pause())
  await line.locator('.at-word', { hasText: /^richtig$/ }).click()
  await expect(page.getByTestId('word-panel')).toContainText('Danke, mir geht es heute richtig gut.')
  await page.getByTestId('mine').click()
  await expect(page.getByTestId('word-panel')).toContainText('Gemined')
  const mined = await (await request.get('http://127.0.0.1:8001/api/mined')).json()
  const card = mined.find((c: { sentence: string }) => c.sentence === 'Danke, mir geht es heute richtig gut.')
  expect([card.mediaId, card.clipStart, card.clipEnd, card.transcript]).toEqual([clip.id, 2.55, 3.85, true])
  // Z on the spoken track stores that line
  await page.keyboard.press('z')
  const lastMark = async () => (await (await request.get(`http://127.0.0.1:8001/api/media/${clip.id}/hard`)).json()).marks.at(-1)
  await expect.poll(lastMark).toMatchObject({ text: 'Danke, mir geht es heute richtig gut.', start: 2.55, track: 'spoken' })
  // … and goes on to the next line: there Whisper heard nothing, so ARD's line stands in, labelled as such
  await expect(line).toContainText('Hast du heute Zeit für einen Kaffee?')
  await expect(page.getByTestId('watch-standin')).toHaveText('ARD-Untertitel — hier hat die KI nichts gehört')
  await expect(page.getByTestId('watch-ki')).toHaveCount(0)
  await video.evaluate((v: HTMLVideoElement) => v.pause())
  // the card says where its sentence comes from (older unseen mined cards out of the way, no daily limit)
  await page.goto('about:blank')
  for (const c of mined) {
    if (c.id !== card.id && !sql('SELECT 1 FROM cards WHERE id = ?', c.id)) await request.post(`http://127.0.0.1:8001/api/cards/${c.id}/known`)
  }
  await request.put('http://127.0.0.1:8001/api/cards/settings', { data: { newPerDay: 200 } })
  await page.goto('/karten')
  await expect(page.getByTestId('karte-satz')).toHaveText('Danke, mir geht es heute richtig gut.')
  await page.keyboard.press('Space')
  await expect(page.getByTestId('karte-transcript')).toHaveText('KI-Transkript')
  await request.put('http://127.0.0.1:8001/api/cards/settings', { data: { newPerDay: 20 } })
  expect(errors).toEqual([])
})

// ── #34: separable verbs; a line inside its sentence ──

test('#34 Schauen: fällt … ein is einfallen on both words, a sentence over two lines is parsed and mined whole', async ({ page, request }) => {
  const errors = watchConsole(page)
  const SPLIT = srtOf([[0.5, 2.0, 'Mir fällt heute nichts ein.'], [2.5, 4.0, 'Dabei fängt der Film'], [4.0, 5.5, 'gleich an.']])
  const up = await request.post('http://127.0.0.1:8001/api/media/upload', {
    multipart: {
      title: 'E2E-Trennbar',
      subtitles: { name: 's.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(SPLIT) },
      media: { name: 's.webm', mimeType: 'video/webm', buffer: readFileSync(testClip()) }
    }
  })
  const clip = await up.json()
  await page.goto(`/schauen/${clip.id}`)
  const line = page.getByTestId('watch-line')
  const panel = page.getByTestId('word-panel')
  const video = page.getByTestId('watch-video')
  await page.getByTestId('watch-play').click()
  await expect(line).toContainText('Mir fällt heute nichts ein.')
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.paused), { timeout: 8000 }).toBe(true)

  // tap fällt: the panel shows einfallen, and both halves are marked
  await line.locator('.at-word', { hasText: /^fällt$/ }).click()
  await expect(panel).toContainText('einfallen · fiel ein · ist eingefallen')
  await expect(page.getByTestId('word-split')).toHaveText('Trennbares Verb: fällt … ein')
  await expect(line.locator('.at-selected')).toHaveText(['fällt', 'ein'])
  // the prefix alone gives the same word
  await line.locator('.at-word', { hasText: /^ein$/ }).click()
  await expect(panel).toContainText('einfallen · fiel ein · ist eingefallen')
  await expect(line.locator('.at-selected')).toHaveText(['fällt', 'ein'])
  for (const width of [1280, 480]) {
    await page.setViewportSize({ width, height: 900 })
    await page.locator('.sw-grid').screenshot({ path: join(SHOTS, `schauen-trennbar-${width}.png`) })
  }
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.getByTestId('mine').click()
  await expect(panel).toContainText('Gemined')
  let mined = await (await request.get('http://127.0.0.1:8001/api/mined')).json()
  const one = mined.find((c: { sentence: string }) => c.sentence === 'Mir fällt heute nichts ein.')
  expect([one.lemma, one.display, one.target]).toEqual(['einfallen', 'einfallen · fiel ein · ist eingefallen', 'fällt'])

  // the next line starts a sentence that ends on the line after: verb here, prefix there
  await page.keyboard.press('ArrowRight')
  await expect(line).toContainText('Dabei fängt der Film')
  await video.evaluate((v: HTMLVideoElement) => v.pause())
  await expect(line).not.toContainText('gleich an')
  await line.locator('.at-word', { hasText: /^fängt$/ }).click()
  await expect(panel).toContainText('anfangen · fing an · hat angefangen')
  await expect(panel).toContainText('„Dabei fängt der Film gleich an.“')
  await page.getByTestId('mine').click()
  await expect(panel).toContainText('Gemined')
  mined = await (await request.get('http://127.0.0.1:8001/api/mined')).json()
  const two = mined.find((c: { sentence: string }) => c.sentence === 'Dabei fängt der Film gleich an.')
  expect([two.lemma, two.target, two.mediaId, two.clipStart, two.clipEnd]).toEqual(['anfangen', 'fängt', clip.id, 2.5, 5.5])
  // … and on the second line the prefix knows its verb
  await page.keyboard.press('ArrowRight')
  await expect(line).toContainText('gleich an.')
  await video.evaluate((v: HTMLVideoElement) => v.pause())
  await line.locator('.at-word', { hasText: /^an$/ }).click()
  await expect(panel).toContainText('anfangen · fing an · hat angefangen')
  await expect(page.getByTestId('word-split')).toHaveText('Trennbares Verb: fängt … an')
  expect(errors).toEqual([])
})

// ── #30: Schauen jumped back to 0:00 ──

/** An invented 89-min clip (grey, silent): one 60-s piece, joined 90 times — quick to make. */
function longClip(): string {
  mkdirSync(TMP, { recursive: true })
  const out = join(TMP, 'lang.webm')
  if (!existsSync(out)) {
    const piece = join(TMP, 'lang-60s.webm')
    execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:s=64x36:r=2:d=60',
      '-f', 'lavfi', '-i', 'anullsrc=r=22050:cl=mono', '-t', '60', '-c:v', 'libvpx', '-b:v', '20k', '-g', '20',
      '-c:a', 'libvorbis', '-q:a', '0', piece])
    writeFileSync(join(TMP, 'lang.txt'), Array(90).fill(`file '${piece}'`).join('\n'))
    execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', join(TMP, 'lang.txt'), '-t', '5361', '-c', 'copy', out])
  }
  return out
}

/** Shaped like Tatort: Schweigen (invented lines): a credit line at 0:00, a minute without speech, lines around 62:26. */
const LONG_CUES: [number, number, string][] = [
  [0, 3.04, 'Untertitel: Testfunk 2026'], [5.92, 10.52, '♪ Titelmusik ♪'], [69.24, 70.92, 'Hallo? Ist da wer?'],
  [3739.96, 3741.44, 'Wo ist mein Schlüssel?'], [3748.28, 3749.8, 'Kommst du mit ins Kino?'], [3750.0, 3753.0, 'Ich habe leider keine Zeit.'],
  [3757.2, 3759.4, 'Morgen kaufe ich eine Lampe.'], [3761.0, 3763.0, 'Wir fahren morgen nach Hamburg.'], [5359, 5360, 'Ende.']
]
function srtOf(cues: [number, number, string][]): string {
  const ts = (x: number) => {
    const ms = Math.round(x * 1000)
    const p = (n: number, w = 2) => String(n).padStart(w, '0')
    return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`
  }
  return cues.map(([a, b, text], i) => `${i + 1}\n${ts(a)} --> ${ts(b)}\n${text}\n`).join('\n')
}
/** Its Whisper transcript (invented): "Musik" over the credits at 0:00, as on Thursday, and fuller lines. */
function longWhisper(): string {
  const seg = (text: string, at: number, step: number) => {
    const words = text.split(' ').map((w, i) => ({ w, s: +(at + i * step).toFixed(2), e: +(at + (i + 1) * step - 0.03).toFixed(2), p: 0.92 }))
    return { start: words[0].s, end: words.at(-1)!.e, text, no_speech_prob: 0.01, avg_logprob: -0.2, words }
  }
  return JSON.stringify({ model: 'e2e', language: 'de', version: 2, segments: [
    seg('Musik', 0, 1.47), seg('Hallo? Ist da wer?', 68.9, 0.4), seg('Wo ist mein Schlüssel?', 3739.66, 0.26),
    seg('Kommst du heute mit ins Kino?', 3747.86, 0.3), // ends 3749.63
    seg('Ich habe heute leider gar keine Zeit dafür.', 3750.34, 0.2), // ends 3751.94
    seg('Morgen kaufe ich mir eine neue Lampe.', 3756.94, 0.25), // ends 3758.66
    seg('Wir fahren morgen früh nach Hamburg.', 3760.9, 0.3)
  ] })
}
async function longTatort(request, title: string) {
  const up = await request.post('http://127.0.0.1:8001/api/media/upload', {
    multipart: {
      title,
      subtitles: { name: 'lang.srt', mimeType: 'application/x-subrip', buffer: Buffer.from(srtOf(LONG_CUES)) },
      media: { name: 'lang.webm', mimeType: 'video/webm', buffer: readFileSync(longClip()) }
    }
  })
  expect(up.ok()).toBeTruthy()
  const clip = await up.json()
  const file = sql('SELECT media_file FROM media WHERE id = ?', clip.id)
  mkdirSync(join(DATA_DIR, 'transcripts'), { recursive: true })
  writeFileSync(join(DATA_DIR, 'transcripts', file.replace(/\.[^.]+$/, '.whisper.json')), longWhisper())
  execFileSync('../server/.venv/bin/python', ['-m', 'kaskade.transcripts'], { cwd: '../server', env: { ...process.env, KASKADE_DATA_DIR: DATA_DIR } })
  return clip
}
/** Every position the page saves for `id`, and each save's body. */
function savedPositions(page: Page, id: number) {
  const saves: { position: number, reason?: string, from?: number }[] = []
  page.on('request', (r) => { if (r.method() === 'PUT' && r.url().endsWith(`/media/${id}/progress`)) saves.push(JSON.parse(r.postData() ?? '{}')) })
  return saves
}

test('#30 Schauen: play before the video has loaded still starts at today\'s part, and no control lands near 0:00', async ({ page, request }) => {
  test.setTimeout(120_000)
  const errors = watchConsole(page)
  const clip = await longTatort(request, 'E2E-Langfilm')
  await request.put(`http://127.0.0.1:8001/api/media/${clip.id}/progress`, { data: { position: 3746 } }) // yesterday's end
  const saves = savedPositions(page, clip.id)
  // a slow line: the video's first bytes come 2.5 s late (Thursday: the 6.6-MB header of the real MP4)
  await page.route('**/api/media/*/file', async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue() })
  await page.goto(`/schauen/${clip.id}?von=3746&bis=5361`)
  const video = page.getByTestId('watch-video')
  const line = page.getByTestId('watch-line')
  const at = () => video.evaluate((v: HTMLVideoElement) => v.currentTime)
  const pausedPast = (t: number) => expect.poll(() => video.evaluate((v: HTMLVideoElement, t) => v.paused && v.currentTime >= t, t), { timeout: 20_000 }).toBe(true)
  await expect(page.getByTestId('watch-range')).toContainText('Heute: 62:26–89:21.')
  await expect(line).toContainText('Wo ist mein Schlüssel?')
  expect(await video.evaluate((v: HTMLVideoElement) => v.readyState)).toBe(0) // nothing of the video there yet …
  await page.getByTestId('watch-play').click() // … and he presses play (this sent Thursday's first visit to 0:00)

  // 62:26, and the first play goes on to the end of the next line — no stop at once for the line before
  await pausedPast(3749.6)
  expect(await at()).toBeLessThan(3750.3)
  await expect(line).toContainText('Kommst du heute mit ins Kino?')
  await page.unroute('**/api/media/*/file')

  // every control, from 62:26: nothing may land near 0:00
  await page.keyboard.press('r') // the line again
  await expect.poll(at).toBeLessThan(3749)
  await pausedPast(3749.6)
  await page.keyboard.press('ArrowLeft')
  await expect(line).toContainText('Wo ist mein Schlüssel?')
  await pausedPast(3740.6)
  await page.getByTestId('watch-next').click()
  await expect(line).toContainText('Kommst du heute mit ins Kino?')
  await pausedPast(3749.6)
  await page.keyboard.press('z') // too hard: on to the next line
  await expect(line).toContainText('Ich habe heute leider gar keine Zeit dafür.')
  await pausedPast(3751.9)
  await page.getByTestId('track-ard').click()
  await expect(line).toContainText('Ich habe leider keine Zeit.')
  await page.getByTestId('track-spoken').click()
  await expect(line).toContainText('Ich habe heute leider gar keine Zeit dafür.')
  await page.getByRole('button', { name: '0,85×' }).click()
  expect(await video.evaluate((v: HTMLVideoElement) => v.playbackRate)).toBe(0.85)
  await page.keyboard.press('Space')
  await expect(line).toContainText('Morgen kaufe ich mir eine neue Lampe.', { timeout: 15_000 }) // 0,85×
  await pausedPast(3758.6)
  await line.locator('.at-word', { hasText: /^Lampe$/ }).click()
  await page.getByTestId('mine').click()
  await expect(page.getByTestId('word-panel')).toContainText(/Gemined|Satz schon gemint/) // another browser's run may have mined it
  await video.click() // the video itself: play …
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.paused)).toBe(false)
  await video.click() // … and pause
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.paused)).toBe(true)
  const other = await page.context().newPage() // a tab switch
  await other.goto('about:blank')
  await other.bringToFront()
  await other.waitForTimeout(1000)
  await page.bringToFront()
  await other.close()
  await page.getByTestId('watch-play').click()
  await expect.poll(at).toBeGreaterThan(3759)
  await page.getByTestId('watch-play').click()

  expect(await at()).toBeGreaterThan(3700)
  await expect.poll(() => saves.length).toBeGreaterThan(3)
  expect(Math.min(...saves.map((s) => s.position))).toBeGreaterThan(3740) // never 0, never 0:06
  expect(saves.some((s) => s.reason)).toBe(false) // no jump
  expect((await (await request.get(`http://127.0.0.1:8001/api/media/${clip.id}`)).json()).position).toBeGreaterThan(3740)
  expect(errors).toEqual([])
})

test('#30 Starten after a jump: the saved 0:06 doesn\'t pull him back, and "Zurück zu 62:26" fixes a jump on the page', async ({ page, request }) => {
  const errors = watchConsole(page)
  await page.addInitScript(() => { try { localStorage.setItem('kaskade-theme', 'signal') } catch { /* about:blank */ } })
  const clip = await longTatort(request, 'E2E-Langfilm mit Plan')
  // yesterday's part (block "e2e30", so the real plan blocks stay as they are) ended at 62:26 — then a jump saved 0:06
  sql("UPDATE media SET key = 'e2e-lang' WHERE id = ?", clip.id)
  sql("INSERT INTO watch_ranges(local_date, block, clip, start, end, clean, reached) VALUES ('2026-10-12', 'e2e30', 'e2e-lang', 2046, 3746, 1, 3746.0)")
  await request.put(`http://127.0.0.1:8001/api/media/${clip.id}/progress`, { data: { position: 6.85 } })
  const saves = savedPositions(page, clip.id)
  try {
    await page.goto(`/schauen/${clip.id}?von=3746&bis=5361`)
    const video = page.getByTestId('watch-video')
    const at = () => video.evaluate((v: HTMLVideoElement) => v.currentTime)
    await expect(page.getByTestId('watch-range')).toHaveText('Heute: 62:26–89:21 (zuletzt gespeichert: 0:06). Das Video hält am Ende des Teils einmal an.')
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => !v.seeking && Math.abs(v.currentTime - 3746) < 0.1)).toBe(true)
    await expect(page.getByTestId('watch-back')).toHaveCount(0)

    // something (not him) moves the playhead to 0:05: the page shows it, offers the way back, and the next save says so
    await video.evaluate((v: HTMLVideoElement) => { v.currentTime = 5 })
    const back = page.getByTestId('watch-back')
    await expect(back).toHaveText('↩ Zurück zu 62:26 (Teil von heute)')
    await expect(page.getByTestId('watch-clock')).toContainText('0:05 / Ziel 89:21')
    for (const width of [1280, 480]) {
      await page.setViewportSize({ width, height: 900 })
      await back.locator('..').screenshot({ path: join(SHOTS, `schauen-zurueck-${width}.png`) })
    }
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.getByTestId('watch-play').click()
    await page.getByTestId('watch-play').click()
    await expect.poll(() => saves.find((s) => s.reason)).toMatchObject({ reason: 'jump', from: 3746 })
    expect(saves.find((s) => s.reason)!.position).toBeLessThan(10)
    await back.click()
    await expect.poll(at).toBeCloseTo(3746, 1)
    await expect(back).toHaveCount(0)
    await expect(page.getByTestId('watch-clock')).toContainText('62:26 / Ziel 89:21')
    expect(errors).toEqual([])
  } finally {
    sql("DELETE FROM watch_ranges WHERE block = 'e2e30'")
    sql('UPDATE media SET key = NULL WHERE id = ?', clip.id)
  }
})

test('#36 Woche frei nehmen: preview, take a later week off, the dates move, undo — and Heute in a week off', async ({ page }) => {
  const errors = watchConsole(page)
  await page.addInitScript(() => { try { localStorage.setItem('kaskade-theme', 'signal') } catch { /* about:blank */ } })
  const restore = asMatt()
  try {
    await page.goto('/fahrplan')
    const notice = page.getByTestId('fp-notice-kling-qualityland')
    await expect(notice).toContainText('ab 2.11. im Plan, Woche 4')
    const box = page.getByTestId('fp-pause')
    await box.getByTestId('fp-pause-select').selectOption('2026-10-26')
    const preview = box.getByTestId('fp-pause-preview')
    await expect(preview).toContainText('beginnt Mo 2.11. statt Mo 26.10. — alles danach eine Woche später.')
    await expect(preview).toContainText('Marc-Uwe Kling: QualityLand: fällig Sa 7.11. statt Sa 31.10.')
    await expect(preview).toContainText('Heute zeigt dann: „Freie Woche bis So 1.11. — weiter am Mo 2.11.')
    for (const width of [1280, 480]) {
      await page.setViewportSize({ width, height: 900 })
      await box.screenshot({ path: join(SHOTS, `fahrplan-woche-frei-${width}.png`) })
    }
    await box.getByTestId('fp-pause-take').click()
    await expect(box.getByTestId('fp-pause-2026-10-26')).toContainText('Frei: Mo 26.10.–So 1.11.')
    await expect(preview).toHaveCount(0)
    await expect(notice).toContainText('ab 9.11. im Plan, Woche 4')   // every date follows the shifted plan
    await page.goto('/')
    await expect(page.getByTestId('block-karten')).toBeVisible()      // this week isn't the one off
    await page.goto('/fahrplan')
    await box.getByTestId('fp-pause-undo-2026-10-26').click()
    await expect(box.getByTestId('fp-pauses')).toHaveCount(0)
    await expect(notice).toContainText('ab 2.11. im Plan, Woche 4')

    // the week off is this one: one calm line on Heute, no blocks, Karten optional, the days "frei"
    sql("INSERT INTO settings(key, value) VALUES ('pauses', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
      JSON.stringify([{ from: '2026-10-12', to: '2026-10-18' }]))
    await page.goto('/')
    await expect(page.getByTestId('heute-pause')).toContainText('Freie Woche bis So 18.10. — weiter am Mo 19.10.')
    await expect(page.getByTestId('pause-karten')).toContainText(/Karten freiwillig · \d+ fällig/)
    await expect(page.getByTestId('block-karten')).toHaveCount(0)
    await expect(page.getByTestId('timeline')).toHaveCount(0)
    await expect(page.getByTestId('too-hard')).toHaveCount(0)
    await expect(page.getByTestId('free-6')).toHaveText('frei')
    for (const width of [1280, 480]) {
      await page.setViewportSize({ width, height: 900 })
      await page.screenshot({ path: join(SHOTS, `heute-woche-frei-${width}.png`), fullPage: true })
    }
  } finally {
    sql("DELETE FROM settings WHERE key = 'pauses'")
    restore()
  }
  expect(errors).toEqual([])
})
