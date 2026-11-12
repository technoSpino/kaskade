import { describe, expect, it } from 'vitest'
import { coverageLabel, cuesInWindow, summarize, verdict } from '../../lib/satzcheck'

describe('summarize', () => {
  it('counts ratings and ignores unrated cues', () => {
    const s = summarize(['v', 'v', 'h', 'v', 'h', 's', 'h', 's', 'v', null])
    expect(s).toEqual({ v: 4, h: 3, s: 2, rated: 9, coverage: 78 })
  })

  it('is 0 % with nothing rated', () => {
    expect(summarize([null, null]).coverage).toBe(0)
  })

  it('counts "mit Hilfe" as covered', () => {
    expect(summarize(['h', 'h', 'h', 's']).coverage).toBe(75)
  })
})

describe('verdict (same gates as the server)', () => {
  it.each([
    [75, 'simple', null, '2A', 'phase1-done'],
    [74, 'simple', null, '1', 'phase1'],
    [80, 'adult', 2000, '2B', 'ready-2b'],
    [95, 'adult', 1500, '2A', '2a-words'],
    [80, 'adult', null, '2A', '2a-words'],
    [79, 'adult', 2500, '2A', '2a'],
    [60, 'adult', 2500, '2A', '2a'],
    [59, 'adult', 2500, '2A', 'too-hard']
  ])('%i %% %s words=%s → %s', (coverage, type, words, phase, key) => {
    const v = verdict(coverage, type, words)
    expect(v.phase).toBe(phase)
    expect(v.key).toBe(key)
  })
})

describe('cuesInWindow', () => {
  const cues = [1, 100, 179.9, 180, 400].map((start) => ({ start, text: 'Ein Satz.' }))
  it('keeps cues starting inside the window and remembers their index', () => {
    expect(cuesInWindow(cues, 0).map((c) => c.index)).toEqual([0, 1, 2])
    expect(cuesInWindow(cues, 150).map((c) => c.index)).toEqual([2, 3])
  })
})

describe('non-speech cues (follow-up #1)', () => {
  it('are skipped in the window, indices stay those of the full list', () => {
    const cues = [
      { start: 1, end: 2, text: '♪ Musik ♪' },
      { start: 3, end: 4, text: 'Na?' },
      { start: 5, end: 6, text: '* Stimmen und Lachen *' },
      { start: 7, end: 8, text: '[Klopfen]' },
      { start: 9, end: 10, text: '(dumpf)' },
      { start: 11, end: 12, text: 'Komm rein.' }
    ]
    expect(cuesInWindow(cues, 0).map((c) => c.index)).toEqual([1, 5])
  })

  it('labels recounted runs with both numbers', () => {
    expect(coverageLabel({ coverage: 80, coverageAll: 83 })).toBe('80 % (mit Geräusch-Zeilen 83 %)')
    expect(coverageLabel({ coverage: 80 })).toBe('80 %')
  })
})
