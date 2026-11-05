<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../lib/api'
import { defaultView, markGlossary, paragraphs, READER_VIEWS, storedView, storeView, viewFlags } from '../../lib/reader'
import { useStatusStore } from '../../stores/statusStore'
import AnalyzedText from '../../components/kaskade/AnalyzedText.vue'
import WordPanel from '../../components/kaskade/WordPanel.vue'
import CaseLegend from '../../components/kaskade/CaseLegend.vue'
import OriginBadge from '../../components/kaskade/OriginBadge.vue'
import RateAsk from '../../components/kaskade/RateAsk.vue'
import { TTS_NOTE } from '../../lib/origin'
import { ratingLabel } from '../../lib/ratings'

const route = useRoute()
const t = ref(null)
const analysis = ref(null)
const error = ref(null)
const showHelp = ref(true)
const status = useStatusStore()
const view = ref(defaultView(storedView(), status.phase))
const flags = computed(() => viewFlags(view.value))
const lens = computed(() => flags.value.lens)
const token = ref(null)
const active = ref(null)
const answers = ref({})
const checked = ref(false)
const done = ref(false)
const audio = ref(null)
const audioFailed = ref(false)
// ?modus=frei (Heute's "Frei lesen" block, #16): plain text, no highlights, no lookups
const frei = route.query.modus === 'frei'

onMounted(async () => {
  try {
    t.value = await api.get(`/texts/${route.params.id}`)
    showHelp.value = !frei && t.value.slot === 'input'
    done.value = !!t.value.readAt
  } catch (e) {
    error.value = e.message
    return
  }
  try {
    analysis.value = await api.get(`/texts/${route.params.id}/analysis`)
  } catch {
    analysis.value = null // spaCy unavailable: glossary-only mode
  }
})
onBeforeUnmount(() => audio.value?.pause())

// Without a remembered choice, follow the phase once it is known (2B → new words only).
watch(() => status.phase, (p) => { if (!storedView()) view.value = defaultView(null, p) })
function setView(v) {
  view.value = v
  storeView(v)
}

const paras = computed(() => (t.value ? paragraphs(t.value.text).map((p) => markGlossary(p, showHelp.value ? t.value.glossary : [])) : []))
const score = computed(() => (t.value ? t.value.questions.filter((q, i) => answers.value[i] === q.correct).length : 0))

function toggleAudio() {
  if (!audio.value) {
    audio.value = new Audio(`/api/texts/${t.value.id}/audio`)
    audio.value.addEventListener('error', () => { audioFailed.value = true; audio.value = null })
  }
  if (audio.value.paused) audio.value.play().catch(() => { audioFailed.value = true })
  else audio.value.pause()
}

async function finish() {
  try {
    await api.post(`/texts/${t.value.id}/read`)
    done.value = true
  } catch (e) {
    error.value = e.message
    return
  }
  // #23: today's text of a plan block → "Wie viel hast du verstanden?"
  try {
    rateFor.value = (await api.get('/ratings/today')).find((r) => r.textId === t.value.id) ?? null
  } catch {
    rateFor.value = null
  }
}
const rateFor = ref(null)
const rateBusy = ref(false)
async function rate(pct) {
  rateBusy.value = true
  try {
    rateFor.value = { ...rateFor.value, rating: await api.post('/ratings', { block: rateFor.value.block, item: rateFor.value.item, pct }) }
  } catch (e) {
    error.value = e.message
  } finally {
    rateBusy.value = false
  }
}
</script>

