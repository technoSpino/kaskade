<script setup>
import { ref } from 'vue'
import { api } from '../../lib/api'

// Quick entry for immersion outside the block ("Checker Tobi, 25 min, passiv").
const props = defineProps({ today: { type: String, default: null } })
const emit = defineEmits(['saved'])
const title = ref('')
const minutes = ref(30)
const kind = ref('aktiv')
const date = ref(props.today ?? new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Berlin' }).format(new Date()))
const error = ref(null)
const busy = ref(false)

async function save() {
  busy.value = true
  error.value = null
  try {
    const r = await api.post('/immersion', { title: title.value, minutes: Number(minutes.value), kind: kind.value, date: date.value })
    title.value = ''
    emit('saved', r)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="flex flex-col gap-2.5" data-testid="immersion-form" @submit.prevent="save">
    <label class="flex flex-col gap-1 k-small">Was?
      <input v-model="title" class="k-input" required maxlength="120" placeholder="z. B. Checker Tobi, Podcast, Serie" data-testid="imm-title" />
    </label>
    <div class="flex flex-wrap gap-2.5">
      <label class="flex flex-col gap-1 k-small" style="flex: 1 1 90px">Minuten
        <input v-model="minutes" class="k-input" type="number" min="1" max="600" required data-testid="imm-minutes" />
      </label>
      <label class="flex flex-col gap-1 k-small" style="flex: 1 1 140px">Datum
        <input v-model="date" class="k-input" type="date" required />
      </label>
    </div>
    <fieldset class="flex gap-4 border-0 p-0 m-0 k-small">
      <legend class="sr-only">Art</legend>
      <label class="flex items-center gap-2"><input v-model="kind" type="radio" value="aktiv" /> aktiv (konzentriert)</label>
      <label class="flex items-center gap-2"><input v-model="kind" type="radio" value="passiv" data-testid="imm-passiv" /> passiv (nebenbei)</label>
    </fieldset>
    <div><button class="k-btn k-btn-sm" :disabled="busy || !title.trim()" data-testid="imm-save">Eintragen</button></div>
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
  </form>
</template>
