<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { formatDate, formatNumber } from '../../lib/format'
import { AI_GRADE } from '../../lib/origin'
import { useStatusStore } from '../../stores/statusStore'
import VocabTest from '../../components/kaskade/VocabTest.vue'
import ReadingTest from '../../components/kaskade/ReadingTest.vue'
import SatzCheckSource from '../../components/kaskade/SatzCheckSource.vue'
import SatzCheckRun from '../../components/kaskade/SatzCheckRun.vue'
import WritingTask from '../../components/kaskade/WritingTask.vue'
import SpeakingTask from '../../components/kaskade/SpeakingTask.vue'
import PlacementResult from '../../components/kaskade/PlacementResult.vue'

const STEPS = [
  { id: 'wortschatz', label: 'Wortschatz', minutes: 5 },
  { id: 'lesen', label: 'Lesen', minutes: 15 },
  { id: 'satzcheck', label: 'Satz-Check', minutes: 10 },
  { id: 'schreiben', label: 'Schreiben', minutes: 20 },
  { id: 'sprechen', label: 'Sprechen', minutes: 5 }
]

const status = useStatusStore()
const placement = ref(null)
const content = ref(null)
const error = ref(null)
const loading = ref(true)
const finishing = ref(false)
let saveTimer = 0

const state = computed(() => placement.value?.state ?? {})
const step = computed(() => state.value.step)
const stepIndex = computed(() => STEPS.findIndex((s) => s.id === step.value))
const done = computed(() => placement.value?.status === 'done')