<template>
  <main class="k-main" data-testid="reader">
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
    <template v-if="t">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div class="min-w-0">
          <p class="k-eyebrow mb-1.5"><router-link to="/lesen">Lesen</router-link> · {{ t.theme }} · {{ t.level }} · {{ t.words }} Wörter</p>
          <h1 class="k-h1">{{ t.title }}</h1>
          <p class="flex flex-wrap items-center gap-x-3 gap-y-1 m-0 mt-2" data-testid="reader-origin">
            <OriginBadge :origin="t.origin" :source="t.source" fallback="ai" />
            <span class="k-hint">Vorlesen: {{ TTS_NOTE }}</span>
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button class="k-btn k-btn-ghost k-btn-sm" data-testid="reader-audio" :disabled="audioFailed" @click="toggleAudio">
            {{ audioFailed ? 'Kein Audio' : audio && !audio.paused ? '❚❚ Pause' : '▶ Vorlesen' }}
          </button>
          <button v-if="!frei" class="k-btn k-btn-ghost k-btn-sm" :aria-pressed="showHelp" data-testid="reader-help" @click="showHelp = !showHelp; active = null">
            {{ showHelp ? 'Hilfen ausblenden' : 'Neue Wörter zeigen' }}
          </button>
        </div>
      </div>
      <div v-if="analysis && showHelp" class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div class="rd-seg" role="radiogroup" aria-label="Markieren">
          <button
            v-for="v in READER_VIEWS"
            :key="v.id"
            type="button"
            role="radio"
            :aria-checked="view === v.id"
            :class="['rd-seg-btn', { 'rd-seg-on': view === v.id }]"
            :data-testid="`reader-view-${v.id}`"
            @click="setView(v.id)"
          >{{ v.label }}</button>
        </div>
        <CaseLegend v-if="lens" />
      </div>

      <div class="flex flex-wrap gap-6 items-start">
        <article class="k-card min-w-0" style="flex: 999 1 560px">
          <AnalyzedText
            v-if="analysis"
            :analysis="analysis"
            :lens="showHelp && lens"
            :states="showHelp && flags.states"
            :selected="token?.i ?? null"
            @select="token = frei ? null : $event"
          />
          <div v-else class="k-read rd-text">
            <p v-for="(segs, i) in paras" :key="i">
              <template v-for="(s, j) in segs" :key="j">
                <button v-if="s.entry" type="button" class="rd-word" :aria-pressed="active === s.entry" @click="active = active === s.entry ? null : s.entry">{{ s.text }}</button>
                <template v-else>{{ s.text }}</template>
              </template>
            </p>
          </div>
        </article>

        <aside class="flex flex-col gap-4 min-w-0" style="flex: 1 1 300px; position: sticky; top: 12px">
          <WordPanel v-if="analysis && !frei" :analysis="analysis" :token="token" :glossary="t.glossary" :source="`Lesen · ${t.title}`" />
          <section v-else-if="showHelp" class="k-card" aria-live="polite">
            <h2 class="k-h2" style="font-size: 17px">Wort</h2>
            <template v-if="active">
              <p class="m-0 mt-2 k-read" style="font-size: 22px; font-weight: 600">{{ active.term }}</p>
              <p class="m-0 mt-1" style="font-size: 17px">„{{ active.gloss }}“</p>
              <p v-if="active.note" class="k-small m-0 mt-1.5">{{ active.note }}</p>
            </template>
            <p v-else class="k-small m-0 mt-2">Markierte Wörter gehören nicht zu den 2.000 Kernwörtern. Antippen zeigt die Bedeutung.</p>
          </section>
          <section v-if="!showHelp" class="k-callout">
            <strong>Freies Lesen{{ frei ? ' · ohne Hilfen' : '' }}:</strong> nichts nachschlagen, einfach weiterlesen. Wenn du die Geschichte grob verstehst, ist alles gut.
          </section>

          <section class="k-card flex flex-col gap-3">
            <h2 class="k-h2" style="font-size: 17px">Verstanden?</h2>
            <div v-for="(q, i) in t.questions" :key="i" class="flex flex-col gap-1.5">
              <p class="m-0" style="font-weight: 700; font-size: 15px">{{ q.question }}</p>
              <label v-for="(o, k) in q.options" :key="k" class="flex items-start gap-2 k-small" :class="{ 'rd-right': checked && k === q.correct, 'rd-wrong': checked && answers[i] === k && k !== q.correct }">
                <input v-model="answers[i]" type="radio" :name="`q${i}`" :value="k" :disabled="checked" class="mt-1" /> {{ o }}
              </label>
            </div>
            <button v-if="!checked" class="k-btn k-btn-sm" :disabled="Object.keys(answers).length < t.questions.length" @click="checked = true">Prüfen</button>
            <p v-else class="m-0" style="font-weight: 700">{{ score }} von {{ t.questions.length }} richtig</p>
            <button v-if="!done" class="k-btn" data-testid="reader-done" @click="finish">Fertig gelesen</button>
            <p v-else class="k-chip k-chip-success m-0" style="width: fit-content">✓ gelesen</p>
            <RateAsk v-if="rateFor && !rateFor.rating" :label="rateFor.label" :busy="rateBusy" @rate="rate" />
            <p v-else-if="rateFor?.rating" class="k-hint m-0" data-testid="reader-rated">{{ ratingLabel(rateFor.rating) }}</p>
          </section>
        </aside>
      </div>
    </template>
  </main>
</template>

<style scoped>
.rd-seg { display: inline-flex; border: var(--border-width) solid var(--border-strong); border-radius: var(--radius-sm); overflow: hidden; }
.rd-seg-btn { min-height: var(--touch); padding: 0 14px; border: 0; background: var(--surface); color: var(--text); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.rd-seg-btn + .rd-seg-btn { border-left: var(--border-width) solid var(--border-strong); }
.rd-seg-btn:hover { background: var(--surface-2); }
.rd-seg-on, .rd-seg-on:hover { background: var(--primary); color: var(--primary-text); }
.rd-text { font-size: clamp(19px, 2.4vw, 21px); line-height: 1.75; max-width: 66ch; }
.rd-text p { margin: 0 0 1em; }
.rd-word { font: inherit; color: inherit; background: var(--word-new-tint); box-shadow: inset 0 -2px 0 var(--word-new-underline); border: 0; border-radius: 4px; padding: 0 3px; cursor: pointer; }
.rd-word[aria-pressed='true'] { outline: 2px solid var(--focus); }
.rd-right { color: var(--success); font-weight: 700; }
.rd-wrong { color: var(--danger); text-decoration: line-through; }
</style>
