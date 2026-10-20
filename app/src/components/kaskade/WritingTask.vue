<script setup>
import { computed, ref } from 'vue'
import { api } from '../../lib/api'
import { AI_GRADE } from '../../lib/origin'
import OriginBadge from './OriginBadge.vue'

// A B1-style writing task. Saves the text; graded only when the server has an API key.
const props = defineProps({
  task: { type: Object, required: true },
  context: { type: String, required: true },
  ai: { type: Boolean, default: false },
  state: { type: Object, default: null },
  showTitle: { type: Boolean, default: true }
})
const emit = defineEmits(['progress', 'done'])

const text = ref(props.state?.draft ?? props.state?.text ?? '')
const saved = ref(props.state?.writingId ? props.state : null)
const busy = ref(false)
const error = ref(null)
const words = computed(() => (text.value.trim() ? text.value.trim().split(/\s+/).length : 0))

let timer = 0
function onInput() {
  clearTimeout(timer)
  timer = setTimeout(() => emit('progress', { draft: text.value }), 600)
}

async function submit() {
  busy.value = true
  error.value = null
  try {
    const r = await api.post('/writing', { context: props.context, promptId: props.task.id, text: text.value })
    saved.value = { text: text.value, writingId: r.id, grade: r.grade }
    emit('done', saved.value)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

const criteria = { erfuellung: 'Erfüllung', kohaerenz: 'Kohärenz', wortschatz: 'Wortschatz', strukturen: 'Strukturen' }
</script>

<template>
  <div class="flex flex-wrap gap-6 items-start" data-testid="writing-task">
    <section class="k-card flex flex-col gap-3" style="flex: 1 1 340px" :aria-label="task.title">
      <p class="k-eyebrow">{{ task.type }} · {{ task.minutes }} min</p>
      <h2 v-if="showTitle" id="wt-h" class="k-h2">{{ task.title }}</h2>
      <OriginBadge v-if="showTitle" :origin="task.origin" :source="task.source" fallback="ai" />
      <p class="k-read m-0" style="font-size: 18px; line-height: 1.6">{{ task.situation }}</p>
      <ul class="m-0 list-disc pl-5 flex flex-col gap-1.5">
        <li v-for="p in task.points" :key="p">{{ p }}</li>
      </ul>
      <p class="k-hint m-0">Schreib etwa {{ task.words }} Wörter. Denk an Anrede und Gruß.</p>
    </section>
    <section class="k-card flex flex-col gap-3" style="flex: 999 1 480px" aria-label="Dein Text">
      <textarea
        v-model="text"
        class="k-input"
        :readonly="!!saved"
        aria-label="Dein Text"
        placeholder="Liebe Jana, …"
        spellcheck="false"
        data-testid="wt-text"
        @input="onInput"
      ></textarea>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <span class="k-small" :style="{ fontWeight: 700 }">{{ words }} Wörter</span>
        <button v-if="!saved" class="k-btn" :disabled="words < 10 || busy" data-testid="wt-submit" @click="submit">
          {{ busy ? (ai ? 'Wird bewertet …' : 'Speichert …') : 'Text abgeben' }}
        </button>
        <span v-else class="k-chip k-chip-success">✓ Gespeichert</span>
      </div>
      <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
      <p v-if="!ai && !saved" class="k-hint m-0">Ohne KI-Schlüssel wird der Text nur gespeichert, nicht bewertet.</p>
      <div v-if="saved?.grade" class="k-callout flex flex-col gap-2" data-testid="wt-grade">
        <p class="m-0" style="font-size: 18px; font-weight: 800; color: var(--text)">{{ AI_GRADE }}: {{ saved.grade.level }}</p>
        <p class="m-0">{{ saved.grade.summary }}</p>
        <ul v-if="saved.grade.scores" class="m-0 pl-5">
          <li v-for="(v, k) in saved.grade.scores" :key="k">{{ criteria[k] || k }}: {{ v }}/5</li>
        </ul>
        <ul v-if="saved.grade.corrections?.length" class="m-0 pl-5">
          <li v-for="(c, i) in saved.grade.corrections" :key="i"><s>{{ c.original }}</s> → <strong>{{ c.korrektur }}</strong> — {{ c.erklaerung }}</li>
        </ul>
      </div>
    </section>
  </div>
</template>