onMounted(async () => {
  try {
    const [cur, c] = await Promise.all([api.get('/placement/current'), api.get('/placement/content')])
    placement.value = cur
    content.value = c
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
onBeforeUnmount(() => flush())

async function startNew() {
  try {
    placement.value = await api.post('/placement')
  } catch (e) {
    error.value = e.message
  }
}

function save(delay = 500) {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flush, delay)
}

async function flush() {
  clearTimeout(saveTimer)
  if (!placement.value || placement.value.status !== 'in_progress') return
  try {
    await api.put(`/placement/${placement.value.id}`, { state: placement.value.state })
  } catch (e) {
    error.value = `Speichern fehlgeschlagen: ${e.message}`
  }
}

function patch(key, value, nextStep) {
  const s = { ...placement.value.state, [key]: { ...(placement.value.state[key] || {}), ...value } }
  if (nextStep) s.step = nextStep
  placement.value = { ...placement.value, state: s }
  save(nextStep ? 0 : 500)
}

function nextOf(id) {
  const i = STEPS.findIndex((s) => s.id === id)
  return i < STEPS.length - 1 ? STEPS[i + 1].id : 'ergebnis'
}

function goto(id) {
  placement.value = { ...placement.value, state: { ...placement.value.state, step: id } }
  save(0)
}

async function finish() {
  finishing.value = true
  await flush()
  try {
    placement.value = await api.post(`/placement/${placement.value.id}/finish`)
    status.load()
  } catch (e) {
    error.value = e.message
  } finally {
    finishing.value = false
  }
}

function summary(id) {
  const s = state.value
  switch (id) {
    case 'wortschatz':
      return s.vocab?.result ? { big: '≈ ' + formatNumber(s.vocab.result.estimate), small: `Wörter · ${Math.round(s.vocab.result.coreShare * 100)} % der Kern-2.000` } : null
    case 'lesen':
      return s.reading?.result ? { big: s.reading.result.level, small: `B1-Text ${s.reading.result.b1}/5 · B2-Text ${s.reading.result.b2}/5` } : null
    case 'satzcheck':
      if (s.satzcheck?.skipped) return { big: '—', small: 'übersprungen' }
      return s.satzcheck?.result ? { big: s.satzcheck.result.coverage + ' %', small: s.satzcheck.result.verdict.title } : null
    case 'schreiben':
      if (s.writing?.skipped) return { big: '—', small: 'übersprungen' }
      return s.writing?.writingId ? { big: s.writing.grade?.level || '✓', small: s.writing.grade ? AI_GRADE : 'gespeichert' } : null
    case 'sprechen':
      if (s.speaking?.skipped) return { big: '—', small: 'übersprungen' }
      return s.speaking?.done ? { big: '✓', small: 'aufgenommen' } : null
  }
  return null
}

const words = computed(() => state.value.vocab?.result?.estimate ?? null)
</script>

<template>
  <div>
    <div class="k-subbar">
      <div class="k-subbar-in">
        <span v-if="placement && !done">Einstufung · {{ step === 'ergebnis' ? 'Abschluss' : `Schritt ${stepIndex + 1} von ${STEPS.length}` }}</span>
        <span v-else>Einstufung</span>
        <router-link v-if="placement && !done" to="/" class="ml-auto" @click="flush">Pause — später weitermachen</router-link>
      </div>
    </div>

    <main class="k-main" data-testid="einstufung">
      <div class="min-w-0">
        <p class="k-eyebrow mb-1.5">{{ done ? 'Ergebnis vom ' + formatDate(placement.updatedAt) : 'Erster Start' }}</p>
        <h1 class="k-h1">Wo stehst du wirklich?</h1>
        <p class="k-lead">Kurs B1.2 abgeschlossen, aber nicht getestet. Ein Kurs zeigt, was du <em>gelernt</em> hast — die Kaskade braucht, was du <em>verstehst</em>. Jede Fähigkeit wird einzeln gemessen. Etwa 55 Minuten, jederzeit pausierbar: der Stand wird automatisch gespeichert.</p>
      </div>

      <p v-if="error" class="k-error" role="alert">{{ error }}</p>
      <p v-if="loading" class="k-small">Lädt …</p>

      <template v-else-if="!placement">
        <div><button class="k-btn" data-testid="pl-start" @click="startNew">Einstufung starten</button></div>
      </template>

      <template v-else>
        <ol class="k-steps">
          <li v-for="(s, i) in STEPS" :key="s.id" :class="{ 'k-step-now': s.id === step && !done }">
            <button type="button" class="k-step-btn" :disabled="done || !summary(s.id)" @click="goto(s.id)">
              <span class="k-step-label">{{ i + 1 }} · {{ s.label.toUpperCase() }} · {{ s.minutes }} MIN</span>
              <span class="k-step-big">{{ summary(s.id)?.big ?? (s.id === step && !done ? 'jetzt' : 'offen') }}</span>
              <span class="k-step-small">{{ summary(s.id)?.small ?? '' }}</span>
            </button>
          </li>
        </ol>

        <template v-if="done">
          <PlacementResult :result="placement.result" />
          <div class="flex flex-wrap gap-3">
            <router-link to="/" class="k-btn">Zu Heute</router-link>
            <router-link to="/karten" class="k-btn k-btn-ghost">Erste Karten-Sitzung</router-link>
            <button class="k-btn k-btn-ghost" @click="startNew">Neue Einstufung</button>
          </div>
        </template>

        <VocabTest
          v-else-if="step === 'wortschatz'"
          :state="state.vocab?.progress"
          @progress="patch('vocab', { progress: $event })"
          @done="patch('vocab', { result: $event }, nextOf('wortschatz'))"
        />

        <ReadingTest
          v-else-if="step === 'lesen' && content"
          :texts="content.reading"
          :state="state.reading?.progress"
          @progress="patch('reading', { progress: $event })"
          @done="patch('reading', { progress: { answers: $event.answers }, result: $event.result }, nextOf('lesen'))"
        />

        <template v-else-if="step === 'satzcheck'">
          <SatzCheckRun
            v-if="state.satzcheck?.setup && !state.satzcheck?.result"
            :media="state.satzcheck.setup.media"
            :content-type="state.satzcheck.setup.contentType"
            :window-start="state.satzcheck.setup.windowStart"
            :initial-ratings="state.satzcheck.ratings"
            :words="words"
            @progress="patch('satzcheck', { ratings: $event.ratings })"
            @done="patch('satzcheck', { result: $event })"
          />
          <template v-else-if="state.satzcheck?.result">
            <section class="k-card flex flex-wrap items-center justify-between gap-4">
              <p class="m-0"><strong>{{ state.satzcheck.result.coverage }} %</strong> · {{ state.satzcheck.result.verdict.title }}</p>
              <button class="k-btn" data-testid="pl-next" @click="goto(nextOf('satzcheck'))">Weiter zu Schreiben</button>
            </section>
          </template>
          <template v-else>
            <SatzCheckSource @start="patch('satzcheck', { setup: $event, ratings: null })" />
            <div><button class="k-btn k-btn-ghost k-btn-sm" data-testid="sc-skip" @click="patch('satzcheck', { skipped: true }, nextOf('satzcheck'))">Satz-Check überspringen (später nachholen)</button></div>
          </template>
        </template>

        <template v-else-if="step === 'schreiben' && content">
          <WritingTask
            :task="content.writing"
            :context="`placement:${placement.id}`"
            :ai="content.ai"
            :state="state.writing"
            @progress="patch('writing', $event)"
            @done="patch('writing', $event)"
          />
          <div class="flex flex-wrap gap-3">
            <button v-if="state.writing?.writingId" class="k-btn" data-testid="pl-next" @click="goto(nextOf('schreiben'))">Weiter zu Sprechen</button>
            <button v-else class="k-btn k-btn-ghost k-btn-sm" data-testid="wt-skip" @click="patch('writing', { skipped: true }, nextOf('schreiben'))">Überspringen</button>
          </div>
        </template>

        <SpeakingTask
          v-else-if="step === 'sprechen' && content"
          :questions="content.speaking"
          :context="`placement:${placement.id}`"
          :state="state.speaking"
          @progress="patch('speaking', $event)"
          @done="patch('speaking', { ...$event, done: !$event.skipped }, 'ergebnis')"
        />

        <section v-else-if="step === 'ergebnis'" class="k-card flex flex-col gap-3">
          <h2 class="k-h2">Alles erledigt</h2>
          <p class="k-small m-0">Jetzt das Ergebnis berechnen. Es stellt deine Phase, die bekannten Wörter und den Startpunkt für die B2-Prognose ein.</p>
          <div><button class="k-btn" :disabled="finishing" data-testid="pl-finish" @click="finish">Ergebnis anzeigen</button></div>
        </section>
      </template>

      <aside v-if="!done" class="flex flex-wrap gap-4">
        <section class="k-card" style="flex: 1 1 320px">
          <h2 class="k-h2" style="font-size: 17px">Was das Ergebnis einstellt</h2>
          <ul class="mt-2.5 mb-0 list-disc pl-5 k-small" style="line-height: 1.6">
            <li><strong>Deine Refold-Phase</strong> (aus dem Satz-Check)</li>
            <li><strong>Bekannte Wörter</strong> — und welche Kernwörter du schon kennst</li>
            <li><strong>Startstunden</strong> für die B2-Prognose</li>
            <li><strong>Tagesplan</strong> für den Block 09:00–11:30</li>
          </ul>
        </section>
        <section class="k-callout" style="flex: 1 1 320px">
          <strong>Typisch nach einem Kurs:</strong> Lesen und Grammatik sind weiter als das Hören bei normalem Tempo. Genau das soll der Test zeigen.
        </section>
      </aside>
    </main>
  </div>
</template>

<style scoped>
.k-subbar { background: var(--nav-bg); color: var(--nav-muted); border-top: 1px solid var(--nav-hover); }
.k-subbar-in {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 14px;
  font-weight: 700;
}
.k-subbar a { color: var(--nav-muted) !important; font-weight: 600; }
.k-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}
.k-step-btn {
  width: 100%;
  height: 100%;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--surface);
  border: var(--border-width) solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  font: inherit;
  color: var(--text-2);
  cursor: pointer;
}
.k-step-btn:disabled { cursor: default; }
.k-step-now .k-step-btn { border: calc(var(--border-width) + 1px) solid var(--text); color: var(--text); }
.k-step-label { font-size: 12px; font-weight: 800; color: var(--muted); letter-spacing: 0.06em; }
.k-step-now .k-step-label { color: var(--text); }
.k-step-big { font-size: 22px; font-weight: 800; color: var(--text); }
.k-step-small { font-size: 13px; }
@media (max-width: 480px) { .k-subbar-in { padding: 0 16px; } }
</style>
