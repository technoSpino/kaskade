<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../lib/api'
import { CASE_OPTIONS } from '../../lib/cards'

// Edit or delete a mined card (#19): lemma, display, gloss, case, note. What he edits loses its KI mark.
const props = defineProps({ card: { type: Object, required: true } })
const emit = defineEmits(['saved', 'deleted', 'cancel'])

const n = props.card.id.split(':')[1]
const form = ref({
  lemma: props.card.lemma,
  display: props.card.display,
  gloss: props.card.gloss === '—' ? '' : props.card.gloss,
  case: props.card.case ?? '',
  note: props.card.note ?? ''
})
const first = ref(null)
onMounted(() => first.value?.focus())
const confirming = ref(false)
const busy = ref(false)
const error = ref(null)

async function save() {
  busy.value = true
  error.value = null
  const f = form.value
  const changed = {}
  if (f.lemma.trim() !== props.card.lemma) changed.lemma = f.lemma.trim()
  if (f.display.trim() !== props.card.display) changed.display = f.display.trim()
  if (f.gloss.trim() !== (props.card.gloss === '—' ? '' : props.card.gloss)) changed.gloss = f.gloss.trim()
  if ((f.case || null) !== (props.card.case ?? null)) changed.case = f.case || null
  if (f.note.trim() !== (props.card.note ?? '')) changed.note = f.note.trim()
  try {
    emit('saved', Object.keys(changed).length ? await api.patch(`/mined/${n}`, changed) : props.card)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function remove() {
  busy.value = true
  try {
    await api.del(`/mined/${n}`)
    emit('deleted', props.card)
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}
</script>

<template>
  <form class="flex flex-col gap-2.5" data-testid="mined-editor" @submit.prevent="save" @keydown.stop>
    <label class="me-field">Grundform
      <input ref="first" v-model="form.lemma" class="k-input" required maxlength="80" data-testid="edit-lemma" />
    </label>
    <label class="me-field">Anzeige (mit Artikel · Plural)
      <input v-model="form.display" class="k-input" required maxlength="120" data-testid="edit-display" />
    </label>
    <label class="me-field">Bedeutung
      <input v-model="form.gloss" class="k-input" maxlength="200" data-testid="edit-gloss" />
    </label>
    <label class="me-field">Kasus
      <select v-model="form.case" class="k-input" data-testid="edit-case">
        <option v-for="o in CASE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
    </label>
    <label class="me-field">Notiz
      <input v-model="form.note" class="k-input" maxlength="300" data-testid="edit-note" />
    </label>
    <p v-if="error" class="k-error m-0">{{ error }}</p>
    <div class="flex flex-wrap items-center gap-2 mt-1">
      <button type="submit" class="k-btn k-btn-sm" :disabled="busy" data-testid="edit-save">Speichern</button>
      <button type="button" class="k-btn k-btn-ghost k-btn-sm" :disabled="busy" @click="emit('cancel')">Abbrechen</button>
      <button v-if="!confirming" type="button" class="k-btn k-btn-ghost k-btn-sm me-delete" :disabled="busy" data-testid="edit-delete" @click="confirming = true">Karte löschen</button>
      <span v-else class="inline-flex items-center gap-2">
        <span class="k-small">Wirklich löschen?</span>
        <button type="button" class="k-btn k-btn-sm me-delete-yes" :disabled="busy" data-testid="edit-delete-yes" @click="remove">Ja, löschen</button>
        <button type="button" class="k-btn k-btn-ghost k-btn-sm" @click="confirming = false">Nein</button>
      </span>
    </div>
  </form>
</template>

<style scoped>
.me-field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; font-weight: 700; color: var(--muted); }
.me-field .k-input { font-weight: 500; color: var(--text); }
.me-delete { color: var(--danger); }
.me-delete-yes { background: var(--surface); border-color: var(--danger); color: var(--danger); }
</style>
