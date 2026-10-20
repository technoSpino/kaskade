import { defineConfig, devices } from '@playwright/test'

// E2E smoke tests for Kaskade:  npm run build && npm run test:e2e:kaskade
// Starts its own API (127.0.0.1:8001, throwaway data in app/.e2e-data) and a
// preview server (127.0.0.1:5174), so tests never touch the real ~/kaskade-data.
const DATA = '.e2e-data'

// #28: the Karten audio tests also run in WebKit (Safari's engine: autoplay rules), and so do #30's
// Schauen start tests (a video that loads slowly). Opt-in: Playwright
// has no WebKit build for Ubuntu 26.04 — the 24.04 one runs with the libraries it misses unpacked
// (no root) in KASKADE_WEBKIT_ROOT, drawing with Mesa's software renderer. Set up and run as in
// deploy/webkit-e2e-setup.sh (PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1).
const KARTEN = /#28|#25 Karten|Karten: reveal|Karten audio|#30/
const WK = process.env.KASKADE_WEBKIT_ROOT
const webkit = WK
  ? [{
      name: 'webkit',
      grep: KARTEN,
      use: {
        ...devices['Desktop Safari'],
        permissions: [],
        launchOptions: {
          env: {
            ...process.env,
            LD_LIBRARY_PATH: `${WK}/usr/lib/x86_64-linux-gnu`,
            GST_PLUGIN_PATH: `${WK}/usr/lib/x86_64-linux-gnu/gstreamer-1.0`,
            __EGL_VENDOR_LIBRARY_DIRS: `${WK}/usr/share/glvnd/egl_vendor.d`,
            EGL_PLATFORM: 'surfaceless',
            LIBGL_ALWAYS_SOFTWARE: '1'
          }
        }
      }
    }]
  : []
// … and in Firefox (KASKADE_FIREFOX=1): it also holds back sound until the page had a click
const firefox = process.env.KASKADE_FIREFOX
  ? [{ name: 'firefox', grep: KARTEN, use: { ...devices['Desktop Firefox'], permissions: [], launchOptions: {} } }]
  : []

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    // Fake microphone for the Sprechen recordings.
    permissions: ['microphone'],
    launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] }
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }, ...webkit, ...firefox],
  webServer: [
    {
      // Server clock pinned to Tuesday of plan week 1, 09:30 Berlin. No H.264 conversion:
      // Playwright's Chromium can't play H.264, so test clips stay WebM.
      command: `rm -rf ${DATA} && KASKADE_OFFLINE=1 KASKADE_TRANSCODE=0 KASKADE_NOW=2026-10-13T07:30:00+00:00 KASKADE_DATA_DIR=$PWD/${DATA} ../server/.venv/bin/uvicorn kaskade.main:app --app-dir ../server --host 127.0.0.1 --port 8001`,
      url: 'http://127.0.0.1:8001/api/health',
      reuseExistingServer: false
    },
    {
      // KASKADE_DIST: test a build outside app/dist (which the live site serves)
      command: `KASKADE_API=http://127.0.0.1:8001 npx vite preview --host 127.0.0.1 --port 5174 --strictPort --outDir ${process.env.KASKADE_DIST ?? 'dist'}`,
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: false
    }
  ]
})
