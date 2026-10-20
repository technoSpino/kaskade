<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../lib/api'
import { formatClock, formatDate, formatNumber } from '../../lib/format'
import { berlinMinutes, greeting, layoutBlocks, levelToPct, nextBlock, nowMarker, NO_HOURS_YET, PHASE2_TARGET, previewHint, weekStack } from '../../lib/heute'
import ImmersionForm from '../../components/kaskade/ImmersionForm.vue'
import MaterialsCard from '../../components/kaskade/MaterialsCard.vue'
import DueSoon from '../../components/kaskade/DueSoon.vue'
import OriginBadge from '../../components/kaskade/OriginBadge.vue'
import RateAsk from '../../components/kaskade/RateAsk.vue'
import { itemLine } from '../../lib/materials'
import { ratingLabel, shareLine } from '../../lib/ratings'
import { useNow } from '../../lib/useNow'
import { useStatusStore } from '../../stores/statusStore'
import { coverageLabel } from '../../lib/satzcheck'

const router = useRouter()
const status = useStatusStore()
const now = useNow(15000)
const t = ref(null)
const error = ref(null)
const feed = ref(null)
const copied = ref(false)
// The feed link points at Kaskade's HTTPS address (#17) — podcast apps want HTTPS.
const feedUrl = computed(() => `${t.value?.httpsUrl ?? window.location.origin}/api/feed.xml`)

const mat = ref(null) // Material für heute und morgen + Bald fällig (#16)
async function loadMaterials() {
  try {
    mat.value = await api.get('/materials')
  } catch (e) {
    error.value = e.message
  }
}

async function load() {
  try {
    t.value = await api.get('/today')
    error.value = null
  } catch (e) {
    error.value = e.message
  }
}
onMounted(async () => {
  loadMaterials()
  await load()
  try {
    feed.value = await api.get('/feed/info')
  } catch {
    feed.value = null
  }
})

async function copyFeed() {
  try {
    await navigator.clipboard.writeText(feedUrl.value)
    copied.value = true
  } catch {
    copied.value = false
  }
}

const minutes = computed(() => berlinMinutes(now.value))
const day = computed(() => t.value?.day ?? t.value?.preview?.day ?? null)
const planInfo = computed(() => (t.value?.day ? t.value : t.value?.preview ?? null))
const isPreview = computed(() => !!t.value && !t.value.day)
const hint = computed(() => previewHint(t.value))
const layout = computed(() => (t.value ? layoutBlocks(t.value.block) : null))
const marker = computed(() => (t.value && !isPreview.value ? nowMarker(t.value.block, minutes.value) : null))
const suggestion = computed(() => (t.value && !isPreview.value ? nextBlock(t.value.block, t.value.done, minutes.value) : null))
// The server's date (Berlin), so the label always matches the plan day shown below.
const dateLabel = computed(() =>
  new Intl.DateTimeFormat('de-DE', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }).format(
    t.value?.date ? new Date(`${t.value.date}T12:00:00Z`) : now.value
  )
)
const bars = computed(() => (t.value ? weekStack(t.value.weekTotals.seconds, t.value.weekTotals.passive) : []))
const sumH = (arr) => arr.reduce((a, b) => a + b, 0) / 3600
const activeH = computed(() => (t.value ? sumH(t.value.weekTotals.seconds) : 0))
const passiveH = computed(() => (t.value ? sumH(t.value.weekTotals.passive) : 0))
const showForm = ref(false)
const hours = (x) => x.toLocaleString('de-DE', { maximumFractionDigits: 1 })
const todayIndex = computed(() => (t.value ? t.value.weekTotals.days.indexOf(t.value.date) : -1))
// #36: days of a week off count as "frei" in the chart, not as missed
const isFree = (i) => !!t.value?.weekTotals.free?.[i]
const anyFree = computed(() => !!t.value?.weekTotals.free?.some(Boolean))
const weekOff = computed(() => !!t.value?.weekTotals.free?.slice(0, 5).every(Boolean))
const skills = computed(() => t.value?.placement?.skills ?? null)
const nextSatzcheck = computed(() => {
  const sc = t.value?.satzcheck
  if (!sc) return null
  const d = new Date(sc.createdAt)
  d.setDate(d.getDate() + 28)
  return d
})

