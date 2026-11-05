<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import OriginBadge from './OriginBadge.vue'

// Placement reading: texts with multiple-choice questions. Keys A/B/C, Enter = weiter.
const props = defineProps({
  texts: { type: Array, required: true },
  state: { type: Object, default: null }
})
const emit = defineEmits(['progress', 'done'])

const questions = computed(() => props.texts.flatMap((t) => t.questions.map((q) => ({ ...q, textId: t.id }))))
const answers = ref({ ...(props.state?.answers ?? {}) })
const index = ref(Math.min(props.state?.index ?? 0, questions.value.length - 1))
const error = ref(null)
const busy = ref(false)

const q = computed(() => questions.value[index.value])
const text = computed(() => props.texts.find((t) => t.id === q.value.textId))
const textNo = computed(() => props.texts.findIndex((t) => t.id === q.value.textId) + 1)
const qNo = computed(() => text.value.questions.findIndex((x) => x.id === q.value.id) + 1)
const picked = computed(() => answers.value[q.value.id])
const keys = ['A', 'B', 'C', 'D']

function pick(i) {
  answers.value = { ...answers.value, [q.value.id]: i }
  emit('progress', { answers: answers.value, index: index.value })
}

async function next() {
  if (picked.value === undefined || busy.value) return
  if (index.value < questions.value.length - 1) {
    index.value++
    emit('progress', { answers: answers.value, index: index.value })
    return
  }
  busy.value = true
  error.value = null
  try {
    const result = await api.post('/placement/reading/score', { answers: answers.value })
    emit('done', { answers: answers.value, result })
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function back() {
  if (index.value > 0) index.value--
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target?.tagName)) return
  const k = e.key.toUpperCase()
  const i = keys.indexOf(k)
  if (i !== -1 && i < q.value.options.length) pick(i)
  else if (e.key === 'Enter') next()
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="flex flex-wrap gap-6 items-start" data-testid="reading-test">
    <article class="k-card" style="flex: 999 1 520px" aria-labelledby="rt-title">
      <p class="k-eyebrow">Text {{ textNo }} von {{ texts.length }} · {{ text.kind }}</p>
      <h2 id="rt-title" class="k-h2 mt-1.5">{{ text.title }}</h2>
      <OriginBadge class="mt-1.5" :origin="text.origin" :source="text.source" fallback="ai" />
      <div class="k-read mt-4 flex flex-col gap-3" style="font-size: 18px; line-height: 1.7">
        <p v-for="(para, i) in text.text.split('\n\n')" :key="i" class="m-0">{{ para }}</p>
      </div>
    </article>
    <section class="k-card flex flex-col gap-4" style="flex: 1 1 360px; position: sticky; top: 12px" aria-labelledby="rt-q">
      <p class="k-eyebrow">Frage {{ qNo }} von {{ text.questions.length }}</p>
      <h3 id="rt-q" class="k-read m-0" style="font-size: 22px; font-weight: 600; line-height: 1.35">{{ q.question }}</h3>
      <div role="radiogroup" aria-labelledby="rt-q" class="flex flex-col gap-2.5">
        <button
          v-for="(o, i) in q.options"
          :key="i"
          type="button"
          role="radio"
          class="k-option"
          :aria-checked="picked === i ? 'true' : 'false'"
          :data-testid="`rt-opt-${i}`"
          @click="pick(i)"
        ><span class="k-key">{{ keys[i] }}</span><span>{{ o }}</span></button>
      </div>
      <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <button class="k-btn k-btn-ghost k-btn-sm" :disabled="index === 0" @click="back">Zurück</button>
        <button class="k-btn" :disabled="picked === undefined || busy" data-testid="rt-next" @click="next">
          {{ index === questions.length - 1 ? 'Auswerten' : 'Weiter' }} <kbd class="k-kbd">Enter</kbd>
        </button>
      </div>
      <p class="k-hint m-0">Tasten A, B, C · Enter = weiter. Kein Ergebnis während des Tests.</p>
    </section>
  </div>
</template>
