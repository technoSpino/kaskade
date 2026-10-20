<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../lib/api'
import { formatClock } from '../../lib/format'
import { isComplete, KIND_LABEL, timeLeft } from '../../lib/practice'
import { paragraphs } from '../../lib/reader'
import { useNow } from '../../lib/useNow'
import { TTS_NOTE } from '../../lib/origin'
import OriginBadge from '../../components/kaskade/OriginBadge.vue'

const route = useRoute()
const module = route.params.module
const item = ref(null)
const error = ref(null)
const answers = ref({})
const result = ref(null)
const timed = ref(false)
const startedAt = ref(null)
const now = useNow(1000)
const playsUsed = ref(0)
const playing = ref(false)
const audioFailed = ref(false)
const player = ref(null)
// Schreiben
const text = ref('')
const checks = ref({})
const selfChecks = ref({})

onMounted(async () => {
  try {
    if (module === 'schreiben') {
      const [p, o] = await Promise.all([api.get(`/plan/prompt/${route.params.id}`), api.get('/practice')])
      item.value = p
      selfChecks.value = o.selfChecks
    } else {
      item.value = await api.get(`/practice/${module}/${route.params.id}`)
    }
  } catch (e) {
    error.value = e.message
  }
})
onBeforeUnmount(() => player.value?.pause())

const left = computed(() => (timed.value && startedAt.value ? timeLeft(item.value.minutes, startedAt.value, now.value) : null))
const words = computed(() => (text.value.trim() ? text.value.trim().split(/\s+/).length : 0))
const complete = computed(() => item.value && module !== 'schreiben' && isComplete(item.value, answers.value))
const review = computed(() => Object.fromEntries((result.value?.review ?? []).map((r) => [r.id, r])))
const plays = computed(() => item.value?.plays ?? 1)

watch(left, (s) => { if (s === 0 && !result.value) submit() })

function start(withTimer) {
  timed.value = withTimer
  startedAt.value = Date.now()
}

function play() {
  if (playsUsed.value >= plays.value || playing.value) return
  if (!player.value) {
    player.value = new Audio(`/api/practice/hoeren/${item.value.id}/audio`)
    player.value.addEventListener('ended', () => { playing.value = false })
    player.value.addEventListener('error', () => { audioFailed.value = true; playing.value = false })
  }
  player.value.currentTime = 0
  player.value.play().then(() => {
    playing.value = true
    playsUsed.value++
  }).catch(() => { audioFailed.value = true })
}

async function submit() {
  const seconds = startedAt.value ? Math.round((Date.now() - startedAt.value) / 1000) : null
  try {
    if (module === 'schreiben') {
      result.value = await api.post(`/practice/schreiben/${item.value.id}/selfcheck`, { checks: checks.value, text: text.value, seconds, timed: timed.value })
    } else {
      result.value = await api.post(`/practice/${module}/${item.value.id}/submit`, { answers: answers.value, seconds, timed: timed.value })
    }
    player.value?.pause()
  } catch (e) {
    error.value = e.message
  }
}

function mark(id, value) {
  if (result.value) return
  answers.value = { ...answers.value, [id]: value }
}
const optClass = (id, value) => {
  const r = review.value[id]
  return {
    'pi-opt': true,
    'pi-on': answers.value[id] === value,
    'pi-right': r && r.correct === value,
    'pi-wrong': r && r.given === value && !r.ok
  }
}
</script>

