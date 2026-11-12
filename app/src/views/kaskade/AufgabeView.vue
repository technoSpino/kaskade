<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../lib/api'
import WritingTask from '../../components/kaskade/WritingTask.vue'
import SpeakingTask from '../../components/kaskade/SpeakingTask.vue'
import OriginBadge from '../../components/kaskade/OriginBadge.vue'

const route = useRoute()
const prompt = ref(null)
const ai = ref(false)
const error = ref(null)
const done = ref(false)
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Berlin' }).format(new Date())

onMounted(async () => {
  try {
    const [p, h] = await Promise.all([api.get(`/plan/prompt/${route.params.id}`), api.get('/health')])
    prompt.value = p
    ai.value = h.ai
  } catch (e) {
    error.value = e.message
  }
})

const speakingQuestions = computed(() =>
  prompt.value
    ? [{ id: prompt.value.id, prompt: prompt.value.title, hint: `Sprich frei, etwa ${prompt.value.minutes - 5} Minuten. Nimm dich auf und hör es dir danach an.`, seconds: (prompt.value.minutes - 5) * 60 }]
    : []
)
</script>

<template>
  <main class="k-main" data-testid="aufgabe">
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
    <template v-if="prompt">
      <div>
        <p class="k-eyebrow mb-1.5">B1-Prüfungsteil · {{ prompt.skill === 'schreiben' ? 'Schreiben' : 'Sprechen' }} · {{ prompt.minutes }} min</p>
        <h1 class="k-h1">{{ prompt.title }}</h1>
        <OriginBadge class="mt-2" :origin="prompt.origin" :source="prompt.source" fallback="ai" />
        <p class="k-lead">Eigene Übungsaufgabe im Stil der B1-Prüfung (keine echte Prüfungsaufgabe).</p>
      </div>

      <WritingTask
        v-if="prompt.skill === 'schreiben'"
        :task="prompt"
        :context="`plan:${today}`"
        :ai="ai"
        :show-title="false"
        @done="done = true"
      />

      <template v-else>
        <section class="k-card flex flex-col gap-3">
          <p class="k-eyebrow">{{ prompt.type }}</p>
          <p class="k-read m-0" style="font-size: 18px; line-height: 1.6">{{ prompt.situation }}</p>
          <ul class="m-0 list-disc pl-5 flex flex-col gap-1.5">
            <li v-for="p in prompt.points" :key="p">{{ p }}</li>
          </ul>
        </section>
        <SpeakingTask :questions="speakingQuestions" :context="`plan:${today}`" @done="done = true" />
      </template>

      <section class="k-callout">
        <strong>Tipps</strong>
        <ul class="m-0 mt-1.5 list-disc pl-5">
          <li v-for="tip in prompt.tips" :key="tip">{{ tip }}</li>
        </ul>
      </section>
      <div class="flex gap-3">
        <router-link to="/" class="k-btn" :class="{ 'k-btn-ghost': !done }">{{ done ? 'Fertig — zurück zu Heute' : 'Zurück zu Heute' }}</router-link>
      </div>
    </template>
  </main>
</template>
