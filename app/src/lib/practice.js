// Helpers for the B1 practice bank.

export const PASS = 0.6

/** Question ids an item expects answers for. */
export function answerIds(item) {
  return (item.questions ?? item.situations ?? []).map((q) => q.id)
}

export function isComplete(item, answers) {
  return answerIds(item).every((id) => answers[id] !== undefined && answers[id] !== null)
}

/** Seconds left in timed mode (never negative). */
export function timeLeft(minutes, startedAt, now) {
  return Math.max(0, Math.round(minutes * 60 - (now - startedAt) / 1000))
}

export function verdictLabel(pct) {
  if (pct == null) return 'noch nicht geübt'
  return pct >= PASS ? 'bestanden (≥ 60 %)' : 'noch unter 60 %'
}

export const KIND_LABEL = {
  'richtig-falsch': 'Richtig oder falsch',
  mc: 'Multiple Choice',
  zuordnung: 'Zuordnung',
  durchsage: 'Durchsage',
  anrufbeantworter: 'Anrufbeantworter',
  gespraech: 'Gespräch',
  radio: 'Radiointerview'
}
