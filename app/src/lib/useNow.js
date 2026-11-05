import { onBeforeUnmount, onMounted, ref } from 'vue'

/** A reactive Date that updates every `ms` milliseconds while mounted. */
export function useNow(ms = 1000) {
  const now = ref(new Date())
  let t = 0
  onMounted(() => { t = setInterval(() => { now.value = new Date() }, ms) })
  onBeforeUnmount(() => clearInterval(t))
  return now
}

export const BLOCK_LABELS = {
  karten: 'Karten',
  input: 'Schauen',
  pause: 'Pause',
  lesen: 'Freies Lesen',
  pruefung: 'Prüfungsteil',
  extra: 'Extra'
}
