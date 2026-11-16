<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../../lib/api'

// Yes/no vocabulary test. Resumable: pass saved `state` ({items, answers}),
// listen to `progress` to persist it. Emits `done` with the scored result.
const props = defineProps({
  state: { type: Object, default: null }
})
const emit = defineEmits(['progress', 'done'])

const items = ref(props.state?.items ?? [])
const answers = ref(props.state?.answers ?? [])
const started = ref(answers.value.length > 0)
const error = ref(null)
const submitting = ref(false)

const index = computed(() => answers.value.length)
const current = computed(() => items.value[index.value])
const pct = computed(() => (items.value.length ? Math.round((index.value / items.value.length) * 100) : 0))

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  if (!items.value.length) {
    try {
      items.value = (await api.get('/vocab/test')).items
    } catch (e) {
      error.value = e.message
    }
  }
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function answer(yes) {
  if (!started.value || !current.value || submitting.value) return
  answers.value = [...answers.value, { ...current.value, yes }]
  emit('progress', { items: items.value, answers: answers.value })
  if (answers.value.length === items.value.length) submit()
}

function back() {
  if (!answers.value.length || submitting.value) return
  answers.value = answers.value.slice(0, -1)
  emit('progress', { items: items.value, answers: answers.value })
}

async function submit() {
  submitting.value = true
  error.value = null
  try {
    const result = await api.post('/vocab/result', { answers: answers.value })
    emit('done', result)
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target?.tagName)) return
  const k = e.key.toLowerCase()
  if (!started.value && (k === 'enter' || k === ' ')) {
    e.preventDefault()
    started.value = true
  } else if (k === 'j') answer(true)
  else if (k === 'n') answer(false)
  else if (k === 'backspace') back()
}
</script>

<template>
  <section class="k-card flex flex-col gap-5" aria-labelledby="vt-h" data-testid="vocab-test">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="vt-h" class="k-h2">Kennst du das Wort?</h2>
      <p class="k-hint m-0">{{ index }} / {{ items.length || '…' }}</p>
    </div>
    <div class="k-progress" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100">
      <div :style="{ width: pct + '%' }"></div>
    </div>

    <p v-if="error" class="k-error" role="alert">{{ error }}
      <button v-if="answers.length === items.length && items.length" class="k-btn k-btn-sm ml-2" @click="submit">Nochmal senden</button>
    </p>

    <template v-if="!started">
      <div class="k-small flex flex-col gap-2" style="max-width: 62ch">
        <p class="m-0">Du siehst etwa 145 Wörter, eins nach dem anderen. Sag <strong>Ja</strong> nur, wenn du eine Bedeutung nennen könntest. Manche Wörter sind <strong>erfunden</strong> — wer dort Ja sagt, bekommt Punkte abgezogen.</p>
        <p class="m-0">Schnell und ehrlich antworten, nicht lange nachdenken. Etwa 5 Minuten.</p>
      </div>
      <div>
        <button class="k-btn" :disabled="!items.length" data-testid="vt-start" @click="started = true">
          Test starten <kbd class="k-kbd">Enter</kbd>
        </button>
      </div>
    </template>

    <template v-else-if="current">
      <p class="k-read m-0 text-center py-10" style="font-size: clamp(32px, 8vw, 48px); line-height: 1.2" data-testid="vt-word" aria-live="polite">{{ current.word }}</p>
      <div class="grid grid-cols-2 gap-3">
        <button class="k-btn k-btn-ghost" style="min-height: 64px" data-testid="vt-no" @click="answer(false)">
          <kbd class="k-kbd">N</kbd> Nein
        </button>
        <button class="k-btn" style="min-height: 64px" data-testid="vt-yes" @click="answer(true)">
          <kbd class="k-kbd">J</kbd> Ja, kenne ich
        </button>
      </div>
      <p class="k-hint m-0">Tasten: J = ja · N = nein · ⌫ = zurück</p>
    </template>

    <p v-else class="k-small m-0" aria-live="polite">{{ submitting ? 'Wird ausgewertet …' : 'Fertig.' }}</p>
  </section>
</template>
