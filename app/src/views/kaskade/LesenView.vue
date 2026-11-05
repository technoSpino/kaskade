<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import OriginBadge from '../../components/kaskade/OriginBadge.vue'

const texts = ref([])
const error = ref(null)
const filter = ref('alle')

onMounted(async () => {
  try {
    texts.value = await api.get('/texts')
  } catch (e) {
    error.value = e.message
  }
})

const shown = computed(() => texts.value.filter((t) => filter.value === 'alle' || t.slot === filter.value))
const SLOT = { input: '09:30 · mit Hilfen', lesen: '10:35 · freies Lesen' }
</script>

<template>
  <main class="k-main" data-testid="lesen">
    <div>
      <p class="k-eyebrow mb-1.5">Bibliothek</p>
      <h1 class="k-h1">Lesen</h1>
      <p class="k-lead">Kurze Texte aus dem Alltag, fast nur aus den 2.000 häufigsten Wörtern gebaut. Lies mit Audio. Bei „mit Hilfen“ siehst du die neuen Wörter markiert, beim freien Lesen einfach weiterlesen, ohne nachzuschlagen.</p>
    </div>
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
    <div class="flex flex-wrap gap-2" role="group" aria-label="Filter">
      <router-link to="/lesen/eigener-text" class="k-btn k-btn-sm" data-testid="eigener-text-link">+ Eigener Text</router-link>
      <button v-for="f in ['alle', 'input', 'lesen']" :key="f" class="k-btn k-btn-sm" :class="{ 'k-btn-ghost': filter !== f }" @click="filter = f">
        {{ f === 'alle' ? 'Alle' : f === 'input' ? 'Mit Hilfen (09:30)' : 'Freies Lesen (10:35)' }}
      </button>
    </div>
    <p v-if="!texts.length && !error" class="k-small">Noch keine Texte.</p>
    <ul class="list-none m-0 p-0 grid gap-4" style="grid-template-columns: repeat(auto-fill, minmax(260px, 1fr))">
      <li v-for="t in shown" :key="t.id">
        <router-link :to="`/lesen/${t.id}`" class="k-card lb-card" :data-testid="`text-${t.id}`">
          <span class="k-eyebrow">{{ t.theme }} · {{ t.level }}</span>
          <span class="lb-title">{{ t.title }}</span>
          <span class="k-small">{{ SLOT[t.slot] }} · {{ t.words }} Wörter<template v-if="t.coverage != null"> · {{ Math.round(t.coverage * 100) }} % Kernwörter</template></span>
          <span class="flex flex-wrap items-center gap-2">
            <OriginBadge :origin="t.origin" :source="t.source" fallback="ai" />
            <span v-if="t.readAt" class="k-chip k-chip-success" style="width: fit-content">✓ gelesen</span>
          </span>
        </router-link>
      </li>
    </ul>
  </main>
</template>

<style scoped>
.lb-card { display: flex; flex-direction: column; gap: 6px; height: 100%; text-decoration: none; color: var(--text) !important; }
.lb-card:hover { border-color: var(--text); }
.lb-title { font-family: var(--font-read); font-size: 21px; font-weight: 600; line-height: 1.3; }
</style>
