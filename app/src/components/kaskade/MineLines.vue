<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import AnalyzedText from './AnalyzedText.vue'
import WordPanel from './WordPanel.vue'

// Lines rated "mit Hilfe" / "zu schwer" in Satz-Checks, offered as sentence cards:
// open a line, tap the word you want to learn, "Satz minen".
const lines = ref(null)
const error = ref(null)
const open = ref(null)
const analysis = ref(null)
const token = ref(null)
const showMined = ref(false)

async function load() {
  try {
    lines.value = await api.get('/satzcheck/lines')
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)

const visible = computed(() => (lines.value ?? []).filter((l) => showMined.value || !l.mined || l.text === open.value))
const openCount = computed(() => (lines.value ?? []).filter((l) => !l.mined).length)

async function toggle(line) {
  token.value = null
  analysis.value = null
  if (open.value === line.text) {
    open.value = null
    return
  }
  open.value = line.text
  try {
    analysis.value = await api.post('/analyze', { text: line.text })
  } catch (e) {
    error.value = e.message
  }
}

function onMined() {
  const line = lines.value.find((l) => l.text === open.value)
  if (line) line.mined = true
}
</script>

<template>
  <section v-if="lines && lines.length" id="minen" class="k-card" aria-labelledby="mine-h" data-testid="mine-lines">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="mine-h" class="k-h2">Sätze zum Minen · {{ openCount }}</h2>
      <label class="k-small inline-flex items-center gap-2"><input v-model="showMined" type="checkbox" /> auch geminte zeigen</label>
    </div>
    <p class="k-small m-0 mt-1.5">Diese Zeilen hast du im Satz-Check mit Hilfe oder gar nicht verstanden. Zeile öffnen, das Wort antippen, das du lernen willst, dann „Satz minen“ — die ganze Zeile wird zur Karte.</p>
    <p v-if="error" class="k-error m-0 mt-2">{{ error }}</p>
    <ul class="list-none m-0 mt-3 p-0">
      <li v-for="l in visible" :key="l.text" class="ml-row">
        <button type="button" class="ml-line" :aria-expanded="open === l.text" :data-testid="`mine-line-${l.cue}`" @click="toggle(l)">
          <span :class="['k-chip', l.rating === 's' ? 'ml-hard' : 'ml-help']">{{ l.rating === 's' ? 'zu schwer' : 'mit Hilfe' }}</span>
          <span class="k-read ml-text">{{ l.text }}</span>
          <span v-if="l.mined" class="k-chip k-chip-success">✓ gemined</span>
        </button>
        <div v-if="open === l.text" class="ml-open">
          <p v-if="!analysis" class="k-hint m-0">Wird analysiert …</p>
          <template v-else>
            <AnalyzedText :analysis="analysis" :lens="true" :selected="token?.i ?? null" @select="token = $event" />
            <WordPanel
              :analysis="analysis"
              :token="token"
              :sentence="l.text"
              :source="`Satz-Check${l.title ? ' · ' + l.title : ''}`"
              @mined="onMined"
            />
          </template>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.ml-row { border-top: 1px solid var(--surface-2); }
.ml-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 12px 0;
  border: 0;
  background: none;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.ml-line:hover .ml-text { text-decoration: underline; }
.ml-text { font-size: 18px; min-width: 0; flex: 1 1 200px; }
.ml-help { background: var(--surface-2); color: var(--text); }
.ml-hard { background: var(--callout); color: var(--text); }
.ml-open { display: grid; gap: 16px; padding: 4px 0 16px; }
@media (min-width: 820px) { .ml-open { grid-template-columns: minmax(0, 1fr) 320px; align-items: start; } }
</style>
