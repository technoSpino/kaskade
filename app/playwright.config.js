import { defineConfig, devices } from '@playwright/test';

// Legacy A2 pages (tests/). The app shell asks the Kaskade API for its status on every page, so
// this suite starts its own throwaway API (127.0.0.1:8002, data in app/.e2e-legacy-data) and dev
// server (127.0.0.1:5175). Without it, /api fails in CI, and on the box the tests would talk to
// the live API on :8000.
const DATA = '.e2e-legacy-data';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  use: {
    baseURL: 'http://127.0.0.1:5175',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: [
    {
      command: `rm -rf ${DATA} && KASKADE_OFFLINE=1 KASKADE_TRANSCODE=0 KASKADE_DATA_DIR=$PWD/${DATA} ../server/.venv/bin/uvicorn kaskade.main:app --app-dir ../server --host 127.0.0.1 --port 8002`,
      url: 'http://127.0.0.1:8002/api/health',
      reuseExistingServer: false,
    },
    {
      command: 'KASKADE_API=http://127.0.0.1:8002 npx vite --host 127.0.0.1 --port 5175 --strictPort',
      url: 'http://127.0.0.1:5175',
      reuseExistingServer: false,
    },
  ],
});
