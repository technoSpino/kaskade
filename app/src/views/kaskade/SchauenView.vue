<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../../lib/api'
import { clipStatus, clock, formatTime, inside, jumpedBack, pausedBefore, pickTrack, rangeStart, resumeAt, seekTarget, sentenceAround, shouldPause, shownLine, speechCues, stepLine, storeTrack, storedTrack } from '../../lib/watch'
import { hardShare, ratingLabel, shareLine } from '../../lib/ratings'
import AnalyzedText from '../../components/kaskade/AnalyzedText.vue'
import RateAsk from '../../components/kaskade/RateAsk.vue'
import WordPanel from '../../components/kaskade/WordPanel.vue'

// "Schauen & minen": watch a library clip with the current German subtitle line under
// the video, pause after each line, tap words, mine whole lines (with their audio) as cards.
const route = useRoute()
const router = useRouter()
const clips = ref(null)
const media = ref(null)
const error = ref(null)
const video = ref(null)
const t = ref(0)
const playing = ref(false)
const autoPause = ref(readPref('kaskade-autopause', true))
const loop = ref(false) // repeat the current line (listening practice)
const rate = ref(1)
const analysis = ref(null)
const token = ref(null)
const mined = ref(0)
const range = ref(null) // today's plan range from Heute (?von=…&bis=…, #16)
const rangeNote = ref('')
const goal = ref(false) // "Ziel für heute erreicht" shown
const tags = ref([])
const held = ref(-1) // the line auto-pause stopped after: shown (and mined) until play resumes (#18)
const marks = ref([]) // #23: start times of today's lines marked "zu schwer" in this clip
const hardNote = ref('')
const rateFor = ref(null) // today's plan block this clip belongs to: {block, label, rating}
const rateBusy = ref(false)
let startPos = 0 // where this visit started (lines heard are counted from here without a plan range)
let pausedFor = null
let lastT = 0 // playhead at the previous tick
let touched = false // only save a position once the clip was actually played or moved
let loopLine = -1 // the line being looped (fixed when the loop starts or a line is chosen)
let raf = 0
let lastSaved = 0
// #30: where the clip should start (plan range, saved position, ?t=) until the element is really there.
// Before its metadata it can't seek and reports 0 — that 0 must never become his position.
let pendingStart = null
let startTries = 0
let jumpFrom = null // the playhead went back > 60 s by itself: from where (sent with the next save)
const analyses = new Map()

function readPref(key, fallback) {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v === '1'
  } catch {
    return fallback
  }
}
watch(autoPause, (v) => {
  try { localStorage.setItem('kaskade-autopause', v ? '1' : '0') } catch { /* private mode */ }
})

// #29: what is said (Whisper, "KI-Transkript") whenever the clip has it, else ARD's condensed subtitles
const trackPref = ref(storedTrack())
const track = computed(() => pickTrack(media.value, trackPref.value))
const spoken = computed(() => track.value.spoken)
const hasSpoken = computed(() => media.value?.spokenCues?.length > 0)
const cues = computed(() => (media.value ? speechCues(track.value.cues) : []))
// The line just heard stays until its end (and through an auto-pause); only in a gap the
// next one appears slightly early — seeking lands 0.1 s before a line.
const index = computed(() => shownLine(cues.value, t.value, held.value))
const line = computed(() => cues.value[index.value] ?? null)
const speaking = computed(() => inside(cues.value, index.value, t.value))
const standIn = computed(() => line.value?.src === 'ard') // #29: ARD's line where Whisper heard nothing
// #34: the line's sentence (over neighbouring lines): parsed as a whole, mined as a whole
const around = computed(() => (line.value ? sentenceAround(cues.value, index.value) : null))
const spokenLine = computed(() => spoken.value && !standIn.value)

