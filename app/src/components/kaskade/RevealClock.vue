<script setup>
// #28: the time to reveal on the card. Its own component so the ticking (8×/s) re-renders only this.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { clockText } from '../../lib/reveal'

const props = defineProps({
  timer: { type: Object, required: true }, // createRevealTimer()
  phase: { type: String, default: null }, // audio | run | pause | done
  finalMs: { type: Number, default: null }, // the time at reveal
  timing: { type: Object, default: null } // easyMs / hardMs of this card
})

const text = ref('')
const render = () => {
  text.value = clockText(props.phase === 'done' ? (props.finalMs ?? 0) : props.timer.ms, props.phase, props.timing)
}
watch(() => [props.phase, props.finalMs, props.timing], render, { immediate: true })
let tick = 0
onMounted(() => { tick = setInterval(() => { if (props.phase === 'run') render() }, 125) })
onBeforeUnmount(() => clearInterval(tick))
</script>

<template>
  <span class="kc-clock" role="timer" :data-phase="phase" data-testid="karte-clock"
    title="Zeit bis zum Aufdecken — läuft nicht, solange das Audio spielt">{{ text }}</span>
</template>

<style scoped>
.kc-clock { font-size: 14px; font-weight: 600; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>
