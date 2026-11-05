<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { formatDate } from '../../lib/format'
import SatzCheckSource from '../../components/kaskade/SatzCheckSource.vue'
import SatzCheckRun from '../../components/kaskade/SatzCheckRun.vue'
import MineLines from '../../components/kaskade/MineLines.vue'
import TempoLines from '../../components/kaskade/TempoLines.vue'

const setup = ref(null)
const words = ref(null)
const history = ref([])
const run = ref(0)
const linesKey = ref(0)

async function loadHistory() {
  try {
    history.value = await api.get('/satzcheck/history')
  } catch {
    history.value = []
  }
}

onMounted(async () => {
  loadHistory()
  try {
    words.value = (await api.get('/vocab/latest'))?.estimate ?? null
  } catch {
    words.value = null
  }
})

function restart() {
  setup.value = null
  run.value++
}
</script>

<template>
  <main class="k-main">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div class="min-w-0">
        <h1 class="k-h1">Satz-Check</h1>
        <p class="k-lead">Refolds eigener Test: Wie viele Sätze aus echtem Material verstehst du? 3 Minuten mit deutschen Untertiteln. Nach jedem Satz pausiert der Clip — du markierst ehrlich: <strong>verstanden</strong>, <strong>mit Hilfe</strong> (Wörterbuch, Wiederholen) oder <strong>zu schwer</strong>. Einmal im Monat wiederholen, neuer Clip, gleiche Schwierigkeit.</p>
      </div>
      <button v-if="setup" class="k-btn k-btn-ghost" @click="restart">Anderen Clip wählen</button>
    </div>

    <SatzCheckRun
      v-if="setup"
      :key="run"
      :media="setup.media"
      :content-type="setup.contentType"
      :window-start="setup.windowStart"
      :words="words"
      @done="loadHistory(); linesKey++"
    />
    <SatzCheckSource v-else :key="run" @start="setup = $event" />

    <MineLines :key="linesKey" />

    <section v-if="history.length" class="k-card" aria-labelledby="hist-h">
      <h2 id="hist-h" class="k-h2">Bisherige Satz-Checks</h2>
      <ul class="list-none m-0 mt-3 p-0">
        <li v-for="h in history" :key="h.id" class="flex flex-wrap justify-between gap-2 py-3" style="border-top: 1px solid var(--surface-2)">
          <span><strong>{{ h.coverage }} %</strong><template v-if="h.coverageAll != null"> <span class="k-small">(mit Geräusch-Zeilen {{ h.coverageAll }} %)</span></template> · {{ h.verdict.title }}<span class="k-hint block">{{ h.title || 'Clip' }} · {{ h.contentType === 'simple' ? 'einfach' : 'für Erwachsene' }}</span></span>
          <span class="k-small">{{ formatDate(h.createdAt) }}</span>
          <details v-if="h.tempo?.length" class="w-full">
            <summary class="k-small" style="cursor: pointer; font-weight: 700">Hören bei normalem Tempo · {{ h.tempo.length }} {{ h.tempo.length === 1 ? 'Zeile' : 'Zeilen' }}</summary>
            <TempoLines class="mt-2" :lines="h.tempo" :media-id="h.mediaId" />
          </details>
        </li>
      </ul>
    </section>
  </main>
</template>
