<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { bookLine, dueFor, dueLabel } from '../../lib/materials'
import { formatDate, formatDecimal, formatNumber } from '../../lib/format'
import { byBlock, shortDate, TOO_HARD } from '../../lib/ratings'
import WeeksChart from '../../components/kaskade/WeeksChart.vue'
import PauseWeek from '../../components/kaskade/PauseWeek.vue'

const f = ref(null)
const r = ref(null) // #23/#24: ratings per block and how each book is read
const error = ref(null)

async function load() {
  api.get('/ratings').then((x) => { r.value = x }).catch(() => { r.value = null })
  try {
    f.value = await api.get('/fahrplan')
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)
const groups = computed(() => (r.value ? byBlock(r.value.ratings) : []))
const anyRating = computed(() => groups.value.some((g) => g.rows.length))

const month = (iso) => (iso ? new Intl.DateTimeFormat('de-DE', { month: 'short', year: 'numeric' }).format(new Date(iso)) : '—')
const currentPhase = computed(() => (f.value?.phase || '2A').charAt(0))
const youPct = computed(() => (f.value ? Math.min(100, (f.value.hours / f.value.target) * 100) : 0))
const phaseFill = (p) => {
  if (!f.value) return 0
  return Math.max(0, Math.min(100, ((f.value.hours - p.from) / (p.to - p.from)) * 100))
}

const PHASES = [
  { n: '1', title: 'Fundament', goal: 'Ziel: Lesen A2', items: ['Grundwortschatz, Aussprache', 'Grundgrammatik als Vorbereitung'], app: 'Die Grammatik-Seiten unter „Nachschlagen“.' },
  { n: '2', title: 'Verständnis', goal: 'Ziel: Lesen B1 · Serien mit Untertiteln folgen', items: ['2A Die 2.000 häufigsten Wörter', '2B Verstehen durch Satz-Mining', '2C Freies Lesen ohne Tools'], app: 'Karten mit dem Kernwortschatz, Satz-Check, Lernblock mit Lesen und Schauen.' },
  { n: '3', title: 'Hören', goal: 'Ziel: Hören B1–B2 · TV ohne Untertitel', items: ['3A Die Hörlücke schließen', '3B Dialekt wählen', '3C Transkribieren, Loops', '3D Echte Gespräche verstehen'], app: 'Kommt später: Hören mit Loop und Diktat.' },
  { n: '4', title: 'Sprechen', goal: 'Ziel: Sprechen B1 · erst Komfort, dann Genauigkeit', items: ['4A Chorusing, laut lesen, Monolog', '4B Viel sprechen, Fehler erlaubt', '4X Situationen: Amt, Arzt, Wohnung'], app: 'Kommt später: Sprechpartner und Shadowing.' },
  { n: '5', title: 'Genauigkeit', goal: 'Ziel: B2 in allen vier Fähigkeiten', items: ['5A Schreib-Komfort', '5B Schreib-Genauigkeit', '5C Sprech-Genauigkeit'], app: 'Kommt später: Tagebuch mit Korrektur, Prüfungsformat.' }
]
const GOALS = [
  ['1 Fundament', 'A2', 'A1', 'A1', 'A1'],
  ['2 Verständnis', 'B1', 'A2', 'A1', 'A1'],
  ['3 Hören', 'B2', 'B1', 'A1', 'A2'],
  ['4 Sprechen', 'B2', 'B2', 'A2', 'B1'],
  ['5 Genauigkeit', 'C1', 'B2', 'B2', 'B2']
]
</script>

<template>
  <main class="k-main" data-testid="fahrplan">
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
    <div class="flex flex-wrap gap-6 items-stretch">
      <div class="min-w-0" style="flex: 999 1 560px">
        <p class="k-eyebrow mb-1.5">Dein Fahrplan</p>
        <h1 class="k-h1">Von B1 nach B2</h1>
        <p class="k-lead">Die Fähigkeiten kommen nacheinander, wie eine Kaskade: <strong style="color: var(--text)">Lesen → Hören → Sprechen → Genauigkeit</strong>. Dein B1.2-Kurs hat Grammatik und Grundwortschatz gelegt. Jetzt fehlt vor allem viel echter Input in normalem Tempo — dadurch wird aus Gelerntem Verstandenes.</p>
      </div>
      <section v-if="f" class="fp-dark min-w-0" style="flex: 1 1 340px" aria-labelledby="prog-h">
        <h2 id="prog-h" class="fp-dark-label">Prognose B2</h2>
        <p class="m-0 mt-2" style="font-size: 15px">Block Mo–Fr 09:00–11:30 = <strong>{{ formatDecimal(f.forecast.blockPerWeek) }} h aktiv pro Woche</strong></p>
        <div class="grid grid-cols-2 gap-3 mt-4">
          <div class="fp-tile">
            <p class="m-0" style="font-size: 13px">Nur der Block</p>
            <p class="m-0 mt-1" style="font-size: 24px; font-weight: 800">≈ {{ month(f.forecast.block) }}</p>
          </div>
          <div class="fp-tile fp-tile-accent">
            <p class="m-0" style="font-size: 13px; font-weight: 600">+ 48 min passiv, Mo–Fr</p>
            <p class="m-0 mt-1" style="font-size: 24px; font-weight: 800">≈ {{ month(f.forecast.blockPassive) }}</p>
          </div>
        </div>
        <p class="m-0 mt-3.5" style="font-size: 13px; line-height: 1.5">
          Basis: ≈ {{ formatNumber(f.hours) }} h (Einstufung + gemessene Zeit), Refold-Schätzung ≈ 1.150 h bis B2.
          <template v-if="f.forecast.measured"> Bei deinem Tempo der letzten 4 Wochen ({{ formatDecimal(f.forecast.measuredPerWeek) }} h/Woche): ≈ {{ month(f.forecast.measured) }}.</template>
        </p>
      </section>
    </div>

    <section v-if="f" class="k-card" aria-labelledby="track-h">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="track-h" class="k-h2">Stunden bis B2</h2>
        <p class="k-small m-0"><strong style="color: var(--text)">≈ {{ formatNumber(f.hours) }} h</strong> von ≈ 1.150 h</p>
      </div>
      <div class="relative" style="margin-top: 40px">
        <div class="fp-you-label" :style="{ left: youPct + '%' }">Du: ≈ {{ formatNumber(f.hours) }} h</div>
        <div class="fp-you-line" :style="{ left: youPct + '%' }"></div>
        <div class="flex gap-0.5" style="height: 36px">
          <div
            v-for="p in f.phases"
            :key="p.name"
            :title="`Phase ${p.name} · ${p.from}–${p.to} h`"
            class="fp-seg"
            :style="{ flex: `${p.to - p.from} 1 0` }"
          ><div class="fp-fill" :style="{ width: phaseFill(p) + '%' }"></div></div>
        </div>
        <div class="flex gap-0.5 mt-2 k-small" style="font-size: 12px; font-weight: 700">
          <div v-for="p in f.phases" :key="p.name" class="min-w-0" :style="{ flex: `${p.to - p.from} 1 0` }">{{ p.name }}</div>
        </div>
      </div>
      <h3 class="k-h2 mt-8 mb-6" style="font-size: 16px">Stunden pro Woche · aktiv + passiv · <router-link to="/immersion" style="font-weight: 600">eintragen</router-link></h3>
      <WeeksChart :weeks="f.weeks" />
    </section>

    <section v-if="r" class="k-card" aria-labelledby="rate-h" data-testid="fp-ratings">
      <h2 id="rate-h" class="k-h2">Wie viel verstanden?</h2>
      <p class="k-small m-0 mt-1.5">Deine Einschätzung nach jedem Block. Unter {{ TOO_HARD }} % ist es zu schwer — bei Büchern passt Kaskade den Plan selbst an, Clips und Podcasts werden markiert.</p>
      <p v-if="!anyRating" class="k-small m-0 mt-3" data-testid="fp-ratings-empty">Noch keine Einschätzung — nach jedem Schauen- und Lesen-Block fragt Kaskade: „Wie viel hast du verstanden?“</p>
      <div v-else class="grid gap-5 mt-4" style="grid-template-columns: repeat(auto-fit, minmax(260px, 1fr))">
        <div v-for="g in groups" :key="g.block" class="min-w-0" :data-testid="`fp-ratings-${g.block}`">
          <h3 class="fp-rate-h">{{ g.title }}<span v-if="g.avg != null" class="k-small" style="font-weight: 600"> · Ø {{ g.avg }} % (letzte {{ Math.min(5, g.rows.length) }})</span></h3>
          <p v-if="!g.rows.length" class="k-small m-0">Noch keine Einschätzung.</p>
          <template v-else>
            <div class="fp-trend" role="img" :aria-label="`Verlauf ${g.title}: ${g.rows.slice(0, 10).reverse().map((x) => x.pct + ' %').join(', ')}`">
              <span v-for="x in g.rows.slice(0, 10).reverse()" :key="x.id" class="fp-trend-bar" :class="{ 'fp-trend-low': x.pct < TOO_HARD }" :style="{ height: x.pct * 0.4 + 'px' }" :title="`${shortDate(x.date)}: ${x.pct} %`"></span>
            </div>
            <ol class="list-none m-0 mt-2 p-0 flex flex-col gap-1">
              <li v-for="x in g.rows.slice(0, 5)" :key="x.id" class="fp-rate-row k-small">
                <span class="min-w-0">{{ shortDate(x.date) }} · {{ x.label }}</span>
                <strong :style="{ color: 'var(--text)' }">{{ x.pct }} %{{ x.pct < TOO_HARD ? ' · zu schwer' : '' }}</strong>
              </li>
            </ol>
          </template>
        </div>
      </div>
      <template v-if="r.books.length">
        <h3 class="fp-rate-h mt-5">Bücher im Plan</h3>
        <ul class="list-none m-0 p-0 flex flex-col gap-1" data-testid="fp-books">
          <li v-for="b in r.books" :key="b.book" class="k-small" style="color: var(--text)">{{ b.why }}</li>
        </ul>
      </template>
    </section>

    <div class="grid gap-4" style="grid-template-columns: repeat(auto-fit, minmax(210px, 1fr))">
      <article v-for="p in PHASES" :key="p.n" class="k-card flex flex-col gap-2.5" :class="{ 'k-card-strong': p.n === currentPhase }" :data-testid="`phase-${p.n}`">
        <div class="flex items-center justify-between gap-2">
          <span class="k-eyebrow">Phase {{ p.n }}</span>
          <span v-if="p.n === currentPhase" class="k-chip k-chip-accent" style="font-size: 12px">Jetzt · {{ f?.phase || '2A' }}</span>
          <span v-else-if="p.n < currentPhase" class="k-chip k-chip-success" style="font-size: 12px">✓ Erledigt</span>
        </div>
        <h3 class="k-h2" style="font-size: 20px">{{ p.title }}</h3>
        <p class="k-small m-0" style="font-size: 13px">{{ p.goal }}</p>
        <ul class="m-0 list-disc pl-5 k-small" style="line-height: 1.5">
          <li v-for="it in p.items" :key="it">{{ it }}</li>
        </ul>
        <p class="k-small m-0 mt-auto pt-2.5" style="border-top: 1px solid var(--surface-2); font-size: 13px"><strong style="color: var(--text)">Im App:</strong> {{ p.app }}</p>
      </article>
    </div>

    <div class="flex flex-wrap gap-6 items-start">
      <section class="k-card min-w-0" style="flex: 999 1 560px" aria-labelledby="mat-h">
        <h2 id="mat-h" class="k-h2">Ziele pro Phase</h2>
        <p class="k-small m-0 mt-1.5 mb-3.5">Refold-Richtwerte (GER). Die Fähigkeiten wachsen ungleich — das ist gewollt.</p>
        <div style="overflow-x: auto">
          <table class="fp-table">
            <thead><tr><th scope="col">Phase</th><th scope="col">Lesen</th><th scope="col">Hören</th><th scope="col">Schreiben</th><th scope="col">Sprechen</th></tr></thead>
            <tbody>
              <tr v-for="row in GOALS" :key="row[0]" :class="{ 'fp-now': row[0].startsWith(currentPhase) }">
                <th scope="row">{{ row[0] }}{{ row[0].startsWith(currentPhase) ? ' · jetzt' : '' }}</th>
                <td v-for="(c, i) in row.slice(1)" :key="i">{{ c }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="k-card min-w-0" style="flex: 1 1 340px" aria-labelledby="chk-h">
        <h2 id="chk-h" class="k-h2">Einstufungs-Checks</h2>
        <p class="k-small m-0 mt-1.5 mb-4">Alle 4 Wochen ein <router-link to="/satz-check">Satz-Check</router-link> (Refolds Phasen-Tor, 5 min).</p>
        <ol v-if="f" class="list-none m-0 p-0 flex flex-col gap-2.5">
          <li class="fp-check fp-check-next">
            <span><strong>Nächster Satz-Check</strong><span class="block k-small" style="font-size: 13px">{{ f.nextCheck ? formatDate(f.nextCheck) : 'jetzt — noch keiner gemacht' }}</span></span>
            <router-link to="/satz-check" class="k-small self-center" style="font-weight: 700">Starten</router-link>
          </li>
          <li v-for="s in f.satzchecks" :key="s.date" class="fp-check">
            <span><strong style="color: var(--text)">Satz-Check</strong><span class="block" style="font-size: 13px">{{ formatDate(s.date) }} · {{ s.contentType === 'simple' ? 'einfach' : 'für Erwachsene' }}</span></span>
            <span class="self-center" style="font-weight: 700; color: var(--text)" :title="s.coverageAll != null ? `mit Geräusch-Zeilen ${s.coverageAll} %` : undefined">{{ s.coverage }} %<template v-if="s.coverageAll != null"><span class="block k-hint" style="font-weight: 500">vorher {{ s.coverageAll }} %</span></template></span>
          </li>
          <li v-for="p in f.placements" :key="p.id" class="fp-check">
            <span><router-link to="/einstufung" style="font-weight: 800">Einstufung</router-link><span class="block" style="font-size: 13px">{{ formatDate(p.date) }} · alle Fähigkeiten</span></span>
            <span class="self-center" style="font-weight: 700; color: var(--text)">Phase {{ p.phase }}{{ p.words ? ' · ' + formatNumber(p.words) + ' W.' : '' }}</span>
          </li>
          <li class="fp-check">
            <span><strong style="color: var(--text)">Intensivkurs B1.2</strong><span class="block" style="font-size: 13px">abgeschlossen · ohne Prüfung</span></span>
            <span class="self-center" style="font-weight: 700; color: var(--text)">B1.2</span>
          </li>
        </ol>
        <p class="k-small m-0 mt-4 pt-3.5" style="border-top: 1px solid var(--surface-2); font-size: 13px; color: var(--text)" data-testid="fp-exam">{{ f?.exam ?? 'B1-Prüfung: pausiert — kommt zurück, wenn du ein Prüfungsdatum wählst.' }}</p>
        <template v-if="f?.upcoming?.length || f?.notices?.length">
          <h3 class="k-h2 mt-6" style="font-size: 16px">Nächste Schritte</h3>
          <ol class="list-none m-0 mt-3 p-0 flex flex-col gap-2.5" data-testid="fp-upcoming">
            <li v-for="n in f.notices ?? []" :key="n.id" class="fp-check" :data-testid="`fp-notice-${n.id}`">
              <span>
                <strong style="color: var(--text)">{{ n.title }}</strong>
                <span class="block" style="font-size: 13px">{{ n.type === 'book' ? bookLine(n.book) : n.text }} · {{ dueFor(n) }}</span>
              </span>
              <span class="self-center k-small" style="font-weight: 700">{{ dueLabel(n.by, f.today ?? n.by).text }}</span>
            </li>
            <li v-for="u in f.upcoming" :key="u.id" class="fp-check">
              <span>
                <strong :class="{ 'fp-done': u.done }" style="color: var(--text)">{{ u.done ? '✓ ' : '' }}{{ u.title }}</strong>
                <span class="block" style="font-size: 13px">Woche {{ u.week }} · ab {{ formatDate(u.date) }}</span>
              </span>
              <span class="self-center k-small" style="font-weight: 700">{{ u.done ? 'erledigt' : u.week === 5 ? 'vorher' : 'geplant' }}</span>
            </li>
          </ol>
        </template>
      </section>
    </div>

    <!-- #36: a week off moves the plan back; the dates above follow it -->
    <PauseWeek @changed="load" />
  </main>
</template>

<style scoped>
.fp-done { text-decoration: line-through; }
.fp-rate-h { margin: 0 0 8px; font-size: 15px; font-weight: 800; color: var(--text); }
.fp-trend { display: flex; align-items: flex-end; gap: 4px; height: 40px; border-bottom: 1px solid var(--border-strong); }
.fp-trend-bar { width: 14px; border-radius: 3px 3px 0 0; background: var(--chart-active); }
.fp-trend-low { background: var(--chart-passive); }
.fp-rate-row { display: flex; justify-content: space-between; gap: 10px; }
.fp-dark { background: var(--nav-bg); color: var(--nav-text); border-radius: var(--radius-lg); padding: 22px 24px; box-shadow: var(--shadow); }
.fp-dark-label { margin: 0; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--nav-muted); }
.fp-dark p { color: var(--nav-muted); }
.fp-dark strong { color: var(--nav-text); }
.fp-tile { background: var(--nav-hover); border-radius: var(--radius-sm); padding: 14px; }
.fp-tile p { color: var(--nav-text) !important; }
.fp-tile-accent { background: var(--accent); }
.fp-tile-accent p { color: var(--accent-text) !important; }
.fp-seg { position: relative; overflow: hidden; background: var(--surface-2); }
.fp-seg:first-child { border-radius: min(var(--radius-sm), 6px) 0 0 min(var(--radius-sm), 6px); }
.fp-seg:last-child { border-radius: 0 min(var(--radius-sm), 6px) min(var(--radius-sm), 6px) 0; }
.fp-fill { position: absolute; inset: 0 auto 0 0; background: var(--timeline-current); box-shadow: inset 0 0 0 1px var(--timeline-current-border); }
.fp-you-label {
  position: absolute; top: -34px; transform: translateX(-50%); white-space: nowrap;
  font-size: 12px; font-weight: 800; background: var(--accent); color: var(--accent-text);
  padding: 3px 8px; border-radius: 6px;
}
.fp-you-line { position: absolute; top: -10px; bottom: -10px; border-left: 3px solid var(--text); z-index: 1; }
.fp-table { width: 100%; min-width: 440px; border-collapse: collapse; font-size: 15px; }
.fp-table th, .fp-table td { padding: 10px; text-align: left; border-bottom: 1px solid var(--surface-2); }
.fp-table thead th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; border-bottom-color: var(--border); }
.fp-table tbody th { color: var(--muted); font-weight: 600; }
.fp-now { background: var(--callout); }
.fp-now th, .fp-now td { color: var(--text) !important; font-weight: 800; }
.fp-check {
  display: flex; justify-content: space-between; gap: 12px; padding: 12px 14px;
  border: var(--border-width) solid var(--border); border-radius: var(--radius-sm); color: var(--text-2);
}
.fp-check-next { border: calc(var(--border-width) + 1px) solid var(--text); color: var(--text); }
</style>
