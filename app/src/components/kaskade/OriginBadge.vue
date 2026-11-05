<script setup>
import { computed } from 'vue'
import { AI_BADGE_HINT, originBadge } from '../../lib/origin'

// "KI-geschrieben" for Kaskade's own AI-written content, the source for real material (#16).
const props = defineProps({
  origin: { type: String, default: null },
  source: { type: String, default: null },
  // assume this origin when the item doesn't say (Kaskade's own content is AI-written)
  fallback: { type: String, default: null }
})
const badge = computed(() => originBadge(props.origin, props.source, props.fallback))
</script>

<template>
  <span
    v-if="badge?.kind === 'ai'"
    class="k-origin k-origin-ai"
    :title="AI_BADGE_HINT"
    data-testid="origin-ai"
  >{{ badge.text }}</span>
  <span v-else-if="badge" class="k-origin k-origin-real" data-testid="origin-real">Quelle: {{ badge.text }}</span>
</template>