async function load() {
  touched = false
  held.value = -1
  error.value = null
  media.value = null
  analysis.value = null
  token.value = null
  try {
    if (!route.params.id) {
      clips.value = (await api.get('/media')).filter((c) => c.hasMedia)
      if (!tags.value.length) tags.value = await api.get('/media/tags').catch(() => [])
      return
    }
    media.value = await api.get(`/media/${route.params.id}`)
    marks.value = []
    rateFor.value = null
    hardNote.value = ''
    loadRating(media.value.id)
    // ?t=… jumps to a line (e.g. from the Satz-Check result), ?loop=1 repeats it,
    // ?von=…&bis=… is today's plan range: start there (or at his position if he is behind).
    const at = Number(route.query.t)
    const von = Number(route.query.von)
    const bis = Number(route.query.bis)
    goal.value = false
    if (Number.isFinite(von) && Number.isFinite(bis) && bis > von) {
      const r = rangeStart(von, bis, media.value.position, media.value.rangeReached)
      range.value = { from: von, to: bis }
      rangeNote.value = r.note
      goal.value = r.reached
      t.value = r.at
    } else {
      range.value = null
      t.value = Number.isFinite(at) && at > 0 ? at : resumeAt(media.value.position, media.value.duration)
    }
    loop.value = route.query.loop === '1'
    startPos = t.value
    pendingStart = t.value > 0 ? t.value : null
    startTries = 0
    jumpFrom = null
    lastT = t.value
    loopLine = -1
    pausedFor = pausedBefore(cues.value, t.value) // a line that ended before the start: no pause for it on the first play
  } catch (e) {
    error.value = e.message
  }
}

// #23: is this clip one of today's blocks (then "Wie viel hast du verstanden?" comes at the end)?
async function loadRating(id) {
  try {
    const [hard, today] = await Promise.all([api.get(`/media/${id}/hard`), api.get('/ratings/today')])
    if (media.value?.id !== id) return
    marks.value = hard.marks.map((m) => m.start)
    rateFor.value = today.find((r) => r.mediaId === id) ?? null
  } catch {
    rateFor.value = null // no question then — watching still works
  }
}
// lines heard today: from the start of today's part (or of this visit) to the playhead
const share = computed(() => hardShare(cues.value, range.value ? Math.min(range.value.from, startPos) : startPos, t.value, marks.value))
const askRating = computed(() => goal.value && rateFor.value && !rateFor.value.rating)
async function rateClip(pct) {
  rateBusy.value = true
  try {
    const s = share.value
    rateFor.value = { ...rateFor.value, rating: await api.post('/ratings', { block: rateFor.value.block, item: rateFor.value.item, pct, hard: s.marked, lines: s.lines }) }
  } catch (e) {
    error.value = e.message
  } finally {
    rateBusy.value = false
  }
}

// Z = "zu schwer": count the line on screen (no card) and go on with the next one.
function markHard() {
  const i = index.value
  const c = cues.value[i]
  if (!c) return
  if (!marks.value.some((m) => Math.abs(m - c.start) < 0.05)) marks.value = [...marks.value, c.start]
  hardNote.value = `„${c.text.length > 40 ? c.text.slice(0, 40) + ' …' : c.text}“ als zu schwer markiert`
  api.post(`/media/${media.value.id}/hard`, { start: c.start, end: c.end, text: c.text, track: spoken.value ? 'spoken' : 'ard' }).catch((e) => { error.value = e.message })
  if (i < cues.value.length - 1) seekLine(i + 1)
  else video.value?.play().catch(() => {})
}
onMounted(load)
watch(() => route.params.id, load)

// The element can seek once it has its metadata: to the start — or, after a reload, back to where he was.
function onLoaded() {
  const v = video.value
  const at = pendingStart ?? t.value
  if (!v || !(at > 0) || Math.abs(v.currentTime - at) < 1) return
  pendingStart = at
  startTries = 0
  v.currentTime = at
}

