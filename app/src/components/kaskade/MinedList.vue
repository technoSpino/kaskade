<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { cardWords } from '../../lib/cards'
import AiMark from './AiMark.vue'
import MinedEditor from './MinedEditor.vue'

// All mined sentences in Karten (#19): check what the KI filled in, edit or delete any card.
const emit = defineEmits(['changed'])
const cards = ref(null)
const open = ref(null) // id of the card in the editor
const all = ref(false)
const SHOWN = 8

async function reload() {
  try {
    cards.value = await api.get('/mined')
  } catch {
    cards.value = null
  }
}
onMounted(reload)
defineExpose({ reload })

const shown = computed(() => (all.value ? cards.value : cards.value?.slice(0, SHOWN)) ?? [])
const unchecked = computed(() => (cards.value ?? []).filter((c) => cardWords(c).some((w) => w.ai?.length)).length)

function saved(c) {
  cards.value = cards.value.map((x) => (x.id === c.id ? c : x))
  open.value = null
  emit('changed', { id: c.id, card: c })
}
function deleted(c) {
  cards.value = cards.value.filter((x) => x.id !== c.id)
  open.value = null
  emit('changed', { id: c.id, deleted: true })
}
</script>

<template>
  <section v-if="cards?.length" class="k-card" aria-labelledby="mined-h" data-testid="mined-list">
    <h2 id="mined-h" class="k-h2" style="font-size: 17px">Deine geminten Sätze ({{ cards.length }})</h2>
    <p v-if="unchecked" class="k-small m-0 mt-1">„KI“ = von einer KI ergänzt, weil das Wörterbuch das Wort nicht kannte. Kurz prüfen — falsch? Bearbeiten.</p>
    <ul class="list-none m-0 mt-2 p-0">
      <li v-for="c in shown" :key="c.id" class="ml-row" :data-testid="`mined-${c.id}`">
        <MinedEditor v-if="open === c.id" :card="c" @saved="saved" @deleted="deleted" @cancel="open = null" />
        <template v-else>
          <p class="m-0 k-small ml-sentence">„{{ c.sentence }}“</p>
          <p v-for="w in cardWords(c)" :key="w.target" class="m-0 mt-1 flex flex-wrap items-center gap-1.5 text-sm">
            <span v-if="w.case" :class="['k-case', `k-case-${w.case}`]" :aria-label="`Kasus ${w.case}`">{{ w.case }}</span>
            <span class="inline-flex items-center gap-1.5"><strong>{{ w.display }}</strong><AiMark v-if="w.ai?.includes('lemma')" field="lemma" /></span>
            <span class="inline-flex items-center gap-1.5" style="color: var(--text-2)">· {{ w.gloss }}<AiMark v-if="w.ai?.includes('gloss')" field="gloss" /><AiMark v-if="w.ai?.includes('case')" field="case" /></span>
          </p>
          <button type="button" class="ml-edit" :data-testid="`mined-edit-${c.id}`" @click="open = c.id">Bearbeiten</button>
        </template>
      </li>
    </ul>
    <button v-if="cards.length > SHOWN" type="button" class="ml-edit mt-2" @click="all = !all">{{ all ? 'Weniger zeigen' : `Alle ${cards.length} zeigen` }}</button>
  </section>
</template>

<style scoped>
.ml-row { padding: 10px 0; border-top: 1px solid var(--surface-2); }
.ml-row:first-child { border-top: 0; }
.ml-sentence { color: var(--text); font-family: var(--font-read); }
.ml-edit {
  margin-top: 4px; padding: 0; border: 0; background: none; cursor: pointer;
  font: inherit; font-size: 13px; font-weight: 700; color: var(--primary);
  text-decoration: underline; text-underline-offset: 2px;
}
</style>