// #16: every block names exactly one thing (title · part · minutes); the day text says how.
const assignment = (b) => t.value?.assignments?.[b.id] ?? null

function describe(b) {
  const d = day.value
  if (!d) return ''
  switch (b.kind) {
    case 'karten': return d.karten
    // #21: a rolling clip brings the plan text with its real range ("Tatort: Schweigen, 7:10–34:34 …")
    case 'input': return assignment(b)?.text ?? d.input
    case 'pause': return 'Aufstehen, Wasser trinken, kurz ans Fenster und raus.'
    case 'lesen': return assignment(b)?.text ?? d.lesen
    case 'pruefung': {
      if (assignment(b)?.text) return assignment(b).text // #24 the Lesetest
      const exam = planInfo.value?.exam
      if (planInfo.value?.mockExam) return planInfo.value.mockExam.note
      return exam ? `${exam.type}: „${exam.title}“` : 'Heute keine Prüfungsaufgabe — stattdessen Wochenrückblick.'
    }
  }
  return ''
}

const isRunning = (b) => status.running?.block === b.id
const isDone = (b) => t.value?.done.includes(b.id)
const logged = (b) => Math.round((t.value?.blockSeconds?.[b.id] ?? 0) / 60)
const runningFor = computed(() => (status.running ? (now.value - new Date(status.running.startedAt)) / 1000 : 0))

