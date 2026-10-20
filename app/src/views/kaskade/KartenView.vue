<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../../lib/api'
import { cardWords, markTargets } from '../../lib/cards'
import { createRevealTimer, DOUBLE_TAP_MS, grade, GRADE_LABEL, progress, storeAutoplay, storedAutoplay, waitLine } from '../../lib/reveal'
import { useNow } from '../../lib/useNow'
import { playbackOver, speak, stopSpeaking } from '../../lib/speech'
import { audioNote, cardBadge } from '../../lib/origin'
import AiMark from '../../components/kaskade/AiMark.vue'
import MinedEditor from '../../components/kaskade/MinedEditor.vue'
import MinedList from '../../components/kaskade/MinedList.vue'
import OriginBadge from '../../components/kaskade/OriginBadge.vue'
import RevealClock from '../../components/kaskade/RevealClock.vue'

const data = ref(null)
const stats = ref(null)
const revealed = ref(false)
const busy = ref(false)
const error = ref(null)
const flash = ref(null)
// #25: the rating comes from the time to reveal (paused while the tab is hidden or not focused)
const timer = createRevealTimer()
const revealMs = ref(null)
let revealedAt = 0
const now = useNow(1000)
// #28: the timer is on the card; with autoplay it starts when the sentence's audio is over
const autoplay = ref(storedAutoplay())
const phase = ref(null) // audio (clip playing, not counted) | run | pause (window without focus) | done (revealed)
const blocked = ref(false) // the browser refused to play without a click
let shownAutoplay = false // the box when this card came up (logged with the review)
let shown = 0 // counts cards shown: a clip of an earlier card that ends late starts nothing
let lastPlay = null

const card = computed(() => data.value?.card)
const editing = ref(false) // the shown mined card in the editor (#19)
const minedList = ref(null)
const isMined = computed(() => card.value?.id.startsWith('mine:'))
const words = computed(() => (card.value ? (isMined.value ? cardWords(card.value) : [{ ...card.value, ai: [] }]) : []))
const segments = computed(() => (card.value ? markTargets(card.value.sentence, words.value.map((w) => w.target)) : []))
// #25: cards done today against cards still open today — a card in a step stays open
const prog = computed(() => progress(data.value?.counts))
const gewusstAs = computed(() => grade(revealMs.value ?? 0, data.value?.timing)) // what "Gewusst" means for this card
const waiting = computed(() => (!card.value && data.value?.wait ? waitLine(data.value.wait, now.value.getTime()) : null))

let loading = false
async function load() {
  error.value = null
  loading = true
  try {
    data.value = await api.get('/cards/next')
    revealed.value = false
    revealMs.value = null
    editing.value = false
    if (data.value.card) show()
  } catch (e) {
    error.value = e.message
  } finally {
    loading = false
  }
}
// a card waiting in a step comes back by itself
watch(now, (n) => {
  const at = data.value?.wait?.at
  if (at && !card.value && !loading && n.getTime() >= Date.parse(at)) load()
})

// A card comes up: play its sentence once (not counted), then the timer runs
async function show() {
  const id = ++shown
  timer.reset()
  blocked.value = false
  shownAutoplay = autoplay.value
  if (!autoplay.value) return startTimer()
  phase.value = 'audio'
  playAudio()
  const how = await playbackOver(() => lastPlay) // A during the clip: its replay isn't counted either
  if (id !== shown || phase.value !== 'audio') return // the next card is up, or he revealed during the clip
  if (how === 'blocked') blocked.value = true
  if (how === 'blocked' || how === 'error') shownAutoplay = false // nothing played: timed like without autoplay
  startTimer()
}
function startTimer() {
  timer.start()
  phase.value = 'run'
  if (document.hidden || !document.hasFocus()) pauseTimer()
}
function pauseTimer() {
  if (phase.value !== 'run') return
  timer.pause()
  phase.value = 'pause'
}
function resumeTimer() {
  if (phase.value !== 'pause' || document.hidden || !document.hasFocus()) return
  timer.resume()
  phase.value = 'run'
}
function reveal() {
  if (!card.value || revealed.value) return
  revealMs.value = timer.stop() // during the clip: 0 → Leicht
  phase.value = 'done'
  revealed.value = true
  revealedAt = performance.now()
}
const onVisibility = () => (document.hidden ? pauseTimer() : resumeTimer())
const onBlur = () => pauseTimer()
const onFocus = () => resumeTimer()

