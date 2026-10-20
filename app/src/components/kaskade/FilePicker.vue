<script setup>
import { ref, useId } from 'vue'

// German, themed file picker ("Datei wählen" + file name). The real <input type="file">
// stays in the tab order (visually hidden), so Tab + Space/Enter open the dialog.
defineProps({
  label: { type: String, required: true },
  accept: { type: String, default: '' },
  testid: { type: String, default: null }
})
const emit = defineEmits(['change'])
const input = ref(null)
const name = ref('')
const id = useId()

function onChange() {
  const f = input.value?.files?.[0] ?? null
  name.value = f ? f.name : ''
  emit('change', f)
}

defineExpose({
  get files() {
    return input.value?.files ?? null
  }
})
</script>

<template>
  <div class="flex flex-col gap-1 k-small">
    <span :id="`${id}-label`">{{ label }}</span>
    <div class="fp">
      <input
        :id="id"
        ref="input"
        type="file"
        class="fp-input"
        :accept="accept"
        :aria-labelledby="`${id}-label`"
        :aria-describedby="`${id}-name`"
        :data-testid="testid"
        @change="onChange"
      />
      <label :for="id" class="k-btn k-btn-ghost k-btn-sm fp-btn" aria-hidden="true">Datei wählen</label>
      <span :id="`${id}-name`" class="fp-name" aria-live="polite">{{ name || 'keine Datei' }}</span>
    </div>
  </div>
</template>

<style scoped>
.fp { position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.fp-input { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; border: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.fp-input:focus-visible + .fp-btn { outline: var(--focus-width) solid var(--focus); outline-offset: 2px; }
.fp-name { min-width: 0; color: var(--text-2); overflow-wrap: anywhere; }
</style>
