import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The Kaskade API runs on 127.0.0.1:8000 (never public); both the dev server
// and `vite preview` (the kaskade-web service) proxy /api to it.
// KASKADE_API points the proxy elsewhere (E2E runs use a throwaway API on 8001).
const apiProxy = {
  '/api': { target: process.env.KASKADE_API || 'http://127.0.0.1:8000', changeOrigin: false }
}

// https://vite.dev/config/
// VITE_BASE lets the GitHub Pages workflow serve the app from a sub-path
// (e.g. /kaskade/). Netlify and local dev use the default '/'.
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [vue()],
  server: { proxy: apiProxy },
  preview: {
    proxy: apiProxy,
    // Reachable by Tailscale IP or MagicDNS name only (bound to 100.64.43.3).
    allowedHosts: ['.ts.net', 'cos-vps']
  }
})
