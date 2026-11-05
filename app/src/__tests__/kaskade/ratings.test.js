import { describe, expect, it } from 'vitest'
import { byBlock, hardShare, PCTS, ratingLabel, shareLine, shortDate } from '../../lib/ratings'

const cues = Array.from({ length: 10 }, (_, i) => ({ start: 10 * (i + 1), end: 10 * (i + 1) + 3, text: `Zeile ${i + 1}` }))

describe('hardShare (#23 Schauen: lines marked "zu schwer")', () => {
  it('counts the lines heard from the start of today\'s part to the playhead', () => {
    expect(hardShare(cues, 0, 80, [20, 50])).toEqual({ marked: 2, lines: 7, pct: 29 })
    expect(hardShare(cues, 30, 80, [])).toEqual({ marked: 0, lines: 5, pct: 0 })
  })
  it('a line marked twice counts once', () => {
    expect(hardShare(cues, 0, 100, [20, 20.04, 50]).marked).toBe(2)
  })
  it('never more marked than heard (marks from before a reload count)', () => {
    expect(hardShare(cues, 90, 95, [20, 30, 40])).toEqual({ marked: 3, lines: 3, pct: 100 })
  })
  it('nothing heard yet → 0 lines, 0 %', () => {
    expect(hardShare(cues, 0, 5, [])).toEqual({ marked: 0, lines: 0, pct: 0 })
    expect(hardShare([], 0, 100, [])).toEqual({ marked: 0, lines: 0, pct: 0 })
  })
})

describe('labels', () => {
  it('the share line next to the buttons', () => {
    expect(shareLine({ marked: 38, lines: 210, pct: 18 })).toBe('Heute 38 von 210 Zeilen als zu schwer markiert (18 %)')
    expect(shareLine({ marked: 0, lines: 1, pct: 0 })).toBe('Heute 0 von 1 Zeile als zu schwer markiert (0 %)')
    expect(shareLine({ marked: 0, lines: 0, pct: 0 })).toBeNull()
    expect(shareLine(null)).toBeNull()
  })
  it('five buttons, a stored rating as a chip, dates', () => {
    expect(PCTS).toEqual([20, 40, 60, 80, 100])
    expect(ratingLabel({ pct: 60 })).toBe('Verstanden: 60 %')
    expect(ratingLabel({ pct: null })).toBe('Einschätzung übersprungen')
    expect(ratingLabel(null)).toBeNull()
    expect(shortDate('2026-10-13')).toBe('Di 13.10.')
  })
})

describe('byBlock (Fahrplan)', () => {
  it('groups per block, skips skipped ones, averages the last five', () => {
    const rows = [
      { id: 7, block: 'lesen', pct: 80 }, { id: 6, block: 'input', pct: 60 }, { id: 5, block: 'lesen', pct: null },
      { id: 4, block: 'lesen', pct: 40 }, { id: 3, block: 'pruefung', pct: 60 }
    ]
    const g = byBlock(rows)
    expect(g.map((x) => [x.block, x.rows.length, x.avg])).toEqual([['input', 1, 60], ['lesen', 2, 60], ['pruefung', 1, 60]])
    expect(byBlock([]).map((x) => x.block)).toEqual(['input', 'lesen']) // the Lesetest only once there is one
  })
})
