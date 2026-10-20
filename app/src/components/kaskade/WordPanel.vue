<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../../lib/api'
import { sentenceOf } from '../../lib/reader'

// Details for a tapped word + "Satz minen" (creates a sentence card).
const props = defineProps({
  analysis: { type: Object, required: true },
  token: { type: Object, default: null },
  glossary: { type: Array, default: () => [] },
  source: { type: String, default: 'Lesen' },
  // A subtitle line is mined as a whole (not just the spaCy sentence around the word).
  sentence: { type: String, default: null },
  // Extra fields for the mine request (e.g. the clip and time range for an audio snippet).
  extra: { type: Object, default: null }
})
const emit = defineEmits(['mined'])

const mined = ref(null)
const error = ref(null)
const busy = ref(false)
const existing = ref(null) // "Satz schon gemint" with a different word: can go onto that card (#19)
watch(() => props.token, () => { mined.value = null; error.value = null; existing.value = null })
const AI_NAMES = { lemma: 'Grundform', gloss: 'Bedeutung', case: 'Kasus' }
const aiNote = (fields) => (fields?.length ? ` ${fields.map((f) => AI_NAMES[f]).join(', ')} von der KI ergänzt (KI) — in Karten prüfen.` : '')

const chunk = computed(() => (props.token?.chunk != null ? props.analysis.chunks[props.token.chunk] : null))
const authorGloss = computed(() => props.glossary.find((g) => g.term === props.token?.text))
const gloss = computed(() => authorGloss.value?.gloss ?? props.token?.entry?.gloss ?? null)
const display = computed(() => props.token?.entry?.display ?? props.token?.lemma)
const sentence = computed(() => props.sentence ?? (props.token ? sentenceOf(props.analysis, props.token.i) : ''))
const STATE = { neu: 'neu', lernend: 'am Lernen', bekannt: 'bekannt' }
// #34: the word marked on the card — for a separable verb its verb form, whichever half was tapped
const target = computed(() => props.token?.entry?.target ?? props.token?.text)

// Case only where the parser is sure (the analysis leaves out the rest): no badge beats a wrong one.
const body = () => ({
  sentence: sentence.value,
  target: target.value,
  lemma: props.token.entry?.lemma ?? props.token.lemma, // the dictionary's headword beats spaCy's guess
  display: display.value,
  gloss: gloss.value ?? '',
  note: chunk.value?.explain ?? authorGloss.value?.note ?? null,
  case: chunk.value?.case ?? null,
  source: props.source,
  ...(props.extra ?? {})
})

async function mine() {
  error.value = null
  existing.value = null
  busy.value = true
  try {
    const r = await api.post('/mined', body())
    if (r.duplicate) {
      mined.value = r.sameWord ? 'Satz schon gemint — das Wort ist schon auf der Karte.' : 'Satz schon gemint.'
      if (!r.sameWord) existing.value = r.id
    } else {
      mined.value = `Gemined — kommt als neue Karte.${aiNote(r.ai)}`
    }
    emit('mined', r)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function addWord() {
  error.value = null
  busy.value = true
  try {
    const card = await api.post(`/mined/${existing.value.split(':')[1]}/words`, body())
    const w = card.words.find((x) => x.target === target.value)
    mined.value = `„${target.value}“ steht jetzt mit auf der Karte.${aiNote(w?.ai)}`
    existing.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="k-card flex flex-col gap-2" aria-live="polite" data-testid="word-panel">
    <h2 class="k-h2" style="font-size: 17px">Wort</h2>
    <p v-if="!token" class="k-small m-0">Tippe ein Wort an: Bedeutung, Artikel und Plural, und bei Kasus-Linse, warum dieser Fall.</p>
    <template v-else>
      <p class="m-0 k-read" style="font-size: 24px; font-weight: 600">{{ display }}</p>
      <p v-if="token.entry?.split" class="k-hint m-0" data-testid="word-split">Trennbares Verb: {{ token.entry.split }}</p>
      <p v-if="gloss" class="m-0" style="font-size: 17px">„{{ gloss }}“</p>
      <p v-else class="k-small m-0">Keine Übersetzung gefunden.</p>
      <p v-if="token.state" class="k-hint m-0">Status: {{ STATE[token.state] }}<template v-if="token.entry?.cardId"> · im Kernwortschatz</template></p>
      <div v-if="chunk" class="flex gap-2.5 items-start mt-1">
        <span :class="['k-case', `k-case-${chunk.case}`]" :aria-label="`Kasus ${chunk.case}`">{{ chunk.case }}</span>
        <p class="m-0 k-small" style="color: var(--text)">{{ chunk.explain }}</p>
      </div>
      <p class="k-small m-0 mt-1 k-read" style="font-size: 15px">„{{ sentence }}“</p>
      <div class="flex flex-wrap items-center gap-2">
        <button class="k-btn k-btn-sm mt-1" data-testid="mine" :disabled="busy" @click="mine">{{ busy ? 'Wird gemint …' : 'Satz minen' }}</button>
        <slot name="actions" />
      </div>
      <p v-if="mined" class="k-chip k-chip-success m-0" style="width: fit-content; height: auto" data-testid="mine-result">{{ mined }}</p>
      <button v-if="existing" class="k-btn k-btn-ghost k-btn-sm" data-testid="mine-add-word" :disabled="busy" @click="addWord">„{{ target }}“ zur Karte dazunehmen</button>
      <p v-if="error" class="k-error m-0">{{ error }}</p>
    </template>
  </section>
</template>