/** #30: the element isn't where the clip should be yet (no metadata, or the start not reached): t keeps the start. */
function notThereYet(v) {
  if (v.readyState < 1) return true
  if (pendingStart === null) return false
  if (Math.abs(v.currentTime - pendingStart) < 1) {
    pendingStart = null
    return false
  }
  if (v.seeking) return true
  if (startTries++ < 3) {
    v.currentTime = pendingStart // the browser dropped the first seek: once more
    return true
  }
  pendingStart = null // it won't go there: from now on the jump check reports where it is
  return false
}
// where he is: the pending start, else the playhead
const here = (v) => pendingStart ?? (v.readyState < 1 ? t.value : v.currentTime)

// t follows the playhead; a jump back he didn't choose (> 60 s) goes with the next save (#30)
function follow(now) {
  if (jumpFrom === null && jumpedBack(t.value, now)) jumpFrom = t.value
  t.value = now
}
// A seek finished — ours, or one the browser made by itself (then it's a jump: shown and logged).
function onSeeked() {
  const v = video.value
  if (v && !notThereYet(v) && jumpedBack(t.value, v.currentTime)) follow(v.currentTime)
}

// Analyse the line once it is on screen, inside its sentence: only its own words come back (cached).
const analysisKey = (w) => `${w.focus.join(':')}|${w.text}`
watch(around, async (w) => {
  token.value = null
  if (!w) {
    analysis.value = null
    return
  }
  const key = analysisKey(w)
  if (analyses.has(key)) {
    analysis.value = analyses.get(key)
    return
  }
  analysis.value = null
  try {
    const a = await api.post('/analyze', { text: w.text, focus: w.focus })
    analyses.set(key, a)
    if (around.value && analysisKey(around.value) === key) analysis.value = a
  } catch {
    analysis.value = null // spaCy unavailable: plain text below
  }
})

function tick() {
  const v = video.value
  if (!v) return
  if (notThereYet(v)) {
    raf = requestAnimationFrame(tick)
    return
  }
  follow(v.currentTime)
  const cur = cues.value[loopLine]
  if (loop.value && !v.paused && cur && v.currentTime >= cur.end + 0.15) {
    v.currentTime = Math.max(0, cur.start - 0.1) // loop: back to the start of the line
  } else if (autoPause.value && !loop.value && !v.paused) {
    const i = shouldPause(cues.value, v.currentTime, pausedFor, lastT)
    if (i >= 0) {
      pausedFor = i
      held.value = i
      v.pause()
    }
  }
  lastT = v.currentTime
  if (range.value && !goal.value && v.currentTime >= range.value.to) {
    goal.value = true // today's part is done: stop once, he may watch on
    v.pause()
  }
  if (Date.now() - lastSaved > 10000) saveProgress()
  raf = requestAnimationFrame(tick)
}

function onPlay() {
  touched = true
  if (loopLine < 0 || !loop.value) loopLine = index.value
  held.value = -1
  lastT = video.value ? here(video.value) : 0
  playing.value = true
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(tick)
}
function onPause() {
  playing.value = false
  cancelAnimationFrame(raf)
  const v = video.value
  if (v && !notThereYet(v)) follow(v.currentTime)
  saveProgress()
}

const CANT_PLAY = 'Dieser Browser kann das Video nicht abspielen. Wird der Clip gerade umgewandelt, in ein paar Minuten neu laden — sonst den Clip im Satz-Check neu hochladen (er wird dann als H.264/MP4 gespeichert). Untertitel, Wörter und „Satz minen“ gehen trotzdem.'

function onVideoError() {
  error.value = CANT_PLAY
}

function toggle() {
  const v = video.value
  if (!v) return
  if (v.paused) {
    v.play().catch((e) => {
      // AbortError = a seek interrupted play(): harmless. Everything else: explain in German.
      if (e?.name !== 'AbortError') error.value = v.error || e?.name === 'NotSupportedError' ? CANT_PLAY : `Abspielen nicht möglich (${e?.name ?? 'Fehler'}).`
    })
  } else v.pause()
}