watch(autoplay, (on) => {
  storeAutoplay(on)
  if (!on) stopSpeaking() // during the clip: the timer starts now
})
// A click with the mouse doesn't leave the focus on the box, so Leertaste reveals again
const blurAfterClick = (e) => { if (e.detail > 0) e.target.blur() }

async function loadStats() {
  try {
    stats.value = await api.get('/cards/stats')
  } catch {
    stats.value = null
  }
}

onMounted(async () => {
  await Promise.all([load(), loadStats()])
  window.addEventListener('keydown', onKey)
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('blur', onBlur)
  window.addEventListener('focus', onFocus)
})
onBeforeUnmount(() => {
  shown++
  stopSpeaking()
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('visibilitychange', onVisibility)
  window.removeEventListener('blur', onBlur)
  window.removeEventListener('focus', onFocus)
})

async function act(fn, message) {
  if (busy.value || !card.value) return
  busy.value = true
  try {
    await fn()
    flash.value = message
    await load()
    loadStats()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

// "Gewusst": Leicht/Gut/Schwer from the time; "Nicht gewusst" = Nochmal; keys 1–4 override silently
const rate = (r, auto = false) => revealed.value && act(() => api.post(`/cards/${card.value.id}/review`, { rating: r, revealMs: revealMs.value, auto, autoplay: shownAutoplay }), null)
const gewusst = () => rate(gewusstAs.value, true)
const nichtGewusst = () => rate(1)
const known = () => act(() => api.post(`/cards/${card.value.id}/known`), `„${card.value.lemma}“ — kenne ich schon. Kommt nicht wieder.`)

async function undo() {
  if (busy.value) return
  busy.value = true
  try {
    await api.post('/cards/undo')
    flash.value = 'Rückgängig gemacht.'
    await load()
    loadStats()
  } catch (e) {
    flash.value = e.message
  } finally {
    busy.value = false
  }
}

function onSaved(c) {
  data.value = { ...data.value, card: { ...data.value.card, ...c } }
  editing.value = false
  flash.value = 'Karte gespeichert.'
  minedList.value?.reload()
}
async function onDeleted() {
  editing.value = false
  flash.value = 'Karte gelöscht.'
  await load()
  loadStats()
  minedList.value?.reload()
}
function onListChanged(change) {
  // edited or deleted in the list: the card on screen may be the same one
  if (card.value?.id !== change.id) return
  if (change.deleted) onDeleted()
  else data.value = { ...data.value, card: { ...data.value.card, ...change.card } }
}

function playAudio() {
  if (!card.value) return null
  blocked.value = false
  lastPlay = speak(card.value.sentence, { url: `/api/cards/${card.value.id}/audio` })
  return lastPlay
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || editing.value) return // no shortcuts while editing a card
  if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(e.target?.tagName) && e.key === ' ') return
  const k = e.key.toLowerCase()
  if (k === ' ' || k === 'enter') {
    e.preventDefault()
    if (!card.value) return
    if (!revealed.value) reveal()
    else if (performance.now() - revealedAt >= DOUBLE_TAP_MS) gewusst() // a double tap doesn't rate
  } else if (k === 'n') {
    nichtGewusst()
  } else if (['1', '2', '3', '4'].includes(k)) {
    rate(Number(k))
  } else if (k === 'k') {
    known()
  } else if (k === 'z') {
    undo()
  } else if (k === 'a') {
    playAudio()
  }
}

</script>

