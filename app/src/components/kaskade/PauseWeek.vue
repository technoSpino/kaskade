<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../../lib/api'
import { moveLines, weekLabel } from '../../lib/pauses'

// #36 "Woche frei nehmen": pick a Mon–Sun week, see what moves, take it off — undo while it hasn't started.
const emit = defineEmits(['changed'])
const view = ref(null)
const pick = ref('')
const preview = ref(null)
const error = ref(null)
const busy = ref(false)

onMounted(async () => {
  try {
    view.value = await api.get('/pauses')
  } catch (e) {
    error.value = e.message
  }
})

watch(pick, async (monday) => {
  preview.value = null
  error.value = null
  if (!monday) return
  try {
    preview.value = await api.get(`/pauses/preview?monday=${monday}`)
  } catch (e) {
    error.value = e.message
  }
})

async function change(call) {
  busy.value = true
  error.value = null
  try {
    view.value = await call()
    pick.value = ''
    emit('changed')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
const take = () => change(() => api.post('/pauses', { monday: pick.value }))
const undo = (p) => change(() => api.del(`/pauses/${p.from}`))
</script>

<template>
  <section class="k-card min-w-0" aria-labelledby="pause-h" data-testid="fp-pause">
    <h2 id="pause-h" class="k-h2" style="font-size: 18px">Woche frei nehmen</h2>
    <p class="k-small m-0 mt-1.5">Eine Woche Mo–So ohne Lernblock. Der ganze Plan rückt eine Woche nach hinten: Was du gerade schaust oder hörst, geht danach genau da weiter, wo du aufgehört hast. Karten bleiben offen, aber freiwillig.</p>
    <p v-if="error" class="k-error m-0 mt-2" role="alert">{{ error }}</p>
    <ul v-if="view?.pauses.length" class="list-none m-0 mt-3 p-0 flex flex-col gap-2" data-testid="fp-pauses">
      <li v-for="p in view.pauses" :key="p.from" class="pw-row" :data-testid="`fp-pause-${p.from}`">
        <span><strong style="color: var(--text)">Frei: {{ weekLabel(p) }}</strong></span>
        <button v-if="p.canUndo" class="k-btn k-btn-ghost k-btn-sm" :disabled="busy" :data-testid="`fp-pause-undo-${p.from}`" @click="undo(p)">Rückgängig</button>
        <span v-else class="k-small self-center">{{ p.from <= view.today && p.to >= view.today ? 'läuft' : 'vorbei' }}</span>
      </li>
    </ul>
    <label v-if="view" class="block mt-3">
      <span class="k-small" style="font-weight: 700; color: var(--text)">Welche Woche?</span>
      <select v-model="pick" class="k-input mt-1" data-testid="fp-pause-select">
        <option value="">Woche wählen …</option>
        <option v-for="o in view.options" :key="o.from" :value="o.from" :disabled="!!o.problem">{{ weekLabel(o) }}{{ o.problem ? ` — ${o.problem}` : '' }}</option>
      </select>
    </label>
    <div v-if="preview" class="pw-preview mt-3" data-testid="fp-pause-preview">
      <p class="m-0" style="font-weight: 700; color: var(--text)">Das verschiebt sich:</p>
      <ul class="m-0 mt-1.5 pl-5 k-small flex flex-col gap-1" style="list-style: disc">
        <li v-for="l in moveLines(preview)" :key="l">{{ l }}</li>
      </ul>
      <p class="k-small m-0 mt-2">Heute zeigt dann: „{{ preview.line }}“</p>
      <button class="k-btn k-btn-sm mt-3" :disabled="busy" data-testid="fp-pause-take" @click="take">{{ weekLabel(preview) }} frei nehmen</button>
    </div>
  </section>
</template>

<style scoped>
.pw-row {
  display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 14px;
  border: var(--border-width) solid var(--border); border-radius: var(--radius-sm);
}
.pw-preview { padding: 14px; background: var(--callout); border-radius: var(--radius-sm); }
</style>
