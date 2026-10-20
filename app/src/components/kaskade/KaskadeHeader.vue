<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useStatusStore } from '../../stores/statusStore'
import { BLOCK_LABELS, useNow } from '../../lib/useNow'
import { formatClock } from '../../lib/format'
import { THEMES } from '../../lib/theme'

const route = useRoute()
const status = useStatusStore()
const refOpen = ref(false)
const now = useNow()
const elapsed = computed(() =>
  status.running ? formatClock((now.value - new Date(status.running.startedAt)) / 1000) : ''
)

const links = [
  { to: '/', label: 'Heute' },
  { to: '/einstufung', label: 'Einstufung' },
  { to: '/satz-check', label: 'Satz-Check' },
  { to: '/karten', label: 'Karten' },
  { to: '/schauen', label: 'Schauen' },
  { to: '/lesen', label: 'Lesen' },
  { to: '/pruefung', label: 'Prüfung' },
  { to: '/fahrplan', label: 'Fahrplan' }
]

const reference = [
  { to: '/nachschlagen', label: 'Übersicht' },
  { to: '/tables', label: 'Deklination' },
  { to: '/modal-verbs', label: 'Modalverben' },
  { to: '/sentence-structure', label: 'Satzbau' },
  { to: '/verb-conjugation', label: 'Konjugation' },
  { to: '/past-tense', label: 'Perfekt' },
  { to: '/prepositions', label: 'Präpositionen' },
  { to: '/werden', label: 'werden' },
  { to: '/flashcards', label: 'Grammatik-Karten' },
  { to: '/exercises', label: 'Übungen' }
]

const isActive = (to) => (to === '/' ? route.path === '/' || route.path === '/heute' : route.path.startsWith(to))
const refActive = () => reference.some((r) => route.path === r.to)

watch(() => route.path, () => { refOpen.value = false })
status.load()
status.followSystem()
</script>

<template>
  <header class="k-header">
    <div class="k-header-in">
      <router-link to="/" class="k-logo">
        <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
          <rect x="1" y="2" width="6" height="18" rx="1" class="k-logo-a" />
          <rect x="8" y="7" width="6" height="13" rx="1" class="k-logo-b" />
          <rect x="15" y="12" width="6" height="8" rx="1" class="k-logo-b" />
        </svg>
        Kaskade
      </router-link>
      <nav aria-label="Hauptnavigation" class="k-nav">
        <router-link
          v-for="l in links"
          :key="l.to"
          :to="l.to"
          :aria-current="isActive(l.to) ? 'page' : undefined"
        >{{ l.label }}</router-link>
        <div class="k-ref" @keydown.escape="refOpen = false">
          <button
            type="button"
            :aria-expanded="refOpen"
            :aria-current="refActive() ? 'page' : undefined"
            @click="refOpen = !refOpen"
          >Nachschlagen ▾</button>
          <div v-if="refOpen" class="k-ref-menu">
            <router-link v-for="r in reference" :key="r.to" :to="r.to">{{ r.label }}</router-link>
          </div>
        </div>
      </nav>
      <div class="k-header-right">
        <slot name="right" />
        <label class="k-stil">
          <span>Stil</span>
          <select
            :value="status.theme"
            data-testid="theme-select"
            @change="status.setTheme($event.target.value)"
          >
            <option v-for="t in THEMES" :key="t.id" :value="t.id">{{ t.label }}</option>
          </select>
        </label>
        <span v-if="status.phase" class="k-chip k-chip-accent" data-testid="phase">Phase {{ status.phase }}</span>
      </div>
    </div>
    <!-- A running block timer gets its own slim row, so the nav never wraps because of it. -->
    <div v-if="status.running" class="k-runbar">
      <button
        type="button"
        class="k-timer"
        data-testid="header-timer"
        :aria-label="`Zeit läuft: ${BLOCK_LABELS[status.running.block]} — stoppen`"
        @click="status.stopTimer()"
      ><span class="k-runbar-dot" aria-hidden="true"></span>Läuft: {{ BLOCK_LABELS[status.running.block] }} · {{ elapsed }} <span class="k-runbar-stop">■ Stopp</span></button>
    </div>
  </header>
</template>

<style scoped>
.k-header { background: var(--nav-bg); color: var(--nav-text); border-bottom: var(--nav-border); }
.k-stil { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--nav-muted); }
.k-stil select {
  min-height: 36px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--nav-muted);
  background: var(--nav-bg);
  color: var(--nav-text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.k-header-in {
  max-width: 1200px;
  margin: 0 auto;
  padding: 6px 24px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 16px;
}
.k-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--nav-text) !important;
  text-decoration: none;
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 19px;
  min-height: 44px;
}
.k-logo-a { fill: var(--accent); }
.k-logo-b { fill: var(--nav-text); }
.k-nav { display: flex; flex-wrap: wrap; gap: 2px; align-items: center; }
.k-nav a,
.k-ref > button {
  color: var(--nav-muted) !important;
  background: transparent;
  border: 0;
  font: inherit;
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  padding: 12px 10px;
  border-radius: 8px;
  line-height: 20px;
  cursor: pointer;
}
.k-nav a:hover,
.k-ref > button:hover { background: var(--nav-hover); color: var(--nav-text) !important; }
.k-nav a[aria-current='page'],
.k-ref > button[aria-current='page'] {
  background: var(--nav-text);
  color: var(--nav-bg) !important;
  font-weight: 700;
}
.k-ref { position: relative; }
.k-ref-menu {
  position: absolute;
  z-index: 40;
  top: 100%;
  left: 0;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  padding: 6px;
  background: var(--surface);
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow);
}
.k-ref-menu a { color: var(--text) !important; padding: 10px 12px; }
.k-ref-menu a:hover { background: var(--surface-2); color: var(--text) !important; }
.k-header-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.k-timer {
  min-height: 36px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--nav-muted);
  background: transparent;
  color: var(--nav-text);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}
.k-timer:hover { background: var(--nav-hover); }
.k-runbar { max-width: 1200px; margin: 0 auto; padding: 0 24px 8px; display: flex; justify-content: flex-end; }
.k-runbar .k-timer { display: inline-flex; align-items: center; gap: 8px; font-variant-numeric: tabular-nums; }
.k-runbar-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.k-runbar-stop { font-weight: 700; padding-left: 8px; border-left: 1px solid var(--nav-muted); }
@media (max-width: 640px) {
  .k-header-in { padding: 6px 12px; gap: 4px 12px; }
  .k-runbar { padding: 0 12px 8px; justify-content: flex-start; }
  .k-nav a, .k-ref > button { padding: 10px 8px; }
}
</style>