function seekLine(i, play = true) {
  const v = video.value
  const c = cues.value[i]
  if (!v || !c) return
  touched = true
  loopLine = i
  held.value = -1
  pausedFor = i - 1 // the lead-in belongs to the previous line: don't pause for it
  goTo(v, seekTarget(cues.value, i))
  t.value = c.start
  if (play) v.play().catch(() => {})
}
// A seek he chose. Without metadata yet the element can't: then it's the pending start.
function goTo(v, at) {
  startTries = 0
  if (v.readyState < 1) pendingStart = at
  else {
    pendingStart = null
    v.currentTime = at
  }
  lastT = at
  t.value = at
}

// #30: the playhead is far before today's part (whatever put it there): one click back to its start
const behindRange = computed(() => range.value && !goal.value && t.value < range.value.from - 30)
function backToRange() {
  const v = video.value
  if (!v || !range.value) return
  touched = true
  held.value = -1
  loopLine = -1
  pausedFor = pausedBefore(cues.value, range.value.from)
  goTo(v, range.value.from)
}
// ← / → / R / L act on the line on screen
const prev = () => seekLine(stepLine(cues.value, index.value, -1))
const next = () => seekLine(stepLine(cues.value, index.value, 1))
const replay = () => index.value >= 0 && seekLine(index.value)

// The other track, at the same time: the line there, no pause for what was already heard
function setTrack(tr) {
  if (trackPref.value === tr) return
  trackPref.value = tr
  storeTrack(tr)
  const now = video.value ? here(video.value) : t.value
  held.value = -1
  pausedFor = pausedBefore(cues.value, now)
  loopLine = index.value
}

function toggleLoop() {
  loop.value = !loop.value
  loopLine = index.value
}

function setRate(r) {
  rate.value = r
  if (video.value) video.value.playbackRate = r
}

function saveProgress() {
  lastSaved = Date.now()
  if (!touched || !media.value || !video.value) return
  const body = { position: here(video.value) }
  if (jumpFrom !== null) {
    Object.assign(body, { reason: 'jump', from: jumpFrom }) // logged as a warning on the server
    jumpFrom = null
  }
  fetch(`/api/media/${media.value.id}/progress`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    keepalive: true
  }).catch(() => {})
}

function selectWord(tok) {
  token.value = tok
  video.value?.pause()
}

let spaceHandled = false
function onKey(e) {
  if (!media.value || e.ctrlKey || e.metaKey || e.altKey) return
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target?.tagName)) return
  const k = e.key.toLowerCase()
  if (k === ' ') {
    e.preventDefault()
    spaceHandled = true
    toggle()
  } else if (k === 'arrowleft') {
    e.preventDefault()
    prev()
  } else if (k === 'arrowright') {
    e.preventDefault()
    next()
  } else if (k === 'r') {
    replay()
  } else if (k === 'l') {
    toggleLoop()
  } else if (k === 'z') {
    markHard()
  }
}
// Space on a focused button would also "click" it on keyup — swallow that.
function onKeyUp(e) {
  if (e.key === ' ' && spaceHandled) {
    e.preventDefault()
    spaceHandled = false
  }
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('pagehide', saveProgress)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('pagehide', saveProgress)
  cancelAnimationFrame(raf)
  saveProgress()
})

async function setTag(c, tag) {
  try {
    const row = await api.patch(`/media/${c.id}`, { tag })
    c.tag = row.tag
  } catch (e) {
    error.value = e.message
  }
}

// Satz minen: the whole sentence, its audio from the first to the last line
const extra = computed(() => (around.value ? { mediaId: media.value.id, start: around.value.start, end: around.value.end, ...(spokenLine.value ? { track: 'spoken' } : {}) } : null))
const minutesLeft = (c) => Math.max(0, Math.round((c.duration - c.position) / 60))
</script>

