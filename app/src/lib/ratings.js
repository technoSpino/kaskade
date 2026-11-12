// "Wie viel hast du verstanden?" (#23) and Schauen's "zu schwer" lines: pure helpers.

export const PCTS = [20, 40, 60, 80, 100]
export const TOO_HARD = 70

/**
 * Lines marked too hard of the lines heard from `from` to `to` (as ratings.hard_share on the
 * server). `marks` are the start times of the marked lines; one line marked twice counts once.
 */
export function hardShare(cues, from, to, marks) {
  const heard = cues.filter((c) => c.start >= from - 0.5 && c.start < to).length
  const marked = new Set(marks.map((m) => Math.round(m * 10))).size
  const lines = Math.max(heard, marked)
  return { marked, lines, pct: lines ? Math.round((100 * marked) / lines) : 0 }
}

/** "Heute 38 von 210 Zeilen als zu schwer markiert (18 %)" — null before any line was heard. */
export function shareLine(share) {
  if (!share?.lines) return null
  return `Heute ${share.marked} von ${share.lines} ${share.lines === 1 ? 'Zeile' : 'Zeilen'} als zu schwer markiert (${share.pct} %)`
}

/** A stored rating as a short chip text: "Verstanden: 60 %" / "Einschätzung übersprungen". */
export function ratingLabel(r) {
  if (!r) return null
  return r.pct == null ? 'Einschätzung übersprungen' : `Verstanden: ${r.pct} %`
}

/** "Di 13.10." from "2026-10-13" (ratings list on Fahrplan). */
export function shortDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  const wd = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'][new Date(Date.UTC(y, m - 1, d)).getUTCDay()]
  return `${wd} ${d}.${m}.`
}

const BLOCK_ORDER = ['input', 'lesen', 'pruefung']
const BLOCK_TITLE = { input: 'Schauen & minen', lesen: 'Frei lesen / hören', pruefung: 'Lesetest' }

/** Fahrplan: ratings grouped per block (newest first), with the average of the last five. */
export function byBlock(ratings) {
  return BLOCK_ORDER.map((block) => {
    const rows = ratings.filter((r) => r.block === block && r.pct != null)
    const last = rows.slice(0, 5)
    const avg = last.length ? Math.round(last.reduce((a, r) => a + r.pct, 0) / last.length) : null
    return { block, title: BLOCK_TITLE[block], rows, avg }
  }).filter((g) => g.rows.length || g.block !== 'pruefung')
}