<template>
  <main class="k-main k-karten">
    <div class="flex flex-wrap gap-6 items-start">
      <div class="flex flex-col gap-4 min-w-0" style="flex: 999 1 560px">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h1 class="k-h1" style="font-size: 32px">Karten</h1>
          <p class="m-0 k-small" data-testid="karten-progress"><strong style="color: var(--text)">{{ prog.text }}</strong> · heute</p>
        </div>
        <div class="k-progress" role="img" :aria-label="`${prog.done} Karten fertig, ${prog.left} offen`" data-testid="karten-bar" :data-pct="prog.pct"><div :style="{ width: prog.pct + '%' }"></div></div>

        <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>

        <article v-if="card" class="k-card kc-card" data-testid="karte">
          <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
            <span class="k-eyebrow kc-eyebrow">{{ card.isNew ? 'Neu' : 'Wiederholung' }} · {{ card.n ? `Kernwort ${card.n}` : `Gemined · ${card.source || 'Lesen'}` }}</span>
            <div class="kc-tools">
              <div class="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
                <RevealClock :timer="timer" :phase="phase" :final-ms="revealMs" :timing="data.timing" />
                <button type="button" class="kc-audio" data-testid="karte-audio" aria-label="Satz vorlesen (Taste A)" @click="playAudio">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9z" /><path d="M16.5 8.5a5 5 0 0 1 0 7" /></svg>
                  Audio <span class="kc-voice" data-testid="karte-voice">{{ audioNote(card) }}</span> <kbd class="k-kbd">A</kbd>
                </button>
              </div>
              <label class="k-small kc-auto"><input v-model="autoplay" type="checkbox" data-testid="karte-autoplay" @click="blurAfterClick" /> Audio automatisch abspielen</label>
              <p v-if="blocked" class="k-hint m-0" data-testid="karte-blocked">Autoplay vom Browser blockiert — A drücken</p>
            </div>
          </div>
          <p class="k-read kc-sentence" data-testid="karte-satz"><template v-for="(seg, i) in segments" :key="i"><mark v-if="seg.mark" class="k-mark">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></p>
          <p v-if="!revealed" class="k-small m-0 mt-auto" data-testid="karte-front-hint">{{ autoplay ? 'Zuhören, einmal laut mitsprechen, dann aufdecken.' : 'Verstehst du den ganzen Satz? Einmal laut mitsprechen, dann aufdecken.' }}</p>
          <MinedEditor v-else-if="editing" :card="card" @saved="onSaved" @deleted="onDeleted" @cancel="editing = false" />
          <div v-else class="kc-back" data-testid="karte-back">
            <template v-for="(w, wi) in words" :key="w.target">
              <div class="flex flex-col gap-1.5" :data-testid="`karte-wort-${wi}`">
                <p class="m-0 flex flex-wrap items-center gap-2" style="font-size: 24px; font-weight: 800">{{ w.display }} <AiMark v-if="w.ai.includes('lemma')" field="lemma" /></p>
                <p class="m-0 k-read flex flex-wrap items-center gap-2" style="font-size: 18px; color: var(--text-2)">„{{ w.gloss }}“ <AiMark v-if="w.ai.includes('gloss')" field="gloss" /></p>
                <template v-if="wi === 0">
                  <p v-if="card.en" class="m-0 mt-2" style="font-size: 15px; color: var(--muted)">{{ card.en }}</p>
                  <span v-if="cardBadge(card) || card.transcript" class="mt-2 flex flex-wrap items-center gap-2">
                    <span v-if="cardBadge(card)" data-testid="karte-origin"><OriginBadge :origin="card.origin" :source="card.originSource" :fallback="card.n ? 'ai' : null" /></span>
                    <span v-if="card.transcript" class="k-origin k-origin-ai" title="Der Satz kommt aus dem KI-Transkript (Whisper) — ein Wort kann falsch gehört sein" data-testid="karte-transcript">KI-Transkript</span>
                  </span>
                </template>
              </div>
              <div v-if="w.note || w.case" class="kc-note" :data-testid="`karte-note-${wi}`">
                <span v-if="w.case" :class="['k-case', `k-case-${w.case}`]" :aria-label="`Kasus ${w.case}`" data-testid="karte-case">{{ w.case }}</span>
                <p class="m-0" style="font-size: 15px; line-height: 1.5">{{ w.note }} <AiMark v-if="w.ai.includes('case')" field="case" /></p>
              </div>
            </template>
            <div v-if="isMined" class="kc-edit">
              <button type="button" class="k-btn k-btn-ghost k-btn-sm" data-testid="karte-edit" @click="editing = true">Bearbeiten oder löschen</button>
            </div>
          </div>
        </article>

        <section v-else-if="data && data.counts.left > 0" class="k-card flex flex-col gap-3" data-testid="karten-wait">
          <h2 class="k-h2" aria-live="polite">{{ waiting ?? `Noch ${data.counts.left} Karten offen` }}</h2>
          <p class="k-small m-0">Sie sind in einem kurzen Lernschritt und erscheinen hier von selbst wieder. Bis dahin: Pause, oder schon mal ins Schauen.</p>
        </section>

        <section v-else-if="data" class="k-card flex flex-col gap-3" data-testid="karten-fertig">
          <template v-if="stats && stats.deckSize === 0">
            <h2 class="k-h2">Kein Kerndeck gefunden</h2>
            <p class="k-small m-0">Der Server findet keine Dateien in <code>data/core-deck/</code>. Im Repo prüfen und <code>systemctl --user restart kaskade-api</code>.</p>
          </template>
          <template v-else>
            <h2 class="k-h2">Fertig für heute 🎉</h2>
            <p class="k-small m-0">{{ prog.done ? `${prog.done} Karten heute.` : 'Heute ist nichts mehr fällig.' }} Morgen kommen neue Kernwörter.</p>
          </template>
          <div><router-link to="/" class="k-btn">Zurück zu Heute</router-link></div>
        </section>

        <template v-if="card">
          <button v-if="!revealed" class="k-btn kc-reveal" data-testid="karte-reveal" @click="reveal">
            Antwort zeigen <kbd class="k-kbd">Leertaste</kbd>
          </button>
          <div v-else class="kc-rates">
            <button type="button" class="kc-rate kc-rate-primary" data-testid="karte-gewusst" :disabled="busy" @click="gewusst">
              <span data-testid="karte-gewusst-label">Gewusst · {{ GRADE_LABEL[gewusstAs] }} · {{ data.intervals[gewusstAs] }}</span>
              <span class="kc-ivl"><kbd class="k-kbd">Leertaste</kbd></span>
            </button>
            <button type="button" class="kc-rate" data-testid="karte-nicht" :disabled="busy" @click="nichtGewusst">
              <span>Nicht gewusst · {{ data.intervals[1] }}</span>
              <span class="kc-ivl"><kbd class="k-kbd">N</kbd></span>
            </button>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <button class="k-btn k-btn-ghost k-btn-sm" :disabled="busy" data-testid="karte-known" @click="known">Kenne ich schon <kbd class="k-kbd">K</kbd></button>
            <button class="k-btn k-btn-ghost k-btn-sm" :disabled="busy" @click="undo">Rückgängig <kbd class="k-kbd">Z</kbd></button>
          </div>
        </template>
        <p v-if="flash" class="k-hint m-0" aria-live="polite">{{ flash }}</p>
        <p class="k-hint m-0">Leertaste aufdecken · Leertaste gewusst · N nicht gewusst · K kenne ich schon · A Audio · Z rückgängig</p>
      </div>

      <aside aria-label="Sitzung" class="flex flex-col gap-4 min-w-0" style="flex: 1 1 320px">
        <section v-if="data" class="k-card" aria-labelledby="today-h">
          <h2 id="today-h" class="k-h2" style="font-size: 17px">Heute fällig</h2>
          <div class="grid grid-cols-2 gap-3 mt-3">
            <div><p class="m-0" style="font-size: 28px; font-weight: 800" data-testid="due-count">{{ data.counts.left }}</p><p class="k-small m-0">offen<template v-if="data.counts.new"> · davon {{ data.counts.new }} neu</template></p></div>
            <div><p class="m-0" style="font-size: 28px; font-weight: 800" data-testid="done-count">{{ data.counts.doneToday }}</p><p class="k-small m-0">fertig</p></div>
          </div>
          <p v-if="data.counts.newHeld" class="k-small m-0 mt-2.5" data-testid="new-held">Nach der freien Woche erst die fälligen — neue Karten kommen wieder, sobald weniger als 20 fällig sind.</p>
          <p class="k-small m-0 mt-3.5 pt-3" style="border-top: 1px solid var(--surface-2)">
            FSRS-Ziel: <strong style="color: var(--text)">90 % behalten</strong><template v-if="stats?.retention30 != null"> · letzte 30 Tage: {{ Math.round(stats.retention30 * 100) }} %</template>
          </p>
        </section>
        <section v-if="stats" class="k-card" aria-labelledby="deck-h">
          <h2 id="deck-h" class="k-h2" style="font-size: 17px">Kernwortschatz</h2>
          <ul class="list-none m-0 mt-2.5 p-0 flex flex-col gap-2 text-sm">
            <li class="flex justify-between"><span>Kenne ich schon</span><strong>{{ stats.known }}</strong></li>
            <li class="flex justify-between"><span>Am Lernen</span><strong>{{ stats.learning }}</strong></li>
            <li class="flex justify-between"><span>Davon sicher (≥ 21 Tage)</span><strong>{{ stats.mature }}</strong></li>
            <li class="flex justify-between"><span>Noch nicht gesehen</span><strong>{{ stats.unseen }}</strong></li>
          </ul>
        </section>
        <MinedList ref="minedList" @changed="onListChanged" />
        <section class="k-callout" aria-labelledby="k-h">
          <h2 id="k-h" class="m-0" style="font-size: 15px; font-weight: 800; color: var(--text)">Erst sortieren, dann lernen</h2>
          <p class="m-0 mt-1.5">Du kennst schon viele Kernwörter. Drück <strong>K</strong>, wenn du den Satz sofort verstehst — die Karte ist dann für immer weg und zählt nicht zu den 20 neuen pro Tag.</p>
        </section>
        <section class="k-card" aria-labelledby="leech-h">
          <h2 id="leech-h" class="k-h2" style="font-size: 15px">Immer wieder vergessen?</h2>
          <p class="k-small m-0 mt-1.5">Nach 4× „Nochmal“ wird die Karte pausiert, damit sie dich nicht aufhält.</p>
        </section>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.kc-card { padding: 32px 40px; min-height: 380px; display: flex; flex-direction: column; gap: 22px; border-radius: calc(var(--radius-lg) + 4px); }
