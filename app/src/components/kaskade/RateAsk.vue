<script setup>
import { PCTS } from '../../lib/ratings'

// #23: one question after a block — five buttons, one tap, skippable.
defineProps({
  label: { type: String, default: '' },
  share: { type: String, default: null }, // Schauen: "Heute 38 von 210 Zeilen als zu schwer markiert (18 %)"
  busy: { type: Boolean, default: false }
})
const emit = defineEmits(['rate'])
</script>

<template>
  <div class="ra" role="group" aria-labelledby="ra-q" data-testid="rate-ask">
    <p id="ra-q" class="m-0 ra-q">Wie viel hast du verstanden?</p>
    <p v-if="label" class="k-hint m-0 mt-0.5">{{ label }}</p>
    <p v-if="share" class="k-small m-0 mt-1" data-testid="rate-share">{{ share }}</p>
    <div class="flex flex-wrap items-center gap-2 mt-2.5">
      <button
        v-for="p in PCTS"
        :key="p"
        type="button"
        class="k-btn k-btn-sm ra-pct"
        :disabled="busy"
        :data-testid="`rate-${p}`"
        @click="emit('rate', p)"
      >{{ p }} %</button>
      <button type="button" class="ra-skip" :disabled="busy" data-testid="rate-skip" @click="emit('rate', null)">Überspringen</button>
    </div>
  </div>
</template>

<style scoped>
.ra { margin-top: 10px; padding: 12px 14px; background: var(--callout); border-radius: var(--radius-sm); }
.ra-q { font-weight: 800; color: var(--text); }
.ra-pct { min-width: 58px; justify-content: center; }
.ra-skip {
  padding: 0 4px; border: 0; background: none; cursor: pointer;
  font: inherit; font-size: 13px; font-weight: 700; color: var(--text-2);
  text-decoration: underline; text-underline-offset: 2px;
}
.ra-skip:hover { color: var(--text); }
</style>
