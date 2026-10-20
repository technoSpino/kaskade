<script setup>
import { computed } from 'vue'
import { NO_HOURS_YET } from '../../lib/heute'

// Active + passive hours per week (stacked), last weeks oldest → newest.
const props = defineProps({ weeks: { type: Array, required: true } })

const empty = computed(() => props.weeks.every((w) => !w.aktiv && !w.passiv))
const top = computed(() => Math.max(11.7, ...props.weeks.map((w) => w.aktiv + w.passiv)))
const label = (iso) => new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'numeric' }).format(new Date(iso))
const h = (x) => x.toLocaleString('de-DE', { maximumFractionDigits: 1 })
</script>

<template>
  <p v-if="empty" class="k-small m-0" data-testid="chart-empty">{{ NO_HOURS_YET }}</p>
  <div v-else>
    <div class="wc" role="img" :aria-label="`Stunden pro Woche, letzte ${weeks.length} Wochen`">
      <div class="wc-goal" :style="{ bottom: (11.7 / top) * 100 + '%' }"><span>11,7 h</span></div>
      <div v-for="w in weeks" :key="w.week" class="wc-col" :title="`Woche ab ${label(w.week)}: ${w.free ? 'frei · ' : ''}${h(w.aktiv)} h aktiv · ${h(w.passiv)} h passiv`">
        <!-- #36: a week off is "frei", not a missed week -->
        <span v-if="w.free && !w.aktiv && !w.passiv" class="wc-free" :data-testid="`wc-free-${w.week}`">frei</span>
        <div v-if="w.passiv" :style="{ height: (w.passiv / top) * 100 + '%', background: 'var(--chart-passive)' }"></div>
        <div v-if="w.aktiv" :style="{ height: (w.aktiv / top) * 100 + '%', background: 'var(--chart-active)' }"></div>
      </div>
    </div>
    <div class="wc-axis k-hint"><span v-for="w in weeks" :key="w.week">{{ label(w.week) }}</span></div>
  </div>
</template>

<style scoped>
.wc { position: relative; display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 8px; align-items: end; height: 140px; border-bottom: 1px solid var(--border-strong); }
.wc-col { display: flex; flex-direction: column; justify-content: flex-end; height: 100%; gap: 2px; }
.wc-col > div:first-child { border-radius: 4px 4px 0 0; }
.wc-free { padding-bottom: 4px; text-align: center; font-size: 11px; font-weight: 700; color: var(--muted); }
.wc-goal { position: absolute; left: 0; right: 0; border-top: 2px dashed var(--muted); }
.wc-goal span { position: absolute; right: 0; top: -18px; font-size: 11px; font-weight: 700; color: var(--muted); }
.wc-axis { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 8px; margin-top: 6px; text-align: center; font-size: 11px; }
</style>
