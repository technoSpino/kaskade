import { defineStore } from 'pinia'
import { api } from '../lib/api'
import { applyTheme, resolveTheme, storeTheme, storedTheme, systemTheme } from '../lib/theme'

// Global learner status shown in the header (phase, running block timer, Stil).
export const useStatusStore = defineStore('kaskadeStatus', {
  state: () => ({
    phase: null,
    running: null,
    theme: resolveTheme({ local: storedTheme(), server: null, system: systemTheme() }),
    loaded: false,
    httpsUrl: null,
    error: null
  }),
  actions: {
    async load() {
      try {
        const s = await api.get('/status')
        this.phase = s.phase
        this.running = s.running
        this.httpsUrl = s.httpsUrl ?? null
        this.theme = resolveTheme({ local: storedTheme(), server: s.theme, system: systemTheme() })
        applyTheme(this.theme)
        this.error = null
      } catch (e) {
        this.error = e.message
      }
      this.loaded = true
    },
    async setTheme(id) {
      this.theme = id
      applyTheme(id)
      storeTheme(id)
      try {
        await api.put('/settings/theme', { theme: id })
      } catch {
        // offline: the local choice still applies
      }
    },
    followSystem() {
      // Without an explicit choice, react to the OS switching light/dark.
      try {
        const mq = globalThis.matchMedia?.('(prefers-color-scheme: dark)')
        mq?.addEventListener?.('change', () => {
          if (!storedTheme()) {
            this.theme = systemTheme()
            applyTheme(this.theme)
          }
        })
      } catch {
        // matchMedia unavailable
      }
    },
    async startTimer(block) {
      const r = await api.post('/activity/start', { block })
      this.running = r
      return r
    },
    async stopTimer() {
      await api.post('/activity/stop')
      this.running = null
    }
  }
})
