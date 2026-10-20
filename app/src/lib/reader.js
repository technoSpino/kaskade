// Reader helpers: split a paragraph into plain and glossary segments.

const LETTER = /[\p{L}\p{N}]/u

function isBoundary(text, i) {
  return i < 0 || i >= text.length || !LETTER.test(text[i])
}

/**
 * Split `paragraph` into [{ text, entry? }] where `entry` is the glossary item for
 * whole-word matches of its `term` (longest terms win, every occurrence).
 */
export function markGlossary(paragraph, glossary) {
  const terms = [...glossary].sort((a, b) => b.term.length - a.term.length)
  const hits = []
  for (const entry of terms) {
    let from = 0
    while (true) {
      const i = paragraph.indexOf(entry.term, from)
      if (i === -1) break
      const end = i + entry.term.length
      const free = !hits.some((h) => i < h.end && end > h.start)
      if (free && isBoundary(paragraph, i - 1) && isBoundary(paragraph, end)) hits.push({ start: i, end, entry })
      from = i + 1
    }
  }
  hits.sort((a, b) => a.start - b.start)
  const out = []
  let pos = 0
  for (const h of hits) {
    if (h.start > pos) out.push({ text: paragraph.slice(pos, h.start) })
    out.push({ text: paragraph.slice(h.start, h.end), entry: h.entry })
    pos = h.end
  }
  if (pos < paragraph.length) out.push({ text: paragraph.slice(pos) })
  return out
}

/** The sentence (from an analysis) that contains token index `i`. */
export function sentenceOf(analysis, i) {
  const s = analysis.sentences.find((x) => i >= x.start && i < x.end)
  return s ? s.text : ''
}

export const paragraphs =(text) => text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)

/**
 * Tokens joined into groups that must not break across lines: a group ends at a token
 * followed by whitespace. So opening marks („ ‚ « ( [) stick to the next word, closing
 * marks (“ ‘ » ) ] . , ! ? : ;) and case superscripts to the previous one.
 */
export function groupTokens(tokens) {
  const groups = []
  let cur = []
  for (const t of tokens) {
    cur.push(t)
    if (t.ws) {
      groups.push(cur)
      cur = []
    }
  }
  if (cur.length) groups.push(cur)
  return groups
}

/** Reader view: highlight new words, the case lens, or both. */
export const READER_VIEWS = [
  { id: 'neu', label: 'Neue Wörter' },
  { id: 'kasus', label: 'Kasus' },
  { id: 'beides', label: 'Beides' }
]
const VIEW_KEY = 'kaskade-reader-view'

/** The remembered choice, else phase 2B → new words only (calm), otherwise both. */
export function defaultView(stored, phase) {
  if (READER_VIEWS.some((v) => v.id === stored)) return stored
  return phase === '2B' ? 'neu' : 'beides'
}

export const viewFlags = (view) => ({ states: view !== 'kasus', lens: view !== 'neu' })

export function storedView(storage = globalThis.localStorage) {
  try {
    return storage?.getItem(VIEW_KEY) ?? null
  } catch {
    return null
  }
}

export function storeView(view, storage = globalThis.localStorage) {
  try {
    storage?.setItem(VIEW_KEY, view)
  } catch {
    /* private mode: the choice just isn't remembered */
  }
}
