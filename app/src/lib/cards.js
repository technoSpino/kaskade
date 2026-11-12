// Helpers for sentence cards.

/** Split a sentence around the first occurrence of `target` (for highlighting). */
export function splitTarget(sentence, target) {
  const i = target ? sentence.indexOf(target) : -1
  if (i === -1) return { pre: sentence, target: '', post: '' }
  return { pre: sentence.slice(0, i), target, post: sentence.slice(i + target.length) }
}

/**
 * A sentence as segments with every target word marked (#19: a card can have a second word):
 * markTargets('Er versaust die Chance', ['versaust', 'Chance']) → [{text:'Er ',mark:false}, {text:'versaust',mark:true}, …]
 */
export function markTargets(sentence, targets) {
  const spans = []
  for (const t of targets.filter(Boolean)) {
    const i = sentence.indexOf(t)
    if (i >= 0 && !spans.some(([a, b]) => i < b && i + t.length > a)) spans.push([i, i + t.length])
  }
  spans.sort((x, y) => x[0] - y[0])
  const out = []
  let at = 0
  for (const [a, b] of spans) {
    if (a > at) out.push({ text: sentence.slice(at, a), mark: false })
    out.push({ text: sentence.slice(a, b), mark: true })
    at = b
  }
  if (at < sentence.length) out.push({ text: sentence.slice(at), mark: false })
  return out
}

/** The words of a mined card: its target first, then the ones added later from the same line. */
export const cardWords = (card) => [
  { target: card.target, lemma: card.lemma, display: card.display, gloss: card.gloss, case: card.case, note: card.note, ai: card.aiFields ?? [] },
  ...(card.words ?? [])
]

export const CASE_OPTIONS = [
  { value: '', label: '— kein Kasus' },
  { value: 'N', label: 'N · Nominativ' },
  { value: 'A', label: 'A · Akkusativ' },
  { value: 'D', label: 'D · Dativ' },
  { value: 'G', label: 'G · Genitiv' }
]
