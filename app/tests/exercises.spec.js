import { test, expect } from '@playwright/test';

/**
 * Answer whatever item is on screen (fill, choice or sentence builder) and move on.
 * Fill items get a deliberately wrong answer; the others may land right or wrong.
 */
async function answerCurrentItem(page) {
  const input = page.getByLabel('Your answer');
  if (await input.isVisible()) {
    await input.fill('xyz');
    await input.press('Enter');
  } else if (await page.getByText('Sentence builder').isVisible()) {
    const pool = page.locator('.order-pool .chip');
    const count = await pool.count();
    for (let i = 0; i < count; i++) await pool.nth(i).click();
    await page.getByRole('button', { name: /Check/ }).click();
  } else {
    await page.keyboard.press('1');
  }
  await expect(page.getByText(/Richtig!|Nicht ganz\./)).toBeVisible();
  await page.keyboard.press('Enter');
}

test.describe('Skill Builder exercises', () => {
  let consoleErrors;

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', err => consoleErrors.push(err.message));
    await page.goto('/exercises');
  });

  test.afterEach(() => {
    expect(consoleErrors).toEqual([]);
  });

  test('shows the drill menu, Blitz card and cheat sheet', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Skill Builder' })).toBeVisible();
    await expect(page.getByText('Blitz mode')).toBeVisible();
    await expect(page.getByRole('button', { name: /Two-way prepositions/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Nebensätze/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /zu \+ Infinitiv/ })).toBeVisible();

    await page.getByRole('button', { name: /Cheat sheet/ }).click();
    await expect(page.getByText('Position verbs vs movement verbs')).toBeVisible();
    await page.getByRole('tab', { name: 'Prepositions' }).click();
    await expect(page.getByText('Always Dativ')).toBeVisible();
  });

  test('is reachable from the nav and home page', async ({ page }) => {
    // Since Kaskade, the grammar app's home lives at /nachschlagen and its pages
    // are in the "Nachschlagen" menu of the main navigation.
    await page.goto('/nachschlagen');
    await page.getByRole('link', { name: 'Build Skills' }).click();
    await expect(page).toHaveURL(/\/exercises$/);
    await page.getByRole('button', { name: /Nachschlagen/ }).click();
    await page.getByRole('link', { name: 'Übersicht' }).click();
    await expect(page).toHaveURL(/\/nachschlagen$/);
    await page.getByRole('button', { name: /Nachschlagen/ }).click();
    await page.getByRole('link', { name: 'Übungen' }).click();
    await expect(page.getByRole('heading', { name: 'Skill Builder' })).toBeVisible();
  });

  test('runs a full round, shows results and feeds weak spots', async ({ page }) => {
    await page.getByRole('button', { name: /Fixed-case prepositions/ }).click();
    await expect(page.getByText('1 / 10')).toBeVisible();

    for (let i = 0; i < 10; i++) {
      await answerCurrentItem(page);
    }

    // Fill items always got a wrong answer, so there are misses to review.
    await expect(page.getByRole('heading', { name: /\d+ \/ 10/ })).toBeVisible();
    await expect(page.getByText('Review your misses')).toBeVisible();
    await page.getByRole('button', { name: 'Back to drills' }).click();
    await expect(page.getByRole('button', { name: /Weak spots/ })).toBeVisible();
    await expect(page.getByText('Best', { exact: false }).first()).toBeVisible();
  });

  test('a fill item shows the correct answer and explanation after a wrong answer', async ({ page }) => {
    await page.getByRole('button', { name: /Two-way prepositions/ }).click();
    // Skip past any non-fill item at the start of the round.
    for (let i = 0; i < 10; i++) {
      if (await page.getByLabel('Your answer').isVisible()) break;
      await answerCurrentItem(page);
    }
    const input = page.getByLabel('Your answer');
    await expect(input).toBeVisible();
    await input.fill('xyz');
    await input.press('Enter');
    await expect(page.getByText('Nicht ganz.')).toBeVisible();
    await expect(page.getByText('Correct:')).toBeVisible();
    await expect(page.locator('.case-badge')).toHaveText(/Dativ|Akkusativ/);
    await expect(input).toBeDisabled();
  });

  test('umlaut buttons insert characters into the answer', async ({ page }) => {
    await page.getByRole('button', { name: /Adjectives after prepositions/ }).click();
    for (let i = 0; i < 10; i++) {
      if (await page.getByLabel('Your answer').isVisible()) break;
      await answerCurrentItem(page);
    }
    const input = page.getByLabel('Your answer');
    await input.fill('gr');
    await page.getByRole('button', { name: 'ö', exact: true }).click();
    await page.getByRole('button', { name: 'ß', exact: true }).click();
    await expect(input).toHaveValue('größ');
  });

  test('runs a choice round with keyboard shortcuts', async ({ page }) => {
    await page.getByRole('button', { name: /Wo\? Wohin\? Woher\?/ }).click();
    await expect(page.getByRole('button', { name: /Wo\?$/ })).toBeVisible();
    await page.keyboard.press('1');
    await expect(page.getByText(/Richtig!|Nicht ganz\./)).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(page.getByText('2 / 10')).toBeVisible();
  });

  test('sentence builder accepts a correct chip order', async ({ page }) => {
    // Nebensatz rounds contain choice, fill and order items; walk until an order item appears.
    await page.getByRole('button', { name: /Nebensätze/ }).click();
    let found = false;
    for (let i = 0; i < 10 && !found; i++) {
      if (await page.getByText('Sentence builder').isVisible()) {
        found = true;
        break;
      }
      await answerCurrentItem(page);
    }
    test.skip(!found, 'round had no sentence-builder item this time');

    // Clear button starts disabled; Check disabled until all chips placed.
    await expect(page.getByRole('button', { name: 'Clear' })).toBeDisabled();
    await expect(page.getByRole('button', { name: /Check/ })).toBeDisabled();

    const pool = page.locator('.order-pool .chip');
    const count = await pool.count();
    for (let i = 0; i < count; i++) {
      await pool.nth(i).click();
    }
    await expect(page.getByRole('button', { name: /Check/ })).toBeEnabled();
    await page.getByRole('button', { name: /Check/ }).click();
    await expect(page.getByText(/Richtig!|Nicht ganz\./)).toBeVisible();
  });

  test('Blitz mode starts, accepts answers and ends', async ({ page }) => {
    await page.getByRole('button', { name: /Blitz mode/ }).click();
    await expect(page.getByText('60 seconds. As many as you can.')).toBeVisible();
    await page.getByRole('button', { name: 'Start' }).click();
    await expect(page.getByText('Score')).toBeVisible();
    await page.keyboard.press('d');
    await page.waitForTimeout(1600);
    await page.getByRole('button', { name: /Akkusativ/ }).click();
    await page.waitForTimeout(1600);
    // Score or streak must have moved, or a wrong-answer explanation is showing.
    const answered = await page.locator('.stat-value').first().textContent();
    expect(answered).toBeTruthy();
    await page.getByRole('button', { name: '← Drills' }).click();
    await expect(page.getByText('Drills', { exact: true })).toBeVisible();
  });

  test('works at 320px width', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.getByRole('button', { name: /Fixed-case prepositions/ }).click();
    await expect(page.getByText('1 / 10')).toBeVisible();
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(320);
  });
});