async function start(b) {
  const a = assignment(b)
  // YouTube/Netflix open in a new tab (Language Reactor) — before any await, or the popup is blocked.
  if (a?.start?.href) window.open(a.start.href, '_blank', 'noopener')
  try {
    await status.startTimer(b.id)
    if (a?.start?.to) return router.push(a.start.to)
    // a link (opened above), a book, the news links below, a clip still being fetched: stay here.
    // The exam block always falls through to its task (#20).
    if (a && b.kind !== 'pruefung') return load()
    if (b.kind === 'karten') return router.push('/karten')
    if (b.kind === 'input' && t.value?.watch) return router.push(`/schauen/${t.value.watch.id}`)
    if ((b.kind === 'input' || b.kind === 'lesen') && t.value?.texts?.[b.kind]) return router.push(`/lesen/${t.value.texts[b.kind].id}`)
    if (b.kind === 'pruefung' && planInfo.value?.exam) return router.push(`/aufgabe/${planInfo.value.exam.id}`)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function stop() {
  await status.stopTimer()
  await load()
}

// #27: the second item of a block ("Danach …"): opens its source, the block timer keeps running
async function openThen(b, n) {
  if (n.start?.href) window.open(n.start.href, '_blank', 'noopener')
  try {
    if (!isRunning(b)) await status.startTimer(b.id)
    if (n.start?.to) return router.push(n.start.to)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

// #23: "Wie viel hast du verstanden?" — asked on the block once it's done or its timer stopped
const rating = ref(null) // item being saved
async function rate(b, pct, item = assignment(b)) {
  rating.value = item.rateItem
  try {
    await api.post('/ratings', { block: b.id, item: item.rateItem, pct })
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    rating.value = null
  }
}

async function tickTodo(todo) {
  try {
    await api.post(`/todos/${todo.id}`, { done: true })
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function toggleDone(b) {
  try {
    if (isRunning(b)) await status.stopTimer()
    await api.post('/plan/done', { block: b.id, done: !isDone(b) })
    await load()
  } catch (e) {
    error.value = e.message
  }
}

const SKILLS = [
  { key: 'lesen', label: 'Lesen' },
  { key: 'hoeren', label: 'Hören' },
  { key: 'schreiben', label: 'Schreiben' },
  { key: 'sprechen', label: 'Sprechen' }
]
const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const KIND_LABEL = { karten: 'Karten', input: 'Interaktiv schauen / lesen', pause: 'Pause', lesen: 'Freies Lesen · ohne Tools', pruefung: 'B1-Prüfungsteil' }
const SHORT_LABEL = { karten: 'Karten', input: 'Schauen', lesen: 'Lesen', pruefung: 'Prüfung' }
// Labels come from the plan data (they differ between 2A and 2B); the maps are fallbacks.
const kindLabel = (b) => b.label ?? KIND_LABEL[b.kind]
const shortLabel = (b) => b.short ?? SHORT_LABEL[b.kind]

/** The highlighted block: the running one, else the suggested one (plan days only). */
const currentId = computed(() => (isPreview.value ? null : status.running?.block ?? suggestion.value?.id ?? null))
function segState(b) {
  if (b.kind === 'pause') return 'pause'
  if (!isPreview.value && isDone(b)) return 'done'
  return b.id === currentId.value ? 'current' : 'upcoming'
}
// Labels are hidden in segments too narrow for them (see the container queries below).
const segWidthClass = (b) => (b.minutes < 30 ? 'hb-w-s' : b.minutes < 50 ? 'hb-w-m' : '')
const timelineLabel = computed(() => {
  if (!layout.value) return ''
  const parts = layout.value.items.filter((b) => b.kind !== 'pause').map((b) => {
    const state = { done: 'erledigt', current: 'aktuell', upcoming: 'offen' }[segState(b)]
    return `${b.start} ${shortLabel(b)} (${b.minutes} min, ${state})`
  })
  return `Zeitleiste 09:00 bis 11:30: ${parts.join(', ')}`
})
</script>

<template>
  <main class="k-main" data-testid="heute">
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>

    <div class="flex flex-wrap items-end justify-between gap-4">
      <div class="min-w-0">
        <p class="k-eyebrow mb-1.5">{{ dateLabel }}</p>
        <h1 class="k-h1">{{ greeting(minutes) }}, {{ t?.name ?? 'Matt' }}.</h1>
        <p v-if="t && !isPreview" class="k-lead">
          Woche {{ t.week }} · {{ t.theme }} · Lernblock 09:00–11:30, 2 h 20 min aktiv, 10 min Pause.
          Heute: <strong style="color: var(--text)">{{ day.focus }}</strong>
        </p>
        <template v-else-if="t && t.pause">
          <!-- #36: a week off — one calm line, no blocks; Karten stay open but optional -->
          <p class="k-lead" data-testid="heute-pause">{{ t.pause.line }}</p>
          <p class="k-small m-0 mt-2"><router-link to="/karten" style="font-weight: 600" data-testid="pause-karten">Karten freiwillig · {{ t.cards.due }} fällig</router-link></p>
        </template>
        <p v-else-if="t && t.beforeStart" class="k-lead">
          Der Plan startet bald. Woche 1 beginnt am <strong style="color: var(--text)">{{ formatDate(t.preview.date) }}</strong>. Wenn du magst: Einstufung machen und die ersten Karten sortieren.
        </p>
        <p v-else-if="t" class="k-lead">
          Wochenende — kein Lernblock. Weiter geht es am <strong style="color: var(--text)">{{ formatDate(t.preview.date) }}</strong> (Woche {{ t.preview.week }}). Karten und Lesen gehen trotzdem über das Menü.
        </p>
      </div>
      <router-link v-if="t && !t.placement" to="/einstufung" class="k-btn" data-testid="heute-einstufung">Zuerst: Einstufung →</router-link>
      <button v-else-if="suggestion && !isRunning(suggestion)" class="k-btn" @click="start(suggestion)">Weiter: {{ kindLabel(suggestion) }} →</button>
    </div>

    <section v-for="todo in t?.todos ?? []" :key="todo.id" class="k-card k-card-strong hb-todo" :aria-labelledby="`todo-${todo.id}`" :data-testid="`todo-${todo.id}`">
      <p class="k-eyebrow mb-1">Zu erledigen · Woche {{ t.week }}</p>
      <h2 :id="`todo-${todo.id}`" class="k-h2">{{ todo.title }}</h2>
      <p class="m-0 mt-1.5">{{ todo.text }}</p>
      <ol class="m-0 mt-3 pl-5 flex flex-col gap-1 k-small" style="list-style: decimal">
        <li v-for="step in todo.steps" :key="step">{{ step }}</li>
      </ol>
      <p v-if="todo.note" class="k-hint m-0 mt-2">{{ todo.note }}</p>
      <div class="flex flex-wrap items-center gap-3 mt-3">
        <button class="k-btn k-btn-sm" :data-testid="`todo-done-${todo.id}`" @click="tickTodo(todo)">✓ Erledigt</button>
        <span v-if="todo.doneWhen === 'ai'" class="k-hint">Verschwindet auch von selbst, sobald der Schlüssel gesetzt ist.</span>
      </div>
    </section>

    <section v-if="t?.tooHard?.length" class="k-card k-card-strong" aria-labelledby="hard-h" data-testid="too-hard">
      <h2 id="hard-h" class="k-h2" style="font-size: 18px">Zu schwer</h2>
      <ul class="list-none m-0 mt-2 p-0 flex flex-col gap-2.5">
        <li v-for="r in t.tooHard" :key="r.id" :data-testid="`too-hard-${r.id}`">
          <p class="m-0" style="font-weight: 700">Zu schwer: {{ r.label }} ({{ r.pct }} %)</p>
          <p class="k-small m-0 mt-0.5">→ {{ r.action }}</p>
        </li>
      </ul>
    </section>

    <div v-if="t" class="flex flex-wrap gap-6 items-start">
      <div class="flex flex-col gap-6 min-w-0" style="flex: 999 1 560px">
      <section v-if="!t.pause" class="k-card min-w-0" style="padding-bottom: 8px" aria-labelledby="plan-h">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="plan-h" class="k-h2">Lernblock 09:00–11:30</h2>
          <p class="k-small m-0">
            <template v-if="isPreview">Vorschau: {{ planInfo.weekday }}, Woche {{ planInfo.week }} · {{ planInfo.theme }}</template>
            <template v-else>Mo–Fr · {{ t.done.length }} von {{ t.block.filter((x) => x.kind !== 'pause').length }} erledigt · Phase {{ t.phase || '2A' }}</template>
          </p>
        </div>

        <div role="img" :aria-label="timelineLabel" class="my-4" data-testid="timeline">
          <div class="hb-track">
            <div
              v-for="b in layout.items"
              :key="b.id"
              :title="`${b.start} ${kindLabel(b)} · ${b.minutes} min`"
              :class="['hb-seg', `hb-seg-${segState(b)}`, segWidthClass(b)]"
              :style="{ flex: `${b.minutes} 1 0` }"
              :data-state="segState(b)"
            >
              <span v-if="b.kind !== 'pause'" class="hb-seg-label">{{ segState(b) === 'done' ? '✓ ' : '' }}{{ shortLabel(b) }}</span>
            </div>
            <div v-if="marker != null" class="hb-now" :style="{ left: marker + '%' }"></div>
          </div>
          <div class="relative k-hint" style="height: 18px; margin-top: 6px">
            <span class="absolute left-0">09:00</span>
            <span class="absolute" style="left: 40%; margin-left: -18px">10:00</span>
            <span class="absolute hb-hide-sm" style="left: 80%; margin-left: -18px">11:00</span>
            <span class="absolute right-0">11:30</span>
          </div>
        </div>

        <ol class="list-none m-0 p-0">
          <li v-for="b in t.block" :key="b.id" class="hb-row" :data-testid="`block-${b.id}`">
            <div class="hb-time" :class="{ 'hb-muted': isDone(b) }">{{ b.start }}<span>{{ b.minutes }} min</span></div>
            <div class="min-w-0">
              <p class="hb-kind"><span :class="['hb-dot', `hb-seg-${segState(b)}`]"></span>{{ kindLabel(b) }}<span v-if="segState(b) === 'current'" class="hb-now-tag">· jetzt</span></p>
              <p class="hb-title" :class="{ 'hb-strike': isDone(b) }" :data-testid="`assign-${b.id}`">{{ assignment(b) ? itemLine(assignment(b)) : b.kind === 'pruefung' && planInfo?.exam ? planInfo.exam.title : b.title }}</p>
              <p v-if="assignment(b) && (assignment(b).source || assignment(b).origin === 'ai' || assignment(b).detail)" class="k-hint m-0 mt-0.5 flex flex-wrap items-center gap-x-2">
                <OriginBadge :origin="assignment(b).origin" :source="assignment(b).source" />
                <span v-if="assignment(b).detail" :class="{ 'hb-todo-text': assignment(b).status === 'todo' }">{{ assignment(b).status === 'todo' ? '→ ' : '' }}{{ assignment(b).detail }}</span>
              </p>
              <p class="k-small m-0 mt-0.5">{{ describe(b) }}</p>
              <p v-if="assignment(b)?.mode?.why" class="k-small m-0 mt-1 hb-mode" :data-testid="`mode-${b.id}`">{{ assignment(b).mode.why }}</p>
              <ol v-if="assignment(b)?.links?.length" class="m-0 mt-1 pl-5 k-small flex flex-col gap-0.5" style="list-style: decimal" :data-testid="`links-${b.id}`">
                <li v-for="l in assignment(b).links" :key="l.url"><a :href="l.url" target="_blank" rel="noopener">{{ l.title }}</a></li>
              </ol>
              <router-link v-if="b.kind === 'karten' && t.mineable" to="/satz-check#minen" class="k-small" style="font-weight: 600" data-testid="heute-mineable">{{ t.mineable }} {{ t.mineable === 1 ? 'Satz' : 'Sätze' }} aus dem Satz-Check minen →</router-link>
              <p v-if="logged(b) && !isPreview" class="k-hint m-0 mt-0.5">{{ logged(b) }} min erfasst</p>
              <RateAsk v-if="!isPreview && assignment(b)?.ask" :label="assignment(b).rateLabel" :share="shareLine(assignment(b).share)" :busy="rating === assignment(b).rateItem" @rate="(p) => rate(b, p)" />
              <p v-else-if="!isPreview && assignment(b)?.rating" class="k-hint m-0 mt-0.5" :data-testid="`rated-${b.id}`">{{ ratingLabel(assignment(b).rating) }}</p>
              <div v-for="(n, i) in assignment(b)?.then ?? []" :key="i" class="hb-then" :data-testid="`then-${b.id}-${i}`">
                <p class="hb-then-title"><span class="hb-then-label">Danach</span>{{ itemLine(n) }}</p>
                <p v-if="n.source || n.origin === 'ai' || n.detail" class="k-hint m-0 mt-0.5 flex flex-wrap items-center gap-x-2">
                  <OriginBadge :origin="n.origin" :source="n.source" />
                  <span v-if="n.detail" :class="{ 'hb-todo-text': n.status === 'todo' }">{{ n.status === 'todo' ? '→ ' : '' }}{{ n.detail }}</span>
                </p>
                <p v-if="n.text" class="k-small m-0 mt-0.5">{{ n.text }}</p>
                <p v-if="n.mode?.why" class="k-small m-0 mt-1 hb-mode">{{ n.mode.why }}</p>
                <ol v-if="n.links?.length" class="m-0 mt-1 pl-5 k-small flex flex-col gap-0.5" style="list-style: decimal" :data-testid="`links-${b.id}-${i}`">
                  <li v-for="l in n.links" :key="l.url"><a :href="l.url" target="_blank" rel="noopener">{{ l.title }}</a></li>
                </ol>
                <button v-if="!isPreview && (n.start?.href || n.start?.to)" class="k-btn k-btn-ghost k-btn-sm mt-1.5" :data-testid="`open-${b.id}-${i}`" @click="openThen(b, n)">{{ n.start.href ? 'Öffnen ↗' : 'Öffnen →' }}</button>
                <RateAsk v-if="!isPreview && n.ask" :label="n.rateLabel" :share="shareLine(n.share)" :busy="rating === n.rateItem" @rate="(p) => rate(b, p, n)" />
                <p v-else-if="!isPreview && n.rating" class="k-hint m-0 mt-0.5" :data-testid="`rated-${b.id}-${i}`">{{ ratingLabel(n.rating) }}</p>
              </div>
            </div>
            <div v-if="isPreview && b.kind !== 'pause'" class="hb-actions flex flex-col items-end gap-1.5">
              <span class="k-tip">
                <button
                  class="k-btn k-btn-sm"
                  aria-disabled="true"
                  :aria-describedby="`tip-${b.id}`"
                  :data-testid="`start-${b.id}`"
                  @click.prevent
                  @keydown.esc="$event.target.blur()"
                >Starten</button>
                <span :id="`tip-${b.id}`" role="tooltip" class="k-tip-bubble" :data-testid="`tip-${b.id}`">{{ hint }}</span>
              </span>
              <router-link v-if="b.kind === 'pruefung' && planInfo?.exam" :to="`/aufgabe/${planInfo.exam.id}`" class="k-btn k-btn-ghost k-btn-sm">Ansehen</router-link>
            </div>
            <div v-else-if="b.kind !== 'pause'" class="hb-actions flex flex-col items-end gap-1.5">
              <button v-if="isRunning(b)" class="k-btn k-btn-sm" :data-testid="`stop-${b.id}`" @click="stop">■ {{ formatClock(runningFor) }}</button>
              <button
                v-else-if="!isDone(b)"
                :class="['k-btn k-btn-sm', { 'k-btn-ghost': segState(b) !== 'current' }]"
                :data-testid="`start-${b.id}`"
                @click="start(b)"
              >Starten</button>
              <button
                :class="isDone(b) ? 'k-chip k-chip-success hb-chipbtn' : 'k-btn k-btn-ghost k-btn-sm'"
                :data-testid="`done-${b.id}`"
                @click="toggleDone(b)"
              >{{ isDone(b) ? '✓ Erledigt' : 'Fertig' }}</button>
            </div>
          </li>
        </ol>
        <div class="hb-after" data-testid="feed-row">
          <div class="hb-after-label">Nach dem Block</div>
          <div class="min-w-0">
            <p class="hb-kind" style="color: var(--text-2)"><span class="hb-dot" style="background: var(--chart-passive)"></span>Passiv · optional</p>
            <p class="hb-title" style="font-size: 16px">Wiederhören-Feed · {{ feed ? feed.episodes.length : 0 }} {{ feed && feed.episodes.length === 1 ? 'Folge' : 'Folgen' }}</p>
            <p class="k-small m-0 mt-0.5">Audio von allem, was du diese Woche gelesen und gelernt hast — als Podcast fürs Handy (im Tailnet): <code class="hb-url">{{ feedUrl }}</code></p>
          </div>
          <button class="k-btn k-btn-ghost k-btn-sm" @click="copyFeed">{{ copied ? '✓ Kopiert' : 'Link kopieren' }}</button>
        </div>
      </section>
      <MaterialsCard v-if="!t.pause" :blocks="t.block" :data="mat" />
      <DueSoon v-if="mat" :notices="mat.notices" :today="mat.today.date" @changed="loadMaterials" />
      </div>

      <div class="flex flex-col gap-6 min-w-0" style="flex: 1 1 340px">
        <section class="k-card" aria-labelledby="kask-h">
          <div class="flex items-baseline justify-between gap-2">
            <h2 id="kask-h" class="k-h2" style="font-size: 18px">Deine Kaskade</h2>
            <router-link to="/fahrplan" class="k-small" style="font-weight: 600">Fahrplan</router-link>
          </div>
          <p class="k-small m-0 mt-1.5 mb-4">Fähigkeiten wachsen nacheinander: erst Lesen, dann Hören, dann Sprechen, dann Genauigkeit.</p>
          <p v-if="!skills" class="k-small m-0">Noch keine Einstufung. <router-link to="/einstufung">Jetzt starten</router-link></p>
          <div v-else class="grid items-center gap-x-2.5 gap-y-1.5" style="grid-template-columns: 78px minmax(0, 1fr) 40px">
            <span></span>
            <div class="grid grid-cols-5 text-center k-hint" style="font-size: 11px; font-weight: 700"><span>A1</span><span>A2</span><span>B1</span><span>B2</span><span>C1</span></div>
            <span></span>
            <template v-for="s in SKILLS" :key="s.key">
              <span style="font-size: 14px; font-weight: 700">{{ s.label }}</span>
              <div class="relative" style="height: 12px; background: var(--surface-2); border-radius: 6px" :title="`${s.label}: ${skills[s.key] || 'noch offen'} · Ziel Phase 2: ${PHASE2_TARGET[s.key]}`">
                <div class="absolute inset-y-0 left-0" :style="{ width: levelToPct(skills[s.key]) + '%', background: 'var(--primary)', borderRadius: '6px' }"></div>
                <div class="hb-target" :style="{ left: levelToPct(PHASE2_TARGET[s.key]) + '%' }"></div>
              </div>
              <span class="text-right" style="font-size: 14px; font-weight: 700">{{ skills[s.key] || '—' }}</span>
            </template>
          </div>
          <p class="k-small m-0 mt-4 pt-3.5" style="border-top: 1px solid var(--surface-2)">
            <template v-if="t.satzcheck">Nächster <router-link to="/satz-check" style="font-weight: 700">Satz-Check</router-link>: {{ formatDate(nextSatzcheck) }} · zuletzt {{ coverageLabel(t.satzcheck) }}, Tor zu 2B: 80 %</template>
            <template v-else>Noch kein <router-link to="/satz-check" style="font-weight: 700">Satz-Check</router-link> — einmal im Monat.</template>
          </p>
        </section>

        <section class="k-card" aria-labelledby="imm-h">
          <h2 id="imm-h" class="k-h2" style="font-size: 18px">Immersion</h2>
          <div class="flex flex-wrap items-baseline gap-2.5 mt-2.5">
            <span style="font-size: 40px; font-weight: 800; letter-spacing: -0.02em">≈ {{ formatNumber(t.immersion.hours) }} h</span>
            <span class="k-small">von ≈ 1.150 h bis B2 · Start aus Einstufung</span>
          </div>
          <div class="k-progress mt-2" style="height: 8px" role="img" :aria-label="`${Math.round(t.immersion.share * 100)} Prozent der Stunden bis B2`">
            <div :style="{ width: t.immersion.share * 100 + '%' }"></div>
          </div>
          <p class="m-0 mt-5 mb-2 k-small" style="font-weight: 700">Diese Woche · {{ hours(activeH + passiveH) }} h <span style="font-weight: 500">· {{ weekOff ? 'freie Woche' : 'Block-Ziel 11,7 h aktiv' }}</span></p>
          <p v-if="activeH + passiveH === 0 && !anyFree" class="k-small m-0" data-testid="heute-hours-empty">{{ NO_HOURS_YET }}</p>
          <template v-else>
          <div class="grid grid-cols-7 gap-2 items-end" style="height: 120px; border-bottom: 1px solid var(--border-strong)" role="img" aria-label="Stunden pro Tag diese Woche, aktiv und passiv">
            <div
              v-for="(b, i) in bars"
              :key="i"
              class="flex flex-col gap-0.5"
              :title="`${WEEKDAYS[i]}: ${isFree(i) ? 'frei · ' : ''}${hours(t.weekTotals.seconds[i] / 3600)} h aktiv · ${hours(t.weekTotals.passive[i] / 3600)} h passiv`"
            >
              <span v-if="isFree(i) && !b.aktiv && !b.passiv" class="hb-free" :data-testid="`free-${i}`">frei</span>
              <div v-if="b.passiv" :style="{ height: b.passiv + 'px', background: 'var(--chart-passive)', borderRadius: '4px 4px 0 0' }"></div>
              <div v-if="b.aktiv" :style="{ height: b.aktiv + 'px', background: 'var(--chart-active)', borderRadius: b.passiv ? '0' : '4px 4px 0 0' }"></div>
            </div>
          </div>
          <div class="grid grid-cols-7 gap-2 mt-1.5 text-center k-hint">
            <span v-for="(d, i) in WEEKDAYS" :key="d" :style="i === todayIndex ? { fontWeight: 800, color: 'var(--text)' } : {}">{{ d }}</span>
          </div>
          </template>
          <div class="flex flex-wrap gap-x-4 gap-y-2 mt-3.5 k-small">
            <span class="inline-flex items-center gap-1.5"><span class="hb-sw" style="background: var(--chart-active)"></span>Aktiv <strong style="color: var(--text)">{{ hours(activeH) }} h</strong></span>
            <span class="inline-flex items-center gap-1.5"><span class="hb-sw" style="background: var(--chart-passive)"></span>Passiv <strong style="color: var(--text)">{{ hours(passiveH) }} h</strong></span>
            <button class="k-btn k-btn-ghost k-btn-sm ml-auto" data-testid="imm-toggle" @click="showForm = !showForm">{{ showForm ? 'Schließen' : '+ Eintragen' }}</button>
          </div>
          <div v-if="showForm" class="mt-3 pt-3" style="border-top: 1px solid var(--surface-2)">
            <ImmersionForm :today="t.date" @saved="showForm = false; load()" />
          </div>
          <p class="k-hint m-0 mt-3">Block-Timer zählen automatisch. Alles andere (Serien, Podcasts, Gespräche) hier eintragen. <router-link to="/immersion">Alle Einträge</router-link></p>
        </section>

        <div class="grid grid-cols-2 gap-4">
          <div class="k-card" style="padding: 18px">
            <p class="k-small m-0" style="font-weight: 700">Wörter bekannt</p>
            <p class="m-0 mt-1.5" style="font-size: 28px; font-weight: 800">{{ t.vocab ? '≈ ' + formatNumber(t.vocab.estimate) : '—' }}</p>
            <p class="k-small m-0 mt-0.5">aus dem Wortschatz-Test</p>
          </div>
          <div class="k-card" style="padding: 18px">
            <p class="k-small m-0" style="font-weight: 700">Kernwörter</p>
            <p class="m-0 mt-1.5" style="font-size: 28px; font-weight: 800">{{ formatNumber(t.cards.known + t.cards.learning) }}</p>
            <p class="k-small m-0 mt-0.5">von {{ formatNumber(t.cards.deckSize) }} · {{ t.cards.known }} kenne ich</p>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>

<style scoped>
/* Timeline: segments coloured by state (upcoming / current / done / pause), labelled, no opacity tricks. */
.hb-track { position: relative; display: flex; gap: 3px; height: 32px; container-type: inline-size; }
.hb-seg {
  display: flex;
  align-items: center;
  min-width: 0;
  padding: 0 8px;
  overflow: hidden;
  border: 1px solid var(--timeline-upcoming-border);
  border-radius: min(var(--radius-sm), 6px);
  background: var(--timeline-upcoming);
  color: var(--timeline-text);
}
.hb-seg-current { background: var(--timeline-current); border-color: var(--timeline-current-border); color: var(--timeline-current-text); }
.hb-seg-done { background: var(--timeline-done); border-color: var(--timeline-done); color: var(--timeline-done-text); }
.hb-seg-pause {
  border: 1px dashed var(--timeline-pause-line);
  background: repeating-linear-gradient(-45deg, var(--timeline-pause) 0 5px, var(--timeline-pause-line) 5px 6px);
}
.hb-seg-label { font-size: 12px; font-weight: 700; line-height: 1; white-space: nowrap; }
@container (max-width: 520px) { .hb-w-s .hb-seg-label { display: none; } }
@container (max-width: 340px) { .hb-w-m .hb-seg-label { display: none; } }
.hb-now { position: absolute; top: -6px; bottom: -6px; border-left: 3px solid var(--text); }
.hb-now-tag { color: var(--text); text-transform: none; letter-spacing: 0; }
.hb-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 16px 0;
  border-top: 1px solid var(--surface-2);
}
.hb-time { font-size: 17px; font-weight: 800; }
.hb-time span { display: block; font-size: 12px; font-weight: 500; color: var(--muted); }
.hb-muted { color: var(--muted); }
.hb-kind {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.hb-dot { width: 10px; height: 10px; flex: none; border-radius: 2px; }
.hb-dot.hb-seg-upcoming { background: var(--timeline-upcoming); border: 1px solid var(--timeline-upcoming-border); }
.hb-dot.hb-seg-current { background: var(--timeline-current); border: 1px solid var(--timeline-current-border); }
.hb-dot.hb-seg-done { background: var(--timeline-done-text); }
.hb-title { margin: 3px 0 0; font-size: 17px; font-weight: 700; }
.hb-strike { text-decoration: line-through; color: var(--muted); }
.hb-todo-text { color: var(--text); font-weight: 600; }
.hb-mode { color: var(--text); font-weight: 600; }
.hb-then { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border); }
.hb-then-title { margin: 0; font-size: 16px; font-weight: 700; color: var(--text); }
.hb-then-label { margin-right: 8px; font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.hb-chipbtn { border: 0; cursor: pointer; font: inherit; font-size: 13px; font-weight: 700; }
.hb-after {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  margin: 8px 0 16px;
  padding: 16px;
  background: var(--callout);
  border-radius: var(--radius-sm);
}
.hb-after-label { font-size: 13px; font-weight: 800; color: var(--text-2); }
.hb-url { font-size: 13px; word-break: break-all; }
.hb-sw { width: 10px; height: 10px; border-radius: 3px; }
.hb-free { margin-top: auto; padding-bottom: 4px; text-align: center; font-size: 11px; font-weight: 700; color: var(--muted); }
.hb-target {
  position: absolute;
  top: -5px;
  width: 6px;
  height: 22px;
  margin-left: -3px;
  background: var(--surface);
  border: 2px solid var(--text);
  border-radius: 2px;
}
@media (max-width: 480px) {
  .hb-row { grid-template-columns: 52px minmax(0, 1fr); }
  .hb-after { grid-template-columns: minmax(0, 1fr); }
  .hb-actions { grid-column: 1 / -1; flex-direction: row !important; justify-content: flex-start; }
  .hb-hide-sm { display: none; }
}
</style>
