<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { KIND_LABEL, verdictLabel } from '../../lib/practice'
import OriginBadge from '../../components/kaskade/OriginBadge.vue'

const data = ref(null)
const prompts = ref([]) // the Schreiben/Sprechen tasks (#27: no longer in the daily plan, still here)
const error = ref(null)

onMounted(async () => {
  api.get('/plan').then((p) => { prompts.value = p.prompts ?? [] }).catch(() => { prompts.value = [] })
  try {
    data.value = await api.get('/practice')
  } catch (e) {
    error.value = e.message
  }
})

const MODULES = [
  { id: 'lesen', label: 'Lesen' },
  { id: 'hoeren', label: 'Hören' },
  { id: 'schreiben', label: 'Schreiben' }
]
const pct = (x) => (x == null ? '—' : `${Math.round(x * 100)} %`)
</script>

<template>
  <main class="k-main" data-testid="pruefung">
    <div>
      <p class="k-eyebrow mb-1.5">B1-Zertifikat</p>
      <h1 class="k-h1">Prüfungstraining</h1>
      <p class="k-lead">Eigene Übungen im Stil der B1-Prüfung (Goethe, telc, ÖSD ähneln sich). Keine echten Prüfungsaufgaben. Bestanden ist ein Teil ab <strong>60 %</strong>. Mit „auf Zeit“ läuft die Uhr wie in der Prüfung.</p>
      <p class="k-callout m-0 mt-3" data-testid="pruefung-paused"><strong>B1-Prüfung: pausiert</strong> — im Lernblock gibt es keinen Prüfungsteil, bis du ein Prüfungsdatum wählst. Alles hier bleibt zum freien Üben.</p>
    </div>
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>

    <template v-if="data">
      <section class="grid gap-4" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))" aria-label="Stand pro Modul">
        <div v-for="m in MODULES" :key="m.id" class="k-card" :data-testid="`ready-${m.id}`">
          <p class="k-eyebrow">{{ m.label }}</p>
          <p class="m-0 mt-1.5" style="font-size: 32px; font-weight: 800">{{ pct(data.readiness[m.id].average) }}</p>
          <p class="k-small m-0">{{ verdictLabel(data.readiness[m.id].average) }} · {{ data.readiness[m.id].attempts }} Versuche</p>
          <div class="pr-bar" role="img" :aria-label="`${pct(data.readiness[m.id].average)} von 60 % nötig`">
            <div :style="{ width: (data.readiness[m.id].average ?? 0) * 100 + '%' }"></div>
            <span class="pr-mark"></span>
          </div>
        </div>
        <div class="k-card">
          <p class="k-eyebrow">Sprechen</p>
          <p class="m-0 mt-1.5" style="font-size: 32px; font-weight: 800">—</p>
          <p class="k-small m-0">Aufgaben unten, mit Aufnahme. Bewertung kommt später.</p>
        </div>
      </section>

      <section v-for="m in MODULES" :key="m.id" class="k-card" :aria-labelledby="`h-${m.id}`">
        <h2 :id="`h-${m.id}`" class="k-h2">{{ m.label }}</h2>
        <ul class="list-none m-0 mt-3 p-0">
          <li v-for="it in data[m.id]" :key="it.id" class="pr-row">
            <span class="min-w-0">
              <router-link :to="`/pruefung/${m.id}/${it.id}`" style="font-weight: 700" :data-testid="`item-${it.id}`">{{ it.title }}</router-link>
              <span class="k-hint flex flex-wrap items-center gap-x-2 gap-y-1">{{ KIND_LABEL[it.kind] || it.kind }} · {{ it.minutes }} min <OriginBadge :origin="it.origin" :source="it.source" fallback="ai" /></span>
            </span>
            <span class="k-small" style="font-weight: 700; color: var(--text)">{{ it.last == null ? '' : pct(it.last) }}</span>
          </li>
        </ul>
        <p v-if="!data[m.id].length" class="k-small m-0 mt-2">Noch keine Aufgaben.</p>
      </section>

      <section v-if="prompts.length" class="k-card" aria-labelledby="h-aufgaben" data-testid="pruefung-aufgaben">
        <h2 id="h-aufgaben" class="k-h2">Schreiben und Sprechen · Aufgaben</h2>
        <ul class="list-none m-0 mt-3 p-0">
          <li v-for="p in prompts" :key="p.id" class="pr-row">
            <span class="min-w-0">
              <router-link :to="`/aufgabe/${p.id}`" style="font-weight: 700" :data-testid="`aufgabe-${p.id}`">{{ p.title }}</router-link>
              <span class="k-hint flex flex-wrap items-center gap-x-2 gap-y-1">{{ p.skill === 'sprechen' ? 'Sprechen' : 'Schreiben' }} · {{ p.type }} <OriginBadge :origin="p.origin" fallback="ai" /></span>
            </span>
          </li>
        </ul>
      </section>
    </template>
  </main>
</template>

<style scoped>
.pr-bar { position: relative; height: 10px; margin-top: 12px; background: var(--surface-2); border-radius: 5px; }
.pr-bar > div { height: 100%; background: var(--primary); border-radius: 5px; }
.pr-mark { position: absolute; left: 60%; top: -4px; bottom: -4px; border-left: 2px solid var(--text); }
.pr-row { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-top: 1px solid var(--surface-2); }
</style>