<template>
  <main class="k-main" data-testid="schauen">
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>

    <!-- Clip list -->
    <template v-if="!route.params.id">
      <div>
        <p class="k-eyebrow mb-1.5">Interaktiv schauen</p>
        <h1 class="k-h1">Schauen &amp; minen</h1>
        <p class="k-lead">Ein Clip aus deiner Bibliothek mit deutschen Untertiteln. Nach jeder Zeile pausiert das Video, du tippst unbekannte Wörter an und minest gute Sätze — mit dem Original-Ton als Karte.</p>
      </div>
      <section class="k-card" aria-labelledby="clips-h">
        <h2 id="clips-h" class="k-h2">Deine Clips</h2>
        <p v-if="clips && !clips.length" class="k-small m-0 mt-2">Noch kein Clip mit Video. Lade im <router-link to="/satz-check">Satz-Check</router-link> einen Clip mit Untertiteln hoch.</p>
        <ul class="list-none m-0 mt-3 p-0">
          <li v-for="c in clips ?? []" :key="c.id" class="sw-clip">
            <div class="min-w-0">
              <p class="m-0" style="font-weight: 700">{{ c.title }}</p>
              <p class="k-hint m-0">{{ formatTime(c.duration) }} · {{ c.isAudio ? 'nur Ton' : `${c.cueCount} Zeilen` }}<template v-if="c.source"> · {{ c.source }}</template><template v-if="c.hasSpoken"> · mit KI-Transkript</template><template v-if="c.position > 2"> · weiter ab {{ formatTime(c.position) }} (noch ≈ {{ minutesLeft(c) }} min)</template><template v-if="clipStatus(c)"> · {{ clipStatus(c) }}</template></p>
              <label class="k-small inline-flex items-center gap-2 mt-1">Genre
                <select class="sw-tag" :value="c.tag ?? ''" :data-testid="`tag-${c.id}`" @change="setTag(c, $event.target.value)">
                  <option value="">—</option>
                  <option v-for="g in tags" :key="g.id" :value="g.id">{{ g.label }}</option>
                </select>
              </label>
            </div>
            <router-link :to="`/schauen/${c.id}`" class="k-btn k-btn-sm" :data-testid="`watch-${c.id}`">{{ c.position > 2 ? 'Weiterschauen' : 'Schauen' }}</router-link>
          </li>
        </ul>
      </section>
    </template>

    <!-- Player -->
    <template v-else-if="media">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div class="min-w-0">
          <p class="k-eyebrow mb-1.5"><router-link to="/schauen">Schauen &amp; minen</router-link> · {{ cues.length }} Zeilen</p>
          <h1 class="k-h1" style="font-size: clamp(24px, 3vw, 32px)">{{ media.title }}</h1>
        </div>
        <router-link v-if="mined" to="/karten" class="k-chip k-chip-success" data-testid="watch-mined">✓ {{ mined }} {{ mined === 1 ? 'Satz' : 'Sätze' }} gemined → Karten</router-link>
      </div>

      <p v-if="range && goal" class="k-callout m-0" role="status" data-testid="watch-goal">
        <strong>Ziel für heute erreicht ✓</strong> (bis {{ clock(range.to) }}). Du kannst weiterschauen — oder auf Heute den Block mit „Fertig“ abschließen.
      </p>
      <div v-else-if="range" class="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p class="k-small m-0" data-testid="watch-range">{{ rangeNote }} Das Video hält am Ende des Teils einmal an.</p>
        <button v-if="behindRange" class="k-btn k-btn-sm" data-testid="watch-back" @click="backToRange">↩ Zurück zu {{ clock(range.from) }} (Teil von heute)</button>
      </div>
      <RateAsk v-if="askRating" :label="rateFor.label" :share="shareLine(share)" :busy="rateBusy" @rate="rateClip" />
      <p v-else-if="goal && rateFor?.rating" class="k-chip k-chip-success m-0" style="width: fit-content" data-testid="watch-rated">✓ {{ ratingLabel(rateFor.rating) }}</p>

      <div class="sw-grid">
        <div class="flex flex-col gap-3 min-w-0">
          <div :class="['sw-stage', { 'sw-stage-audio': media.isAudio }]">
            <p v-if="media.isAudio" class="sw-audio-label" aria-hidden="true">♪ Nur Ton · {{ media.title }}</p>
            <video
              ref="video"
              class="sw-video"
              :src="`/api/media/${media.id}/file`"
              preload="metadata"
              playsinline
              data-testid="watch-video"
              @loadedmetadata="onLoaded"
              @seeked="onSeeked"
              @error="onVideoError"
              @play="onPlay"
              @pause="onPause"
              @click="toggle"
            ></video>
          </div>

          <div class="k-card sw-line" data-testid="watch-line">
            <div v-if="hasSpoken" class="sw-track">
              <span v-if="spoken && !standIn" class="k-origin k-origin-ai" title="Von einer KI (Whisper) aus dem Ton geschrieben — vollständiger als die ARD-Untertitel, einzelne Wörter können falsch sein" data-testid="watch-ki">KI-Transkript</span>
              <span v-else-if="spoken" class="k-hint" data-testid="watch-standin">ARD-Untertitel — hier hat die KI nichts gehört</span>
              <span v-else class="k-hint">ARD-Untertitel · gekürzt</span>
              <div class="sw-seg" role="group" aria-label="Untertitel">
                <button type="button" :class="['sw-seg-btn', { on: spoken }]" :aria-pressed="spoken" data-testid="track-spoken" @click="setTrack('spoken')">Gesprochen (KI)</button>
                <button type="button" :class="['sw-seg-btn', { on: !spoken }]" :aria-pressed="!spoken" data-testid="track-ard" @click="setTrack('ard')">ARD-Untertitel</button>
              </div>
            </div>
            <div aria-live="polite">
            <template v-if="line">
              <AnalyzedText v-if="analysis" :analysis="analysis" :lens="false" :selected="token?.i ?? null" class="sw-text" @select="selectWord" />
              <p v-else class="k-read sw-text m-0">{{ line.text }}</p>
              <div class="flex flex-wrap items-center justify-between gap-2 mt-2">
                <p class="k-hint m-0">{{ formatTime(line.start) }} · Zeile {{ index + 1 }} von {{ cues.length }}{{ speaking ? '' : ' · Wort antippen zum Nachschlagen' }}</p>
                <button class="k-btn k-btn-ghost k-btn-sm" aria-label="Zeile zu schwer, weiter (Z)" data-testid="watch-hard" @click="markHard">✗ Zu schwer</button>
              </div>
              <p v-if="hardNote" class="k-hint m-0 mt-1" role="status" data-testid="watch-hard-note">{{ hardNote }} · {{ marks.length }} heute</p>
            </template>
            <p v-else-if="!cues.length" class="k-small m-0">Nur Ton, ohne Untertitel: einfach zuhören, nicht pausieren, nichts nachschlagen.</p>
            <p v-else class="k-small m-0">Drück Play — die Untertitel erscheinen hier, Zeile für Zeile.</p>
            </div>
          </div>

          <div class="sw-controls" role="group" aria-label="Wiedergabe">
            <button class="k-btn k-btn-ghost k-btn-sm" aria-label="Vorherige Zeile (Pfeil links)" data-testid="watch-prev" @click="prev">← Zeile</button>
            <button class="k-btn k-btn-sm" data-testid="watch-play" @click="toggle">{{ playing ? '❚❚ Pause' : '▶ Play' }}</button>
            <button class="k-btn k-btn-ghost k-btn-sm" aria-label="Nächste Zeile (Pfeil rechts)" data-testid="watch-next" @click="next">Zeile →</button>
            <button class="k-btn k-btn-ghost k-btn-sm" aria-label="Zeile wiederholen (R)" data-testid="watch-replay" @click="replay">↻ Nochmal</button>
            <button :class="['k-btn k-btn-sm', { 'k-btn-ghost': !loop }]" :aria-pressed="loop" aria-label="Zeile in Schleife (L)" data-testid="watch-loop" @click="toggleLoop">⟲ Schleife</button>
            <label class="k-small inline-flex items-center gap-2 sw-auto"><input v-model="autoPause" type="checkbox" :disabled="loop" data-testid="watch-autopause" /> nach jeder Zeile pausieren</label>
            <span class="k-small inline-flex items-center gap-1.5">
              Tempo
              <button v-for="r in [1, 0.85]" :key="r" :class="['k-btn k-btn-sm sw-rate', { 'k-btn-ghost': rate !== r }]" :aria-pressed="rate === r" @click="setRate(r)">{{ r === 1 ? '1×' : '0,85×' }}</button>
            </span>
          </div>
          <p class="k-hint m-0">Tasten: Leertaste Play/Pause · ← → Zeile zurück/vor · R Zeile wiederholen · L Schleife · Z zu schwer, weiter · <span data-testid="watch-clock">{{ range ? `${clock(t)} / Ziel ${clock(range.to)}` : `${formatTime(t)} / ${formatTime(media.duration)}` }}</span></p>
        </div>

        <div class="flex flex-col gap-4 min-w-0">
          <WordPanel
            v-if="analysis"
            :analysis="analysis"
            :token="token"
            :sentence="around?.text ?? null"
            :extra="extra"
            :source="`Schauen · ${media.title}`"
            @mined="(r) => { if (!r.duplicate) mined++ }"
          >
            <template #actions>
              <button class="k-btn k-btn-ghost k-btn-sm mt-1" data-testid="word-hard" @click="markHard">✗ Zu schwer (Z)</button>
            </template>
          </WordPanel>
          <section class="k-card k-small">
            <h2 class="k-h2" style="font-size: 17px">So geht's</h2>
            <ol class="m-0 mt-2 pl-5 flex flex-col gap-1.5" style="list-style: decimal">
              <li>Abspielen. Nach jeder Zeile hält das Video an.</li>
              <li>Nicht verstanden? R oder ↻ — so oft du willst. Langsamer mit 0,85×.</li>
              <li>Unbekanntes Wort antippen: Bedeutung, Artikel, Fall.</li>
              <li>Guter Satz? „Satz minen“ — der ganze Satz wird zur Karte, mit dem Original-Ton (auch wenn er über zwei Zeilen geht).</li>
              <li>Viel zu schwer? Z oder „Zu schwer“ — die Zeile wird nur gezählt (keine Karte), es geht mit der nächsten weiter.</li>
            </ol>
          </section>
        </div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.sw-clip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 0;
  border-top: 1px solid var(--surface-2);
}
.sw-grid { display: grid; gap: 24px; }
@media (min-width: 980px) { .sw-grid { grid-template-columns: minmax(0, 1fr) 340px; align-items: start; } }
.sw-stage { background: var(--stage-bg); border-radius: var(--radius-lg); overflow: hidden; }
.sw-stage-audio { position: relative; }
.sw-stage-audio .sw-video { aspect-ratio: auto; height: 120px; }
.sw-audio-label { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; margin: 0; padding: 0 16px; color: var(--stage-text); font-weight: 700; text-align: center; pointer-events: none; }
.sw-tag { min-height: 32px; border: var(--border-width) solid var(--border-strong); border-radius: var(--radius-sm); background: var(--surface); color: var(--text); font: inherit; font-size: 14px; padding: 0 6px; }
.sw-video { display: block; width: 100%; aspect-ratio: 16 / 9; max-height: 62vh; object-fit: contain; background: var(--stage-bg); }
.sw-line { min-height: 96px; }
.sw-track { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.sw-seg { display: inline-flex; border: var(--border-width) solid var(--border-strong); border-radius: var(--radius-pill); overflow: hidden; }
.sw-seg-btn { min-height: 32px; padding: 0 12px; border: 0; background: var(--surface); color: var(--text-2); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
.sw-seg-btn + .sw-seg-btn { border-left: var(--border-width) solid var(--border-strong); }
.sw-seg-btn.on { background: var(--primary); color: var(--primary-text); }
.sw-seg-btn:hover:not(.on) { background: var(--surface-2); }
.sw-text { font-size: clamp(20px, 2.6vw, 26px); line-height: 1.6; }
.sw-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.sw-auto { margin-left: 4px; }
.sw-rate { padding: 0 10px; }
</style>
