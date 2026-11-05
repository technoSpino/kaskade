// Satz-Check coverage + verdict for the live sidebar. Mirrors
// server/kaskade/satzcheck.py (the server's verdict is the one that is stored).

import { isNonSpeech } from './watch'

export const SIMPLE_GATE = 75
export const ADULT_GATE = 80
export const LOWER_2A = 60
export const WORDS_2B = 1900

/** ratings: array of 'v' | 'h' | 's' | null (null = not rated yet). */
export function summarize(ratings) {
  const v = ratings.filter((r) => r === 'v').length
  const h = ratings.filter((r) => r === 'h').length
  const s = ratings.filter((r) => r === 's').length
  const rated = v + h + s
  return { v, h, s, rated, coverage: rated ? Math.round(((v + h) / rated) * 100) : 0 }
}

export function verdict(coverage, contentType, words) {
  if (contentType === 'simple') {
    return coverage >= SIMPLE_GATE
      ? { phase: '2A', key: 'phase1-done', title: 'Phase 1 geschafft' }
      : { phase: '1', key: 'phase1', title: 'Noch Phase 1' }
  }
  if (coverage >= ADULT_GATE) {
    return words != null && words >= WORDS_2B
      ? { phase: '2B', key: 'ready-2b', title: 'Bereit für Phase 2B' }
      : { phase: '2A', key: '2a-words', title: 'Verständnis reicht — Wortschatz noch nicht' }
  }
  if (coverage >= LOWER_2A) return { phase: '2A', key: '2a', title: 'Phase 2A — fast da' }
  return { phase: '2A', key: 'too-hard', title: 'Noch zu schwer' }
}

/** Speech cues that start inside [start, start + length) — sound and music cues are skipped.
 * Returns [{...cue, index}] with the index into the full cue list. */
export function cuesInWindow(cues, start, length = 180) {
  return cues
    .map((c, index) => ({ ...c, index }))
    .filter((c) => c.start >= start && c.start < start + length && !isNonSpeech(c.text))
}

/** "80 %" or, for older runs that still counted sound cues, "80 % (mit Geräusch-Zeilen 83 %)". */
export const coverageLabel = (r) => (r.coverageAll != null ? `${r.coverage} % (mit Geräusch-Zeilen ${r.coverageAll} %)` : `${r.coverage} %`)
