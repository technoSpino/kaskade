<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { cuesInWindow, summarize, verdict } from '../../lib/satzcheck'
import { formatClock } from '../../lib/format'
import TempoLines from './TempoLines.vue'

// Step 3: the clip pauses after every sentence; rate 1/2/3, R replays.
const props = defineProps({
  media: { type: Object, required: true },
  contentType: { type: String, required: true },
  windowStart: { type: Number, required: true },
  initialRatings: { type: Array, default: null },
  words: { type: Number, default: null }
})
const emit = defineEmits(['progress', 'done'])

const cues = computed(() => cuesInWindow(props.media.cues, props.windowStart))
const ratings = ref(props.initialRatings ?? cues.value.map(() => null))
const current = ref(Math.max(0, ratings.value.indexOf(null)))
const started = ref(ratings.value.some((r) => r))
const playing = ref(false)
const saving = ref(false)
const saved = ref(null)
const error = ref(null)
const player = ref(null)
const rows = ref([])
let raf = 0

const summary = computed(() => summarize(ratings.value))
const live = computed(() => verdict(summary.value.coverage, props.contentType, props.words))
const allRated = computed(() => ratings.value.every((r) => r))
const gate = computed(() => (props.contentType === 'simple' ? 75 : 80))
const cueText = computed(() => cues.value[current.value]?.text ?? '')
const clock = computed(() => {
  const c = cues.value[current.value]
  return c ? `${formatClock(c.start)} · Satz ${current.value + 1} von ${cues.value.length}` : ''
})

function stopLoop() {
  cancelAnimationFrame(raf)
  raf = 0
}

