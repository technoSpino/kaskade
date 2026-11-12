// Where content comes from (#16): Kaskade's own AI-written texts vs. real German with a source.

export const AI_BADGE = 'KI-geschrieben'
export const AI_BADGE_HINT = 'Für Kaskade von einer KI geschrieben — kein echtes Material'
export const TTS_NOTE = 'Computerstimme'
export const AI_GRADE = 'KI-Bewertung'

/**
 * What the badge shows for an item: { kind: 'ai' | 'real', text } or null (unknown origin).
 * `fallback` is the origin to assume when the item doesn't say (Kaskade's own content = 'ai').
 */
export function originBadge(origin, source, fallback = null) {
  const o = origin ?? fallback
  if (o === 'ai') return { kind: 'ai', text: AI_BADGE }
  if (o === 'real' && source) return { kind: 'real', text: source }
  return null
}

/** Badge for a card: core deck and mined sentences both send origin + originSource. */
export const cardBadge = (card) => originBadge(card?.origin, card?.originSource, card?.n ? 'ai' : null)

/** Audio note: the original voice of a clip, else the computer voice (Piper / browser). */
export const audioNote = (card) => (card?.audio ? 'Originalton' : TTS_NOTE)
