<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { formatDate } from '../../lib/format'
import ImmersionForm from '../../components/kaskade/ImmersionForm.vue'
import WeeksChart from '../../components/kaskade/WeeksChart.vue'

const data = ref(null)
const error = ref(null)

async function load() {
  try {
    data.value = await api.get('/immersion?days=60')
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)

async function remove(id) {
  try {
    await api.del(`/immersion/${id}`)
    await load()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <main class="k-main" data-testid="immersion">
    <div>
      <p class="k-eyebrow mb-1.5"><router-link to="/">Heute</router-link></p>
      <h1 class="k-h1">Immersion</h1>
      <p class="k-lead">Die Block-Timer zählen automatisch. Hier trägst du alles andere ein: Serien am Abend, Podcasts beim Kochen, Gespräche. <strong>Aktiv</strong> = konzentriert zuhören oder lesen, <strong>passiv</strong> = nebenbei.</p>
    </div>
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
    <div class="flex flex-wrap gap-6 items-start">
      <section class="k-card min-w-0" style="flex: 1 1 320px" aria-labelledby="new-h">
        <h2 id="new-h" class="k-h2 mb-3" style="font-size: 18px">Neuer Eintrag</h2>
        <ImmersionForm @saved="load" />
      </section>
      <section v-if="data" class="k-card min-w-0" style="flex: 999 1 480px" aria-labelledby="weeks-h">
        <h2 id="weeks-h" class="k-h2 mb-6" style="font-size: 18px">Letzte 8 Wochen</h2>
        <WeeksChart :weeks="data.weeks" />
      </section>
    </div>
    <section v-if="data" class="k-card" aria-labelledby="list-h">
      <h2 id="list-h" class="k-h2" style="font-size: 18px">Einträge (60 Tage)</h2>
      <p v-if="!data.entries.length" class="k-small m-0 mt-2">Noch keine Einträge.</p>
      <ul class="list-none m-0 mt-2 p-0">
        <li v-for="e in data.entries" :key="e.id" class="flex flex-wrap items-center justify-between gap-2 py-2.5" style="border-top: 1px solid var(--surface-2)">
          <span><strong>{{ e.title }}</strong><span class="k-hint block">{{ formatDate(e.date) }} · {{ e.minutes }} min · {{ e.kind }}</span></span>
          <button class="k-btn k-btn-ghost k-btn-sm" :aria-label="`${e.title} löschen`" @click="remove(e.id)">Löschen</button>
        </li>
      </ul>
    </section>
  </main>
</template>