.kc-sentence { margin: 0; font-size: clamp(24px, 4vw, 32px); line-height: 1.5; }
.kc-audio {
  display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 14px;
  border-radius: var(--radius-pill); border: var(--border-width) solid var(--border-strong);
  background: var(--surface); color: var(--text); font: inherit; font-weight: 700; font-size: 14px; cursor: pointer;
}
.kc-audio:disabled { opacity: 0.5; cursor: default; }
.kc-voice { font-size: 12px; font-weight: 600; color: var(--muted); }
.kc-eyebrow { min-height: 44px; display: inline-flex; align-items: center; }
.kc-tools { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; margin-left: auto; text-align: right; }
.kc-auto { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; }
.kc-back { border-top: 1px solid var(--surface-2); padding-top: 20px; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; }
.kc-edit { grid-column: 1 / -1; }
.kc-note { display: flex; gap: 12px; align-items: flex-start; background: var(--bg); border-radius: 12px; padding: 14px; }
.kc-reveal { min-height: 60px; font-size: 18px; font-weight: 800; border-radius: var(--radius-lg); }
.kc-rates { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 10px; }
.kc-rate {
  min-height: 64px; border: var(--border-width) solid var(--border-strong); border-radius: 12px;
  background: var(--surface); color: var(--text); font: inherit; font-weight: 800; font-size: 16px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; cursor: pointer;
}
.kc-rate:hover { background: var(--surface-2); }
.kc-rate-primary { background: var(--primary); color: var(--primary-text); border-color: var(--primary); }
.kc-rate-primary:hover { background: var(--primary-hover); }
.kc-ivl { font-size: 13px; font-weight: 500; opacity: 0.8; }
@media (max-width: 480px) {
  .kc-card { padding: 20px 16px; min-height: 300px; }
  .kc-rates { grid-template-columns: minmax(0, 1fr); }
}
</style>
