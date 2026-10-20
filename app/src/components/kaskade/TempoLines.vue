<script setup>
import { formatTime } from '../../lib/watch'

// "zu schwer" lines that were short and made of known words: the speed was the problem.
// Suggest listening practice (line in a loop, then 0.85×, then normal) instead of cards.
defineProps({
  lines: { type: Array, required: true },
  mediaId: { type: Number, default: null }
})
</script>

<template>
  <section class="tl" aria-label="Hören bei normalem Tempo" data-testid="tempo-lines">
    <p class="m-0" style="font-weight: 800; color: var(--text)">Hören bei normalem Tempo</p>
    <p class="m-0 mt-1 k-small">Diese Zeilen waren kurz, und die Wörter kennst du — es lag am Tempo, nicht am Wortschatz. Das trainierst du mit Hören, nicht mit Karten: Zeile in Schleife, erst mit 0,85×, dann normal, leise mitsprechen.</p>
    <ul class="list-none m-0 mt-2.5 p-0 flex flex-col gap-1.5">
      <li v-for="l in lines" :key="l.cue" class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span class="k-read" style="font-size: 17px">„{{ l.text }}“</span>
        <router-link
          v-if="mediaId && l.start != null"
          :to="`/schauen/${mediaId}?t=${l.start}&loop=1`"
          class="k-small"
          style="font-weight: 700"
          :data-testid="`tempo-loop-${l.cue}`"
        >{{ formatTime(l.start) }} · in Schleife üben →</router-link>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.tl { padding: 14px 16px; border-radius: var(--radius-sm); background: var(--surface-2); color: var(--text-2); }
</style>