function playCue(i) {
  current.value = i
  started.value = true
  const v = player.value
  const cue = cues.value[i]
  if (!v || !cue) return
  stopLoop()
  v.currentTime = Math.max(0, cue.start - 0.15)
  v.play().then(() => {
    playing.value = true
    const tick = () => {
      if (v.currentTime >= cue.end + 0.1 || v.ended) {
        v.pause()
        playing.value = false
        raf = 0
        return
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
  }).catch(() => {
    playing.value = false
    error.value = 'Abspielen nicht möglich. Datei-Format prüfen — du kannst trotzdem nach Text bewerten.'
  })
}

function scrollToCurrent() {
  nextTick(() => rows.value[current.value]?.scrollIntoView?.({ block: 'nearest' }))
}

function rate(i, value) {
  if (saved.value) return
  const next = ratings.value.slice()
  next[i] = value
  ratings.value = next
  emit('progress', { ratings: next })
  if (i === current.value) {
    const open = next.indexOf(null, i + 1)
    const target = open === -1 ? next.indexOf(null) : open
    if (target !== -1) {
      if (props.media.hasMedia) playCue(target)
      else current.value = target
      scrollToCurrent()
    }
  }
}

async function save() {
  saving.value = true
  error.value = null
  try {
    saved.value = await api.post('/satzcheck', {
      mediaId: props.media.id,
      contentType: props.contentType,
      windowStart: props.windowStart,
      windowEnd: props.windowStart + 180,
      ratings: cues.value.map((c, i) => ({ cue: c.index, text: c.text, rating: ratings.value[i] }))
    })
    emit('done', saved.value)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target?.tagName)) return
  const k = e.key.toLowerCase()
  if (k === '1' || k === '2' || k === '3') {
    e.preventDefault()
    rate(current.value, { 1: 'v', 2: 'h', 3: 's' }[k])
  } else if (k === 'r' && props.media.hasMedia) {
    playCue(current.value)
  } else if (k === ' ' && props.media.hasMedia) {
    e.preventDefault()
    if (playing.value) {
      player.value?.pause()
      playing.value = false
      stopLoop()
    } else {
      playCue(current.value)
    }
  } else if (k === 'arrowdown' || k === 'j') {
    current.value = Math.min(cues.value.length - 1, current.value + 1)
    scrollToCurrent()
  } else if (k === 'arrowup' || k === 'k') {
    current.value = Math.max(0, current.value - 1)
    scrollToCurrent()
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  stopLoop()
})

const labels = { v: 'verstanden', h: 'mit Hilfe', s: 'zu schwer' }
const pct = (n) => (summary.value.rated ? Math.round((n / summary.value.rated) * 100) : 0)
</script>

<template>
  <div class="flex flex-wrap gap-6 items-start">
    <div class="flex flex-col gap-4 min-w-0" style="flex: 999 1 560px">
      <div class="sc-stage" :class="{ 'sc-stage-text': !media.hasMedia || media.isAudio }">
        <div class="sc-stage-top">
          <span>{{ media.title }}</span><span>{{ clock }}</span>
        </div>
        <video
          v-if="media.hasMedia"
          ref="player"
          class="sc-video"
          :src="`/api/media/${media.id}/file`"
          preload="auto"
          playsinline
        ></video>
        <div v-if="!started && media.hasMedia" class="sc-overlay">
          <button class="k-btn" data-testid="sc-play" @click="playCue(current)">▶ Ersten Satz abspielen</button>
        </div>
        <p class="sc-caption k-read" aria-live="polite" data-testid="sc-caption">{{ cueText }}</p>
      </div>
      <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>

      <section class="k-card" style="padding: 8px 20px 12px" aria-labelledby="list-h">
        <div class="flex flex-wrap items-baseline justify-between gap-2 py-3">
          <h2 id="list-h" class="k-h2" style="font-size: 17px">Sätze im Clip</h2>
          <p class="k-hint m-0">Tasten: 1 verstanden · 2 mit Hilfe · 3 zu schwer<template v-if="media.hasMedia"> · R nochmal hören · Leertaste Pause</template></p>
        </div>
        <ol class="list-none m-0 p-0">
          <li
            v-for="(c, i) in cues"
            :key="c.index"
            :ref="(el) => (rows[i] = el)"
            class="sc-row"
            :class="{ 'sc-row-current': i === current }"
            :data-testid="`sc-row-${i}`"
          >
            <button type="button" class="sc-n" :aria-label="`Satz ${i + 1} abspielen`" @click="media.hasMedia ? playCue(i) : (current = i)">{{ i + 1 }}</button>
            <span class="k-read sc-text">{{ c.text }}</span>
            <span role="radiogroup" :aria-label="`Satz ${i + 1} bewerten`" class="sc-rates">
              <button
                v-for="val in ['v', 'h', 's']"
                :key="val"
                type="button"
                role="radio"
                class="sc-rate"
                :aria-checked="ratings[i] === val ? 'true' : 'false'"
                :disabled="!!saved"
                @click="rate(i, val)"
              >{{ labels[val] }}</button>
            </span>
          </li>
        </ol>
      </section>
    </div>

    <aside aria-label="Ergebnis" class="flex flex-col gap-4 min-w-0" style="flex: 1 1 340px">
      <section class="k-card k-card-strong" aria-labelledby="res-h" data-testid="sc-result">
        <h2 id="res-h" class="k-eyebrow">Satz-Abdeckung · {{ summary.rated }} von {{ cues.length }} bewertet</h2>
        <p class="m-0 mt-1.5" style="font-size: 48px; font-weight: 800; letter-spacing: -0.02em" data-testid="sc-coverage">{{ summary.coverage }} %</p>
        <p class="k-small m-0">verstanden + mit Hilfe</p>
        <div class="relative mt-7">
          <div class="sc-gate-label" :style="{ left: gate + '%' }">{{ gate }} %</div>
          <div class="flex gap-0.5 overflow-hidden" style="height: 22px; border-radius: 6px; background: var(--surface-2)">
            <div v-if="summary.v" :title="`verstanden: ${summary.v} (${pct(summary.v)} %)`" :style="{ flex: `${summary.v} 1 0`, background: 'var(--primary)' }"></div>
            <div v-if="summary.h" :title="`mit Hilfe: ${summary.h} (${pct(summary.h)} %)`" :style="{ flex: `${summary.h} 1 0`, background: 'var(--rate-help)' }"></div>
            <div v-if="summary.s" :title="`zu schwer: ${summary.s} (${pct(summary.s)} %)`" :style="{ flex: `${summary.s} 1 0`, background: 'var(--rate-hard)' }"></div>
          </div>
          <div class="sc-gate-line" :style="{ left: gate + '%' }"></div>
        </div>
        <ul class="list-none m-0 mt-3 p-0 flex flex-col gap-1.5 text-sm">
          <li class="flex items-center gap-2"><span class="sc-sw" style="background: var(--primary)"></span>verstanden <strong class="ml-auto">{{ summary.v }}</strong></li>
          <li class="flex items-center gap-2"><span class="sc-sw" style="background: var(--rate-help)"></span>mit Hilfe <strong class="ml-auto">{{ summary.h }}</strong></li>
          <li class="flex items-center gap-2"><span class="sc-sw" style="background: var(--rate-hard)"></span>zu schwer <strong class="ml-auto">{{ summary.s }}</strong></li>
        </ul>
        <div class="k-callout mt-4" data-testid="sc-verdict">
          <p class="m-0" style="font-size: 16px; font-weight: 800; color: var(--text)">{{ saved ? saved.verdict.title : live.title }}</p>
          <p v-if="saved" class="m-0 mt-1">{{ saved.verdict.advice }}</p>
          <p v-else class="m-0 mt-1">Vorläufig — gespeichert wird, wenn alle Sätze bewertet sind.</p>
        </div>
        <button v-if="!saved" class="k-btn mt-4 w-full" :disabled="!allRated || saving" data-testid="sc-save" @click="save">
          {{ saving ? 'Speichert …' : allRated ? 'Ergebnis speichern' : `Noch ${cues.length - summary.rated} Sätze` }}
        </button>
        <p v-else class="k-chip k-chip-success mt-4">✓ Gespeichert</p>
        <TempoLines v-if="saved?.tempo?.length" class="mt-4" :lines="saved.tempo" :media-id="saved.mediaId" />
      </section>
      <section class="k-card" aria-labelledby="gate-h">
        <h2 id="gate-h" class="k-h2" style="font-size: 17px">Refolds Tore</h2>
        <ol class="list-none m-0 mt-2.5 p-0 flex flex-col gap-3 text-sm" style="line-height: 1.45">
          <li><strong>Phase 1 → 2</strong> · einfache Sendung mit Untertiteln, ≈ 75 % · ≈ 1.000 Wörter</li>
          <li><strong>2A → 2B</strong> · Inhalt für Erwachsene mit Untertiteln, ≈ 80 % · ≈ 2.000 Wörter</li>
          <li class="k-small"><strong>2B → 2C</strong> · Serien für Erwachsene folgen, Hilfe nur noch selten</li>
        </ol>
      </section>
    </aside>
  </div>
</template>

<style scoped>
.sc-stage {
  position: relative;
  aspect-ratio: 16 / 9;
  background: var(--stage-bg);
  color: var(--stage-text);
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.sc-stage-text { aspect-ratio: auto; min-height: 200px; }
.sc-stage-top {
  position: relative;
  z-index: 2;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  font-size: 13px;
  color: var(--stage-muted);
}
.sc-video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }
.sc-overlay { position: absolute; inset: 0; z-index: 3; display: flex; align-items: center; justify-content: center; }
.sc-caption {
  position: relative;
  z-index: 2;
  margin: 0 auto 16px;
  max-width: 90%;
  text-align: center;
  font-size: clamp(17px, 2.6vw, 22px);
  line-height: 1.4;
  color: var(--stage-text);
  background: var(--stage-caption-bg);
  padding: 6px 12px;
  border-radius: 6px;
}
.sc-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  padding: 10px 0;
  border-top: 1px solid var(--surface-2);
}
.sc-row-current { background: var(--callout); margin: 0 -10px; padding: 10px; border-radius: 8px; }
.sc-n {
  flex: none;
  width: 28px;
  background: none;
  border: 0;
  padding: 0;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  color: var(--muted);
  cursor: pointer;
}
.sc-text { flex: 999 1 280px; min-width: 0; font-size: 17px; line-height: 1.45; }
.sc-rates { flex: 1 1 auto; display: flex; gap: 6px; justify-content: flex-end; }
.sc-rate {
  min-height: 40px;
  padding: 0 10px;
  border-radius: 8px;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  background: var(--surface);
  border: var(--border-width) solid var(--border-strong);
  cursor: pointer;
}
.sc-rate:hover { border-color: var(--text); }
.sc-rate[aria-checked='true'] { color: var(--primary-text); background: var(--primary); border-color: var(--primary); }
.sc-sw { width: 12px; height: 12px; border-radius: 3px; border: 1px solid var(--border-strong); }
.sc-gate-label {
  position: absolute;
  top: -22px;
  transform: translateX(-50%);
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}
.sc-gate-line { position: absolute; top: -4px; bottom: -4px; border-left: 2px solid var(--text); }
</style>