<template>
  <main class="k-main" data-testid="pruefung-item">
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
    <template v-if="item">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div class="min-w-0">
          <p class="k-eyebrow mb-1.5"><router-link to="/pruefung">Prüfungstraining</router-link> · {{ module === 'schreiben' ? item.type : KIND_LABEL[item.kind] }} · {{ item.minutes }} min</p>
          <h1 class="k-h1">{{ item.title }}</h1>
          <OriginBadge class="mt-2" :origin="item.origin" :source="item.source" fallback="ai" />
        </div>
        <p v-if="left != null && !result" class="k-chip k-chip-accent m-0" style="font-size: 18px" data-testid="countdown" aria-live="off">⏱ {{ formatClock(left) }}</p>
      </div>

      <section v-if="!startedAt" class="k-card flex flex-col gap-3">
        <p class="m-0">{{ module === 'schreiben' ? item.situation : item.instructions }}</p>
        <div class="flex flex-wrap gap-3">
          <button class="k-btn" data-testid="start-timed" @click="start(true)">Auf Zeit starten ({{ item.minutes }} min)</button>
          <button class="k-btn k-btn-ghost" data-testid="start-free" @click="start(false)">Ohne Zeit üben</button>
        </div>
      </section>

      <template v-else>
        <!-- Hören: audio with play limit -->
        <section v-if="module === 'hoeren'" class="k-card flex flex-wrap items-center gap-4">
          <button class="k-btn" :disabled="playsUsed >= plays || playing || audioFailed" data-testid="play" @click="play">
            ▶ {{ playing ? 'Läuft …' : playsUsed ? 'Noch einmal hören' : 'Abspielen' }}
          </button>
          <span class="k-small">{{ playsUsed }} von {{ plays }}× gehört · {{ TTS_NOTE }}</span>
          <span v-if="audioFailed" class="k-error">Audio nicht verfügbar (Piper fehlt auf dem Server).</span>
        </section>

        <!-- Lesen: text or ads -->
        <article v-if="item.text" class="k-card">
          <div class="k-read" style="font-size: 19px; line-height: 1.7; max-width: 68ch">
            <p v-for="(p, i) in paragraphs(item.text)" :key="i" class="m-0 mb-3">{{ p }}</p>
          </div>
        </article>
        <section v-if="item.ads" class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(240px, 1fr))">
          <article v-for="ad in item.ads" :key="ad.id" class="k-card" style="padding: 16px">
            <p class="m-0" style="font-weight: 800">{{ ad.id }}) {{ ad.title }}</p>
            <p class="m-0 mt-1 k-read" style="font-size: 16px">{{ ad.text }}</p>
          </article>
        </section>

        <!-- Schreiben -->
        <template v-if="module === 'schreiben'">
          <section class="k-card flex flex-col gap-2">
            <p class="k-read m-0" style="font-size: 18px">{{ item.situation }}</p>
            <ul class="m-0 list-disc pl-5"><li v-for="p in item.points" :key="p">{{ p }}</li></ul>
          </section>
          <section class="k-card flex flex-col gap-3">
            <textarea v-model="text" class="k-input" aria-label="Dein Text" :readonly="!!result" data-testid="practice-text"></textarea>
            <p class="k-small m-0"><strong>{{ words }}</strong> Wörter · Ziel etwa {{ item.words }}</p>
            <fieldset class="border-0 p-0 m-0 flex flex-col gap-2">
              <legend class="k-h2 mb-2" style="font-size: 17px">Selbstcheck</legend>
              <label v-for="(label, key) in selfChecks" :key="key" class="flex items-center gap-2.5" style="min-height: 36px">
                <input v-model="checks[key]" type="checkbox" :disabled="!!result" :data-testid="`check-${key}`" /> {{ label }}
              </label>
            </fieldset>
          </section>
        </template>

        <!-- Questions -->
        <section v-if="item.questions || item.situations" class="k-card flex flex-col gap-4">
          <div v-for="(q, n) in item.questions" :key="q.id" class="flex flex-col gap-2">
            <p class="m-0" style="font-weight: 700">{{ n + 1 }}. {{ q.statement || q.question }}</p>
            <div v-if="q.statement" class="flex gap-2">
              <button :class="optClass(q.id, true)" :data-testid="`${q.id}-r`" @click="mark(q.id, true)">richtig</button>
              <button :class="optClass(q.id, false)" :data-testid="`${q.id}-f`" @click="mark(q.id, false)">falsch</button>
            </div>
            <div v-else class="flex flex-col gap-1.5">
              <button v-for="(o, k) in q.options" :key="k" :class="optClass(q.id, k)" style="text-align: left" :data-testid="`${q.id}-${k}`" @click="mark(q.id, k)">{{ 'abc'[k] }}) {{ o }}</button>
            </div>
          </div>
          <div v-for="(s, n) in item.situations" :key="s.id" class="flex flex-wrap items-center gap-2">
            <p class="m-0 flex-1" style="min-width: 220px"><strong>{{ n + 1 }}.</strong> {{ s.text }}</p>
            <div class="flex flex-wrap gap-1">
              <button v-for="a in [...item.ads.map((x) => x.id), '0']" :key="a" :class="optClass(s.id, a)" style="min-width: 40px" :data-testid="`${s.id}-${a}`" @click="mark(s.id, a)">{{ a }}</button>
            </div>
          </div>
        </section>

        <div v-if="!result" class="flex flex-wrap gap-3 items-center">
          <button class="k-btn" :disabled="module !== 'schreiben' && !complete" data-testid="practice-submit" @click="submit">Abgeben</button>
          <span v-if="module !== 'schreiben' && !complete" class="k-hint">Erst alle Aufgaben beantworten.</span>
        </div>
        <section v-else class="k-card k-card-strong flex flex-col gap-2" data-testid="practice-result">
          <p class="m-0" style="font-size: 32px; font-weight: 800">{{ result.points }} / {{ result.total }} · {{ Math.round(result.pct * 100) }} %</p>
          <p class="m-0">{{ result.passed ? '✓ Bestanden (ab 60 %)' : 'Noch nicht bestanden (60 % nötig) — weiter üben.' }}</p>
          <details v-if="result.script" class="mt-2">
            <summary style="cursor: pointer; font-weight: 700">Transkript anzeigen</summary>
            <p v-for="(s, i) in result.script" :key="i" class="m-0 mt-2 k-read"><strong>{{ s.name }}:</strong> {{ s.text }}</p>
          </details>
          <router-link to="/pruefung" class="k-btn k-btn-ghost mt-2" style="width: fit-content">Zur Übersicht</router-link>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.pi-opt {
  min-height: 44px; padding: 8px 12px; border-radius: var(--radius-sm); font: inherit;
  background: var(--surface); color: var(--text); border: var(--border-width) solid var(--border-strong); cursor: pointer;
}
.pi-opt:hover { border-color: var(--text); }
.pi-on { background: var(--callout); border-color: var(--text); font-weight: 700; }
.pi-right { background: var(--success-bg); color: var(--success); border-color: var(--success); font-weight: 700; }
.pi-wrong { text-decoration: line-through; color: var(--danger); }
</style>
