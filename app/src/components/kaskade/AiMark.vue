<script setup>
// "KI" next to a word field a KI filled in when mining (#19) — check it, edit it if it's wrong.
defineProps({ field: { type: String, default: '' } })
</script>

<template>
  <span class="k-origin k-origin-ai" style="padding: 0 6px" title="Von einer KI ergänzt — bitte prüfen, du kannst es bearbeiten" :data-testid="`ai-${field}`">KI</span>
</template>
